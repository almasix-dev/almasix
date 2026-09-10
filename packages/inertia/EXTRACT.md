# Extract checklist — almasix-dev/inertia

When cutting `almasix-dev/inertia` from this monorepo tree:

1. Copy `packages/inertia/` to the new repo root (adjust hatch paths).
2. Depend on published `almasix` + `httpx` (SSR HTTP client).
3. CI: ruff + pytest; publish to PyPI on tag; keep `almasix[inertia]` extra pointing at the published package.
4. Keep the Node SSR stub under `ssr/server.js` as a documented starting point.
5. Preserve lazy / optional / defer / once / merge props and subpath-aware page `url` (via `url()`).
6. Remove in-tree `packages/inertia` only after Progress uses the PyPI extra and smoke stays green.
