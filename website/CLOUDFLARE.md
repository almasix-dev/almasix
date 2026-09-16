# Cloudflare — docs.almasix.com

Framework Starlight docs live in this `website/` directory and deploy as
**Worker static assets** (same pattern as [almasix.com](https://almasix.com)).

## Wrangler

[`wrangler.jsonc`](./wrangler.jsonc) serves `./dist` (Astro build output). There is no Worker `main` script.

## CI

[`.github/workflows/docs.yml`](../.github/workflows/docs.yml) builds on every PR touching `website/`, and on `main` runs `wrangler deploy`.

Repository secrets (Settings → Secrets → Actions):

| Secret | Purpose |
|--------|---------|
| `CLOUDFLARE_API_TOKEN` | Token with Workers Scripts Edit + Account read |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id |

## Cutover from GitHub Pages

1. Ensure CI secrets above are set on `almasix-dev/almasix`.
2. Merge a PR that includes this Wrangler config; confirm the deploy job succeeds.
3. In Cloudflare → Workers & Pages → `almasix-docs` → **Custom domains** → add **`docs.almasix.com`** (accept DNS).
4. Wait until the domain is **Active** + cert issued.
5. Remove the old DNS record: `docs` CNAME → `almasix-dev.github.io` (DNS-only / grey cloud) if Cloudflare did not replace it.
6. GitHub → Settings → Pages → disable or clear the custom domain so GitHub stops serving the old site.
7. Verify:

```bash
curl -I https://docs.almasix.com/
# expect 200 from Cloudflare, not GitHub Pages
```

## Local

```bash
npm ci
npm run build
npx wrangler deploy   # needs Cloudflare auth
```

## Package docs

First-party package docs (Conduit, Inertia, Permission) use the same Wrangler
assets pattern in each package repo’s `website/`, on hosts like
`conduit.almasix.com`. See those repos and the hub [`CLOUDFLARE.md`](https://github.com/almasix-dev/almasix-website/blob/main/CLOUDFLARE.md).

## Package path redirects (zone Redirect Rules)

After package docs hosts are live, add zone Redirect Rules so old framework paths keep working:

| When (filter) | Then (301) |
|---------------|------------|
| `http.host eq "docs.almasix.com" and starts_with(http.request.uri.path, "/inertia")` | `concat("https://inertia.almasix.com", http.request.uri.path)` — or map `/inertia` → `/` and `/inertia/` → `/` |
| Same for `/conduit` → `https://conduit.almasix.com` | Prefer mapping the single stub path `/conduit/` → `https://conduit.almasix.com/` |

Simpler first cut (recommended):

- `docs.almasix.com/inertia` and `/inertia/` → `https://inertia.almasix.com/`
- `docs.almasix.com/conduit` and `/conduit/` → `https://conduit.almasix.com/`

Leave short stubs in Starlight until search indexes refresh; redirects are optional once stubs are enough.
