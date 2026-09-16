import { defineMiddleware } from 'astro:middleware';

/**
 * Prefix author-written links with the site's base path when it is not `/`.
 *
 * Docs are authored with root-absolute links like `/queues/`. At
 * docs.almasix.com the base is `/`, so this is a no-op. If the site is ever
 * deployed under a subpath again, Starlight bases its own navigation and
 * assets but leaves Markdown links alone — this pass keeps cross-references
 * on the same origin.
 *
 * Runs as middleware (not a post-build pass) so `astro dev`, `astro preview`,
 * and production agree. Only `<a href>` is rewritten; rewriting Vite's
 * dev-only asset URLs would break HMR.
 */

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const ANCHOR = /(<a\b[^>]*?\shref=")(\/[^"]*)(")/g;

export const onRequest = defineMiddleware(async (_context, next) => {
	const response = await next();

	// Domain root (docs.almasix.com): nothing to prefix.
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
