/**
 * Sidebar accordion — at most one group expanded at a time.
 *
 * Starlight renders sidebar groups as native <details> and restores their open
 * state across navigations, which can leave several expanded at once. On load
 * we keep only the group holding the current page; after that, opening a group
 * closes its siblings.
 *
 * Inlined into <head> by astro.config.mjs, so it must be self-contained.
 */
(() => {
	const SIDEBAR = '#starlight__sidebar';

	const groups = () => {
		const sidebar = document.querySelector(SIDEBAR);
		return sidebar ? Array.from(sidebar.querySelectorAll('details')) : [];
	};

	// After Starlight restores session state, show only the current page's group.
	document.addEventListener('DOMContentLoaded', () => {
		for (const details of groups()) {
			details.open = Boolean(details.querySelector('[aria-current="page"]'));
		}
	});

	// `toggle` does not bubble, so it has to be caught on the way down.
	document.addEventListener(
		'toggle',
		(event) => {
			const opened = event.target;
			if (!(opened instanceof HTMLDetailsElement) || !opened.open) return;
			if (!opened.closest(SIDEBAR)) return;

			for (const other of groups()) {
				// Nested groups: an ancestor must stay open to show its child.
				if (other === opened || other.contains(opened) || opened.contains(other)) {
					continue;
				}
				other.open = false;
			}
		},
		true,
	);
})();
