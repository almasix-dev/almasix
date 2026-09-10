import { Channel, PresenceChannel, PrivateChannel } from "./channel.js";
import type { AuthResponse, SonarFrame, SonarOptions } from "./types.js";

const DEFAULT_PATH = "/broadcasting/socket";
const DEFAULT_AUTH = "/broadcasting/auth";

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.location !== "undefined";
}

function deriveWsUrl(options: SonarOptions): string {
  if (options.wsUrl) return options.wsUrl;

  const forceTLS = Boolean(options.forceTLS);
  let scheme = options.scheme;
  if (!scheme) {
    if (forceTLS) scheme = "wss";
    else if (isBrowser()) scheme = window.location.protocol === "https:" ? "wss" : "ws";
    else scheme = "ws";
  }

  let host = options.host;
  if (!host) {
    if (!isBrowser()) {
      throw new Error("@almasix/sonar: set `host` or `wsUrl` outside a browser.");
    }
    host = window.location.hostname;
  }

  let port = options.port;
  if (port === undefined || port === "") {
    if (isBrowser() && window.location.port) port = window.location.port;
    else port = scheme === "wss" ? 443 : 80;
  }

  const path = options.path ?? DEFAULT_PATH;
  const portPart =
    (scheme === "wss" && String(port) === "443") || (scheme === "ws" && String(port) === "80")
      ? ""
      : `:${port}`;

  return `${scheme}://${host}${portPart}${path.startsWith("/") ? path : `/${path}`}`;
}

function deriveAuthUrl(options: SonarOptions): string {
  const endpoint = options.authEndpoint ?? DEFAULT_AUTH;
  if (/^https?:\/\//i.test(endpoint)) return endpoint;
  if (!isBrowser()) {
    throw new Error("@almasix/sonar: set an absolute `authEndpoint` outside a browser.");
  }
  return `${window.location.origin}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
}

/**
 * Sonar — first-party client for Almasix's native `/broadcasting/socket` server.
 *
 * Speaks the `almasix:*` frame protocol the server uses today. Does **not**
 * require pusher-js.
 */
export class Sonar {
  readonly options: SonarOptions;
  #socket: WebSocket | null = null;
  #socketId: string | null = null;
  readonly #channels = new Map<string, Channel>();
  #reconnectAttempts = 0;
  #closedByUser = false;
  #connectPromise: Promise<string> | null = null;
  #connectResolve: ((id: string) => void) | null = null;
  #connectReject: ((err: Error) => void) | null = null;

  constructor(options: SonarOptions = {}) {
    this.options = options;
  }

  /** The connection id for `X-Socket-ID` / `to_others()`. */
  get socketId(): string | null {
    return this.#socketId;
  }

  /** Connect and resolve with the `socket_id` once established. */
  connect(): Promise<string> {
    if (this.#socket && this.#socketId) {
      return Promise.resolve(this.#socketId);
    }
    if (this.#connectPromise) return this.#connectPromise;

    this.#closedByUser = false;
    this.#connectPromise = new Promise<string>((resolve, reject) => {
      this.#connectResolve = resolve;
      this.#connectReject = reject;
    });

    const url = deriveWsUrl(this.options);
    const socket = new WebSocket(url);
    this.#socket = socket;

    socket.onmessage = (message) => {
      this.#onMessage(String(message.data));
    };
    socket.onerror = () => {
      // onclose handles reconnect / reject
    };
    socket.onclose = () => {
      this.#socket = null;
      const wasConnected = this.#socketId !== null;
      this.#socketId = null;
      if (!wasConnected && this.#connectReject) {
        this.#connectReject(new Error("@almasix/sonar: connection closed before established"));
        this.#clearConnectWaiters();
      }
      if (!this.#closedByUser && (this.options.reconnect ?? true)) {
        this.#scheduleReconnect();
      }
    };

    return this.#connectPromise;
  }

  disconnect(): void {
    this.#closedByUser = true;
    this.#channels.clear();
    this.#socket?.close();
    this.#socket = null;
    this.#socketId = null;
    this.#clearConnectWaiters();
  }

  /** Subscribe to a public channel. */
  channel(name: string): Channel {
    return this.#subscribe(
      name,
      () => new Channel(name, (frame) => this.#send(frame), () => this.leave(name)),
    );
  }

  /**
   * Subscribe to a private channel (`private-` prefix added if missing).
   * Quoted because `private` is a TypeScript keyword.
   */
  privateChannel(name: string): PrivateChannel {
    const full = name.startsWith("private-") ? name : `private-${name}`;
    return this.#subscribe(
      full,
      () => new PrivateChannel(full, (frame) => this.#send(frame), () => this.leave(full)),
      true,
    ) as PrivateChannel;
  }

  /** Echo-style alias for {@link privateChannel}. */
  get private(): (name: string) => PrivateChannel {
    return (name: string) => this.privateChannel(name);
  }

  /** Subscribe to a presence channel (`presence-` prefix added if missing). */
  join(name: string): PresenceChannel {
    const full = name.startsWith("presence-") ? name : `presence-${name}`;
    return this.#subscribe(
      full,
      () => new PresenceChannel(full, (frame) => this.#send(frame), () => this.leave(full)),
      true,
    ) as PresenceChannel;
  }

  leave(name: string): void {
    const full = this.#channels.has(name)
      ? name
      : this.#channels.has(`private-${name}`)
        ? `private-${name}`
        : this.#channels.has(`presence-${name}`)
          ? `presence-${name}`
          : name;
    if (!this.#channels.has(full)) return;
    this.#send({ event: "unsubscribe", data: { channel: full } });
    this.#channels.delete(full);
  }

  leaveAllChannels(): void {
    for (const name of [...this.#channels.keys()]) {
      this.leave(name);
    }
  }

  /** Header value for HTTP requests so `to_others()` can exclude this client. */
  socketIdHeader(): Record<string, string> {
    return this.#socketId ? { "X-Socket-ID": this.#socketId } : {};
  }

  #subscribe(name: string, factory: () => Channel, needsAuth = false): Channel {
    const existing = this.#channels.get(name);
    if (existing) return existing;

    const channel = factory();
    this.#channels.set(name, channel);

    void this.#ensureConnected().then(async (socketId) => {
      let auth: string | undefined;
      let channelData: string | undefined;
      if (needsAuth) {
        const response = await this.#authorize(socketId, name);
        auth = response.auth;
        channelData = response.channel_data;
      }
      const data: Record<string, unknown> = { channel: name };
      if (auth) data.auth = auth;
      if (channelData) data.channel_data = channelData;
      this.#send({ event: "subscribe", data });
    });

    return channel;
  }

  async #ensureConnected(): Promise<string> {
    if (this.#socketId) return this.#socketId;
    return this.connect();
  }

  async #authorize(socketId: string, channel: string): Promise<AuthResponse> {
    const url = deriveAuthUrl(this.options);
    const body = new URLSearchParams({
      socket_id: socketId,
      channel_name: channel,
      ...(this.options.auth?.params ?? {}),
    });
    const response = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
        ...(this.options.auth?.headers ?? {}),
      },
      body,
    });
    if (!response.ok) {
      throw new Error(`@almasix/sonar: auth failed for [${channel}] (${response.status})`);
    }
    return (await response.json()) as AuthResponse;
  }

  #send(frame: Record<string, unknown>): void {
    if (!this.#socket || this.#socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.#socket.send(JSON.stringify(frame));
  }

  #onMessage(raw: string): void {
    let frame: SonarFrame;
    try {
      frame = JSON.parse(raw) as SonarFrame;
    } catch {
      return;
    }
    if (!frame || typeof frame.event !== "string") return;

    const event = frame.event.startsWith("pusher:")
      ? `almasix:${frame.event.slice("pusher:".length)}`
      : frame.event;

    if (event === "almasix:connection_established") {
      const data = frame.data as { socket_id?: string } | string | undefined;
      const parsed =
        typeof data === "string"
          ? (JSON.parse(data) as { socket_id?: string })
          : data && typeof data === "object"
            ? data
            : {};
      this.#socketId = String(parsed.socket_id ?? "");
      this.#reconnectAttempts = 0;
      if (this.#connectResolve && this.#socketId) {
        this.#connectResolve(this.#socketId);
        this.#clearConnectWaiters();
      }
      return;
    }

    if (event === "almasix:pong") {
      return;
    }

    if (frame.channel) {
      this.#channels.get(frame.channel)?.handle({ ...frame, event });
      return;
    }

    if (event === "almasix:error") {
      for (const channel of this.#channels.values()) {
        channel.handle({ ...frame, event });
      }
    }
  }

  #scheduleReconnect(): void {
    const max = this.options.maxReconnectAttempts ?? Number.POSITIVE_INFINITY;
    if (this.#reconnectAttempts >= max) return;
    const delay = (this.options.reconnectDelay ?? 1000) * (this.#reconnectAttempts + 1);
    this.#reconnectAttempts += 1;
    setTimeout(() => {
      if (this.#closedByUser) return;
      this.#connectPromise = null;
      const names = [...this.#channels.keys()];
      void this.connect().then(() => {
        for (const name of names) {
          if (!this.#channels.has(name)) continue;
          this.#channels.delete(name);
          if (name.startsWith("presence-")) this.join(name.replace(/^presence-/, ""));
          else if (name.startsWith("private-")) this.privateChannel(name.replace(/^private-/, ""));
          else this.channel(name);
        }
      });
    }, delay);
  }

  #clearConnectWaiters(): void {
    this.#connectPromise = null;
    this.#connectResolve = null;
    this.#connectReject = null;
  }
}

export default Sonar;
