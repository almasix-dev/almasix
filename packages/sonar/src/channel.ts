import type { EventCallback, PresenceMember, SonarFrame } from "./types.js";

type ListenerMap = Map<string, Set<EventCallback>>;

/** Normalize Sonar / optional Pusher-shaped system event names. */
export function normalizeEvent(event: string): string {
  if (event.startsWith("pusher:")) {
    return `almasix:${event.slice("pusher:".length)}`;
  }
  return event;
}

/**
 * A subscribed channel. Public channels need no auth; private / presence
 * subclasses POST `/broadcasting/auth` before sending `subscribe`.
 */
export class Channel {
  readonly name: string;
  protected readonly listeners: ListenerMap = new Map();
  protected isSubscribed = false;
  protected members: PresenceMember[] = [];

  constructor(
    name: string,
    protected readonly sendFrame: (frame: Record<string, unknown>) => void,
    protected readonly leave: () => void,
  ) {
    this.name = name;
  }

  /** Register for a broadcast event on this channel. */
  listen(event: string, callback: EventCallback): this {
    const key = event.startsWith(".") ? event.slice(1) : event;
    let set = this.listeners.get(key);
    if (!set) {
      set = new Set();
      this.listeners.set(key, set);
    }
    set.add(callback);
    return this;
  }

  stopListening(event?: string, callback?: EventCallback): this {
    if (event === undefined) {
      this.listeners.clear();
      return this;
    }
    const key = event.startsWith(".") ? event.slice(1) : event;
    if (!callback) {
      this.listeners.delete(key);
      return this;
    }
    this.listeners.get(key)?.delete(callback);
    return this;
  }

  /** Fires once subscription succeeds (or immediately if already subscribed). */
  subscribed(callback: () => void): this {
    if (this.isSubscribed) {
      callback();
      return this;
    }
    this.listen("almasix:subscription_succeeded", () => callback());
    return this;
  }

  error(callback: EventCallback): this {
    return this.listen("almasix:error", callback);
  }

  /** Whisper a `client-*` event (requires `client_events` on the server). */
  whisper(event: string, data: unknown = {}): this {
    const name = event.startsWith("client-") ? event : `client-${event}`;
    this.sendFrame({ event: name, channel: this.name, data });
    return this;
  }

  unsubscribe(): void {
    this.leave();
  }

  /** @internal */
  handle(frame: SonarFrame): void {
    const event = normalizeEvent(frame.event);
    if (event === "almasix:subscription_succeeded") {
      this.isSubscribed = true;
      const data = frame.data;
      if (data && typeof data === "object" && Array.isArray((data as { members?: unknown }).members)) {
        this.members = (data as { members: PresenceMember[] }).members;
      }
    }
    this.emit(event, frame.data, { ...frame, event });
    // Also notify bare event names without the almasix: prefix for system ones.
    if (event.startsWith("almasix:")) {
      this.emit(event.slice("almasix:".length), frame.data, { ...frame, event });
    }
  }

  protected emit(event: string, data: unknown, frame: SonarFrame): void {
    const set = this.listeners.get(event);
    if (!set) return;
    for (const cb of [...set]) {
      cb(data, frame);
    }
  }
}

export class PrivateChannel extends Channel {}

export class PresenceChannel extends PrivateChannel {
  here(callback: (members: PresenceMember[]) => void): this {
    this.subscribed(() => callback([...this.members]));
    return this;
  }

  joining(callback: (member: PresenceMember) => void): this {
    return this.listen("almasix:member_added", (data) => {
      callback(data as PresenceMember);
    });
  }

  leaving(callback: (member: PresenceMember) => void): this {
    return this.listen("almasix:member_removed", (data) => {
      callback(data as PresenceMember);
    });
  }
}
