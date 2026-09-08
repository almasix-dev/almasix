// @ts-check
import { readFileSync } from 'node:fs';

import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// GitHub Pages serves this repo's site from a subpath, not the domain root.
// Markdown-authored links like `/queues/` are prefixed with this while
// rendering, by src/middleware.ts.
const base = '/almasix';

// https://astro.build/config
export default defineConfig({
	site: 'https://almasix-dev.github.io/almasix',
	base,
	// Astro's audit toolbar currently throws (M_ID) on these pages; docs don't need it.
	devToolbar: { enabled: false },
	integrations: [
		starlight({
			title: 'Almasix',
			description:
				'The elegant Python web framework with Articulate, Prism, and the Smith CLI.',
			logo: {
				src: './src/assets/almasix-banner.svg',
				alt: 'Almasix',
				replacesTitle: true,
			},
			favicon: '/favicon.svg',
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/almasix-dev/almasix',
				},
			],
			editLink: {
				baseUrl: 'https://github.com/almasix-dev/almasix/edit/main/website/',
			},
			customCss: ['./src/styles/custom.css'],
			expressiveCode: {
				themes: ['one-dark-pro'],
				useStarlightDarkModeSwitch: false,
				useStarlightUiThemeColors: false,
				// Avoid hashed /_astro/ec.*.css 404s across pages in Vite/dev
				// (different pages were emitting different hashes; only one existed).
				emitExternalStylesheet: false,
				styleOverrides: {
					borderRadius: '0.85rem',
					borderWidth: '1px',
					codeFontFamily: "'JetBrains Mono', ui-monospace, monospace",
					codeFontSize: '0.9rem',
					codeBackground: '#282c34',
					codeForeground: '#abb2bf',
					frames: {
						shadowColor: 'rgba(0, 0, 0, 0.4)',
						editorBackground: '#282c34',
						terminalBackground: '#282c34',
					},
				},
			},
			head: [
				{
					tag: 'link',
					attrs: {
						rel: 'preconnect',
						href: 'https://fonts.googleapis.com',
					},
				},
				{
					tag: 'link',
					attrs: {
						rel: 'preconnect',
						href: 'https://fonts.gstatic.com',
						crossorigin: true,
					},
				},
				{
					// Sidebar accordion: one group open at a time. Kept in its own
					// file so it stays readable, and inlined to avoid a round trip.
					tag: 'script',
					content: readFileSync('./src/scripts/sidebar-accordion.js', 'utf8'),
				},
			],
			sidebar: [
				{
					label: 'Getting Started',
					collapsed: true,
					items: [
						{ label: 'Installation', slug: 'installation' },
						{ label: 'Directory Structure', slug: 'structure' },
					],
				},
				{
					label: 'The Basics',
					collapsed: true,
					items: [
						{ label: 'Routing', slug: 'routing' },
						{ label: 'Middleware', slug: 'middleware' },
						{ label: 'CSRF Protection', slug: 'csrf' },
						{ label: 'Controllers', slug: 'controllers' },
						{ label: 'Requests', slug: 'requests' },
						{ label: 'Responses', slug: 'responses' },
						{ label: 'Views (Prism)', slug: 'views' },
						{ label: 'Asset Bundling', slug: 'asset-bundling' },
						{ label: 'URL Generation', slug: 'urls' },
						{ label: 'Session', slug: 'session' },
						{ label: 'Validation', slug: 'validation' },
						{ label: 'Error Handling', slug: 'errors' },
						{ label: 'Logging', slug: 'logging' },
					],
				},
				{
					label: 'Digging Deeper',
					collapsed: true,
					items: [
						{ label: 'Smith Console', slug: 'console' },
						{ label: 'Prompts', slug: 'prompts' },
						{ label: 'Task Scheduling', slug: 'scheduling' },
						{ label: 'File Storage', slug: 'filesystem' },
						{ label: 'Queues', slug: 'queues' },
						{ label: 'Mail', slug: 'mail' },
						{ label: 'Notifications', slug: 'notifications' },
						{ label: 'Collections', slug: 'collections' },
						{ label: 'Helpers', slug: 'helpers' },
						{ label: 'Strings', slug: 'strings' },
						{ label: 'Cache', slug: 'cache' },
						{ label: 'Redis', slug: 'redis' },
						{ label: 'Events', slug: 'events' },
						{ label: 'HTTP Client', slug: 'http-client' },
						{ label: 'Processes', slug: 'processes' },
					],
				},
				{
					label: 'Security',
					collapsed: true,
					items: [
						{ label: 'Authentication', slug: 'authentication' },
						{ label: 'Authorization', slug: 'authorization' },
						{ label: 'Hashing', slug: 'hashing' },
						{ label: 'Passwords', slug: 'passwords' },
						{ label: 'Encryption', slug: 'encryption' },
					],
				},
				{
					label: 'Database',
					collapsed: true,
					items: [
						{ label: 'Database: Getting Started', slug: 'database' },
						{ label: 'Query Builder', slug: 'database/queries' },
						{ label: 'Pagination', slug: 'database/pagination' },
						{ label: 'Migrations', slug: 'database/migrations' },
						{ label: 'Seeding', slug: 'database/seeding' },
					],
				},
				{
					label: 'Articulate ORM',
					collapsed: true,
					items: [
						{ label: 'Articulate: Getting Started', slug: 'articulate' },
						{ label: 'Relationships', slug: 'articulate/relationships' },
						{ label: 'Mutators & Casts', slug: 'articulate/casts' },
						{ label: 'Serialization', slug: 'articulate/serialization' },
						{ label: 'Collections', slug: 'articulate/collections' },
						{ label: 'Soft Deletes & Events', slug: 'articulate/events' },
					],
				},
				{
					label: 'Prism View Engine',
					collapsed: true,
					items: [
						{ label: 'Prism: Getting Started', slug: 'prism' },
						{ label: 'Rendering Views', slug: 'prism/rendering' },
						{ label: 'Layouts & Inheritance', slug: 'prism/layouts' },
						{ label: 'Components & Slots', slug: 'prism/components' },
						{ label: 'Control Structures', slug: 'prism/control' },
						{ label: 'Including Subviews', slug: 'prism/includes' },
						{ label: 'Stacks & Directives', slug: 'prism/stacks' },
					],
				},
			],
		}),
	],
});
