import { defineMiddleware } from 'astro:middleware';

/**
 * Prefix author-written links with the site's base path.
 *
 * The docs are authored with root-absolute links like `/queues/`. Starlight
 * bases its own navigation and assets, but leaves Markdown links alone, so
 * without this pass every cross-reference points outside the deployed subpath.
 *
 * This runs as middleware rather than as a post-build pass so that `astro dev`,
 * `astro preview` and the deployed site all serve identical links. The dev
 * server also answers unbased URLs, which hid the problem locally while
 * `preview` and production returned 404.
 *
 * Only `<a href>` is rewritten. Every other root-absolute URL Astro emits is
 * already based, and rewriting Vite's dev-only asset URLs would break HMR.
 */

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const ANCHOR = /(<a\b[^>]*?\shref=")(\/[^"]*)(")/g;

export const onRequest = defineMiddleware(async (_context, next) => {
	const response = await next();

	// Deployed at a domain root: nothing to prefix.
	if (!BASE) return response;
	if (!response.headers.get('content-type')?.includes('text/html')) return response;

	const html = await response.text();
	const based = html.replace(ANCHOR, (whole, open: string, url: string, close: string) =>
		// Leave protocol-relative URLs and anything already based alone.
		url.startsWith('//') || url === BASE || url.startsWith(`${BASE}/`)
			? whole
			: `${open}${BASE}${url}${close}`,
	);

	const headers = new Headers(response.headers);
	headers.delete('content-length'); // the body length just changed

	return new Response(based, {
		status: response.status,
		statusText: response.statusText,
		headers,
	});
});
