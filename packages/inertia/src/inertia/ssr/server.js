/**
 * Minimal Inertia SSR worker (Node). Official apps replace this with the
 * Vite-built SSR bundle; the HTTP contract matches Inertia's /render endpoint.
 *
 * POST /render  { component, props, url, version, ... } → { head: [], body: string }
 */
const http = require("http");

const PORT = process.env.INERTIA_SSR_PORT || 13714;

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  if (req.method !== "POST" || req.url !== "/render") {
    res.writeHead(404);
    res.end();
    return;
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  let page = {};
  try {
    page = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
  } catch (_) {
    res.writeHead(400);
    res.end("invalid json");
    return;
  }
  const component = page.component || "Unknown";
  const props = page.props || {};
  const body =
    `<div data-inertia-ssr="1" data-component="${component}">` +
    `<pre>${JSON.stringify(props)}</pre></div>`;
  const head = [`<title data-inertia>${component}</title>`];
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ head, body }));
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Inertia SSR listening on http://127.0.0.1:${PORT}`);
});
