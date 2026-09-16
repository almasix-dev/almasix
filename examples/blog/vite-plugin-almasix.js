import { resolve } from "node:path";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";

// Prism's `@vite` directive reads public/hot: while that file exists, tags
// point at the dev server, and once it is gone they point at the manifest in
// public/build. Laravel gets this from an npm package; keeping it here means
// the stack has no Almasix dependency on the Node side at all.
export default function almasix() {
  const hot = () => resolve("public/hot");

  return {
    name: "almasix",

    configureServer(server) {
      const write = () => {
        const address = server.httpServer?.address();
        const port = typeof address === "object" && address ? address.port : 5173;
        mkdirSync(resolve("public"), { recursive: true });
        writeFileSync(hot(), `http://127.0.0.1:${port}`);
      };
      const clean = () => rmSync(hot(), { force: true });

      server.httpServer?.once("listening", write);
      process.on("exit", clean);
      for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
        process.on(signal, () => {
          clean();
          process.exit();
        });
      }
    },

    buildStart() {
      rmSync(hot(), { force: true });
    },
  };
}
