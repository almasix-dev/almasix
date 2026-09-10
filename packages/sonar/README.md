# `@almasix/sonar`

First-party browser client for **Sonar**, Almasix's native realtime websocket
server (`/broadcasting/socket`). Speaks the `almasix:*` frame protocol the
server uses today. **Does not require `pusher-js`.**

## Install

```bash
npm install @almasix/sonar
```

From this monorepo while developing:

```bash
cd packages/sonar && npm install && npm run build
```

## Quick start

Point `BROADCAST_CONNECTION` at `websocket` or the `sonar` alias, then:

```js
import Sonar from "@almasix/sonar";

const sonar = new Sonar({
  // defaults: same host as the page, path /broadcasting/socket
  // authEndpoint: "/broadcasting/auth",
});

await sonar.connect();

// Public
sonar.channel("announcements").listen("post.published", (data) => {
  console.log(data);
});

// Private — POSTs /broadcasting/auth with credentials/cookies
sonar.private(`authors.${name}`).listen("post.published", (data) => {
  console.log(data);
});

// Presence
sonar
  .join("rooms.lobby")
  .here((members) => console.log(members))
  .joining((member) => console.log("joined", member))
  .leaving((member) => console.log("left", member));

// Exclude this tab from broadcasts (server `to_others()`)
fetch("/posts", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    ...sonar.socketIdHeader(), // { "X-Socket-ID": "..." }
  },
  body: JSON.stringify({ title: "Hi" }),
  credentials: "include",
});
```

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `wsUrl` | derived | Full `ws://` / `wss://` URL |
| `host` / `port` / `path` / `scheme` | page location, `/broadcasting/socket` | URL pieces when `wsUrl` is unset |
| `forceTLS` | `false` | Prefer `wss` |
| `authEndpoint` | `/broadcasting/auth` | Private / presence auth |
| `auth.headers` / `auth.params` | — | Extra auth request fields |
| `reconnect` | `true` | Reconnect on close |

## Protocol

Compatible with Almasix M26 Sonar frames:

- server → `almasix:connection_established` `{ socket_id }`
- client → `subscribe` / `unsubscribe` / `ping` / `client-*`
- server → `almasix:subscription_succeeded`, `almasix:member_added` / `member_removed`, broadcasts as `{ event, channel, data }`

Optional: inbound `pusher:*` system names are normalized to `almasix:*` if a
relay ever speaks them; the default client always **sends** Sonar/`almasix` shapes.

## Alternatives

If you prefer a hosted bus, see the Broadcasting docs for **Pusher.js**,
**Ably**, and **Socket.IO** — those are supported alternatives, not the default.
