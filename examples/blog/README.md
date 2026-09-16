# Blog

Almasix application generated with `almasix new blog`.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python smith migrate
python smith serve
```

Open http://127.0.0.1:3000

`almasix new --install` (or answering Yes) creates `.venv` and runs
`pip`/`uv install -e .` for you. Prefer `python smith …` from the app root —
it always works. After install, bare `smith …` is also on that virtualenv's PATH.

## Database

This application talks to **SQLite**. Connection details live in `.env`;
`config/database.py` names every engine Almasix speaks. The default migrations
create the tables auth, sessions, cache, and the queue need:

```bash
python smith migrate
python smith migrate:status
```

## Frontend (Vite + Tailwind CSS)

```bash
npm install
npm run dev      # Vite HMR during development
npm run build    # emit into public/build
```


## SPA kit (Inertia)

This application was scaffolded with the **SPA** starter kit — session auth over
**almasix-inertia** with the official `@inertiajs/*` client.

Product surface (Forge):
- Brand landing → Dashboard, Notifications, Settings (Profile / Password / 2FA / Appearance), Teams
- Light + dark (`class="dark"` on `<html>`), teal `#0d9488` + chartreuse accent `#e8ff47`
- Fonts: Fraunces (display) + DM Sans (UI)

Dev:
```bash
npm install && npm run dev
uv run smith serve   # or: smith serve
```

Ensure `almasix-inertia` is installed (see `pyproject.toml`).

Create more apps with `almasix new`.
