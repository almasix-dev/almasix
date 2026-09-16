# Cloudflare — docs.almasix.com

Framework Starlight docs live in this `website/` directory and deploy as
**Worker static assets** (same pattern as [almasix.com](https://almasix.com)).

## Wrangler

[`wrangler.jsonc`](./wrangler.jsonc) serves `./dist` (Astro build output). There is no Worker `main` script.

## CI vs deploy

GitHub Actions ([`.github/workflows/docs.yml`](../.github/workflows/docs.yml)) **builds only** — catches broken docs on PRs.

**Deploy** is Cloudflare **Workers Builds** connected to this repo (no API tokens in GitHub):

| Setting | Value |
|---------|--------|
| Root directory | `website/` |
| Build command | `npm ci && npm run build` |
| Deploy command | `npx wrangler deploy` |
| Node | `24` (or `22`) |

## Cutover from GitHub Pages

1. Connect Workers Builds to `almasix-dev/almasix` with the settings above (project name `almasix-docs`).
2. Merge a PR that includes `website/wrangler.jsonc`.
3. Custom domains → add **`docs.almasix.com`** (accept DNS).
4. Wait until **Active** + cert issued.
5. Remove the old DNS record: `docs` CNAME → `almasix-dev.github.io` (grey cloud) if still present.
6. GitHub → Settings → Pages → disable or clear the custom domain.
7. Verify:

```bash
curl -I https://docs.almasix.com/
# expect 200 from Cloudflare, not GitHub Pages
```

## Local

```bash
npm ci
npm run build
npx wrangler deploy   # needs Cloudflare auth (local only)
```

## Package docs

Conduit, Inertia, and Permission use the same Workers Builds recipe in each
package repo’s `website/`. See the hub
[`CLOUDFLARE.md`](https://github.com/almasix-dev/almasix-website/blob/main/CLOUDFLARE.md).

## Package path redirects (zone Redirect Rules)

Optional after package hosts are live:

- `docs.almasix.com/inertia` and `/inertia/` → `https://inertia.almasix.com/`
- `docs.almasix.com/conduit` and `/conduit/` → `https://conduit.almasix.com/`

Framework Digging Deeper pages are already stubs linking to those hosts.
