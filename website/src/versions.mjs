/**
 * Documentation version switcher — majors + main only.
 *
 * Majors (`0.x`, later `1.x`, …) are the published lines. **Latest** is always
 * the newest major — never `main`. `main` is the unreleased tip and is opt-in.
 *
 * Until parallel content trees exist, non-latest selections use `?docsVersion=`.
 * Static builds must sync the switcher/banner from the live URL in the browser.
 */

/** @typedef {{ slug: string, label: string, kind: 'unreleased' | 'major' }} DocsVersion */

/** @type {DocsVersion[]} — latest major first; `main` last (never default). */
export const DOCS_VERSIONS = [
	{ slug: '0.x', label: '0.x', kind: 'major' },
	{ slug: 'main', label: 'main', kind: 'unreleased' },
];

/** Newest published major — the default docs line. Never `main`. */
export const LATEST_VERSION = '0.x';

export const DOCS_VERSION_QUERY = 'docsVersion';

/** @param {string} slug */
export function isKnownVersion(slug) {
	return DOCS_VERSIONS.some((version) => version.slug === slug);
}

/**
 * @param {URL | string} url
 * @returns {string}
 */
export function versionFromUrl(url) {
	const parsed = typeof url === 'string' ? new URL(url, 'https://example.invalid') : url;
	const fromQuery = parsed.searchParams.get(DOCS_VERSION_QUERY);
	if (fromQuery && isKnownVersion(fromQuery)) {
		return fromQuery;
	}
	// Path prefix: /almasix/0.x/installation/ or /almasix/main/… → that slug
	const parts = parsed.pathname.split('/').filter(Boolean);
	const candidates = parts[0] === 'almasix' ? parts.slice(1) : parts;
	const head = candidates[0];
	if (head && isKnownVersion(head)) {
		return head;
	}
	return LATEST_VERSION;
}

/**
 * @param {string} base  site base ending with /
 * @param {string} slug
 * @param {string} [pathname]
 * @param {string} [search]
 */
export function hrefForVersion(base, slug, pathname = '/', search = '') {
	const normalizedBase = base.endsWith('/') ? base : `${base}/`;
	const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
	if (slug === LATEST_VERSION) {
		params.delete(DOCS_VERSION_QUERY);
	} else {
		params.set(DOCS_VERSION_QUERY, slug);
	}
	const query = params.toString();
	const path = pathname.startsWith(normalizedBase)
		? pathname
		: `${normalizedBase}${pathname.replace(/^\//, '')}`;
	return query ? `${path}?${query}` : path;
}
