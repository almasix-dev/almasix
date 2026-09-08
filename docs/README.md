# Almasix documentation

| Layer | Path | Role |
| --- | --- | --- |
| **Published how-tos** | [`website/`](../website/) | Astro Starlight docs for application developers |
| Binding plan | [`PLAN.md`](PLAN.md) | Architecture, milestone contracts (framework contributors) |
| Gates | [`SMOKE.md`](SMOKE.md) | Smoke / regression / coverage exit criteria |

**Published docs** target people building apps with Almasix. Tone and organization follow Laravel’s documentation style (Getting Started → The Basics → Database → Articulate).

```bash
cd website && npm install && npm run dev
# or: make docs
```

Content: `website/src/content/docs/`. Theme: `website/src/styles/custom.css` (brand `#F1511B`, One Dark code blocks).
