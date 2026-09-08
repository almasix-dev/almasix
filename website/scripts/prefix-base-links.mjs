/**
 * Prefix root-absolute links in the built HTML with the site's base path.
 *
 * The docs are authored with links like `/queues/`. Starlight rewrites its own
 * navigation and assets for `base`, but leaves author-written Markdown links
 * alone, so without this pass 183 cross-references 404 in production.
 *
 * This runs after the build rather than as a rehype plugin because Astro 7's
 * default Markdown processor does not accept remark/rehype plugins; restoring
 * the unified processor would change how all 54 pages render, which is a large
 * blast radius for a fix that only ever touches href/src attributes.
 *
 * Keeping it out of the content means the docs stay deploy-path agnostic: point
 * the site at a root domain and only `base` here and in astro.config.mjs change.
 */

import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist", import.meta.url));
const BASE = "/almasix";

const ATTR = /(href|src)="(\/[^"]*)"/g;

async function* htmlFiles(dir) {
	for (const entry of await readdir(dir, { withFileTypes: true })) {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) yield* htmlFiles(path);
		else if (entry.name.endsWith(".html")) yield path;
	}
}

let touchedFiles = 0;
let rewritten = 0;

for await (const file of htmlFiles(DIST)) {
	const before = await readFile(file, "utf8");
	let count = 0;

	const after = before.replace(ATTR, (whole, attr, url) => {
		// Leave protocol-relative URLs and anything already based alone.
		if (url.startsWith("//") || url === BASE || url.startsWith(`${BASE}/`)) {
			return whole;
		}
		count += 1;
		return `${attr}="${BASE}${url}"`;
	});

	if (count > 0) {
		await writeFile(file, after);
		touchedFiles += 1;
		rewritten += count;
	}
}

console.log(`base-links: prefixed ${rewritten} link(s) across ${touchedFiles} file(s)`);
