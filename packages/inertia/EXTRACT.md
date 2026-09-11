# Extract checklist — almasix-dev/inertia

Until extract, `packages/inertia` is **force-included** in the `almasix` wheel
(and path-installed by `almasix new` from a monorepo checkout) so SPA kits work
without a separate PyPI distribution.

When cutting `almasix-dev/inertia` from this monorepo tree:

1. Copy `packages/inertia/` to the new repo root (adjust hatch paths).
2. Depend on published `almasix` + `httpx` (SSR HTTP client).
3. CI: ruff + pytest; publish to PyPI on tag; set `almasix[inertia]` to
   `almasix-inertia>=…` and stop force-including the package in the core wheel.
4. Keep the Node SSR stub under `ssr/server.js` as a documented starting point.
5. Preserve lazy / optional / defer / once / merge props and subpath-aware page `url` (via `url()`).
6. Remove in-tree `packages/inertia` only after Progress uses the PyPI extra and smoke stays green.
7. Drop the installer monorepo path-install of `packages/inertia` once the extra resolves from PyPI.
