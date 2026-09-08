# Examples

Living sample apps that grow with Almasix milestones.

| App | Purpose |
| --- | --- |
| [`progress/`](progress/) | **Milestone tracker** — exercise M0/M1 now; extend as M2+ lands |
| `api/` | Canonical API example (M3 gate) — not yet |
| `web/` | Prism-backed web example (after M5) — not yet |

## Quick start (progress)

```bash
cd /path/to/almasix
source .venv/bin/activate
pip install -e .
cd examples/progress && pip install -e .
python smith serve
```

Open `http://127.0.0.1:3000/progress` for the milestone board (or the next free port in 3000–3099).
