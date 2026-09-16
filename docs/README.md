# Contributor docs

| Audience | Where | Notes |
|----------|--------|-------|
| **Published how-tos** | [`almasix-dev/almasix-docs`](https://github.com/almasix-dev/almasix-docs) | Astro Starlight at [docs.almasix.com](https://docs.almasix.com/) |
| **Contributor contracts** | this `docs/` tree | `PLAN.md`, `SMOKE.md`, feature notes |

```bash
git clone git@github.com:almasix-dev/almasix-docs.git
cd almasix-docs && npm ci && npm run dev
```

CI checks out `almasix-docs` into `website/` so smoke tests that read
`website/src/content/docs` keep working.
