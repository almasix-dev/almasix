/** Options for connecting to an Almasix Sonar websocket server. */
export type SonarOptions = {
  /**
   * Full WebSocket URL. When set, host / port / path / scheme are ignored.
   * Default derivation: `ws(s)://{host}:{port}{path}`.
   */
  wsUrl?: string;
  /** Hostname. Defaults to `window.location.hostname` in browsers. */
  host?: string;
  /** Port. Defaults to the page port (or 80/443). */
  port?: number | string;
  /** Socket path. Default `/broadcasting/socket`. */
  path?: string;
  /** `ws` or `wss`. Defaults from `window.location.protocol` / `forceTLS`. */
  scheme?: "ws" | "wss";
  /** Force `wss` when deriving the URL. */
  forceTLS?: boolean;
  /** Channel auth endpoint. Default `/broadcasting/auth`. */
  authEndpoint?: string;
  /** Extra headers / body fields on auth POSTs (cookies sent with credentials). */
  auth?: {
    headers?: Record<string, string>;
    params?: Record<string, string>;
  };
  /** Reconnect after close (default true). */
  reconnect?: boolean;
  /** Max reconnect attempts (default Infinity). */
  maxReconnectAttempts?: number;
  /** Base delay between reconnects in ms (default 1000). */
  reconnectDelay?: number;
};

export type SonarFrame = {
  event: string;
  channel?: string;
  data?: unknown;
};

export type EventCallback = (data: unknown, frame: SonarFrame) => void;

export type AuthResponse = {
  auth: string;
  channel_data?: string;
};

export type PresenceMember = {
  user_id: string | number;
  user_info?: Record<string, unknown>;
  [key: string]: unknown;
};
