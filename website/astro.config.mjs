// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://coolsam726.github.io/avalon',
	// Astro's audit toolbar currently throws (M_ID) on these pages; docs don't need it.
	devToolbar: { enabled: false },
	integrations: [
		starlight({
			title: 'Avalon',
			description:
				'The elegant Python web framework with Articulate, Caliburn, and the Grail CLI.',
			logo: {
				src: './src/assets/avalon-banner.svg',
				alt: 'Avalon',
				replacesTitle: true,
			},
			favicon: '/favicon.svg',
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/coolsam726/avalon',
				},
			],
			editLink: {
				baseUrl: 'https://github.com/coolsam726/avalon/edit/main/website/',
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
					// After Starlight restores session open-state, keep only the
					// group that contains the current page expanded.
					tag: 'script',
					content: `
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('starlight__sidebar');
  if (!sidebar) return;
  for (const details of sidebar.querySelectorAll('details')) {
    details.open = Boolean(details.querySelector('[aria-current="page"]'));
  }
});
`,
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
						{ label: 'Views', slug: 'views' },
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
						{ label: 'Grail Console', slug: 'console' },
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
					],
				},
				{
					label: 'Security',
					collapsed: true,
					items: [
						{ label: 'Authentication', slug: 'authentication' },
						{ label: 'Hashing', slug: 'hashing' },
						{ label: 'Passwords', slug: 'passwords' },
						{ label: 'Encryption', slug: 'encryption' },
					],
				},
				{
					label: 'Database',
					collapsed: true,
					items: [
						{ label: 'Getting Started', slug: 'database' },
						{ label: 'Query Builder', slug: 'database/queries' },
						{ label: 'Pagination', slug: 'database/pagination' },
						{ label: 'Migrations', slug: 'database/migrations' },
						{ label: 'Seeding', slug: 'database/seeding' },
					],
				},
				{
					label: 'Caliburn',
					collapsed: true,
					items: [
						{ label: 'Getting Started', slug: 'caliburn' },
						{ label: 'Rendering Views', slug: 'caliburn/rendering' },
						{ label: 'Layouts & Inheritance', slug: 'caliburn/layouts' },
						{ label: 'Components & Slots', slug: 'caliburn/components' },
						{ label: 'Control Structures', slug: 'caliburn/control' },
						{ label: 'Including Subviews', slug: 'caliburn/includes' },
						{ label: 'Stacks & Directives', slug: 'caliburn/stacks' },
					],
				},
				{
					label: 'Articulate',
					collapsed: true,
					items: [
						{ label: 'Getting Started', slug: 'articulate' },
						{ label: 'Relationships', slug: 'articulate/relationships' },
						{ label: 'Collections', slug: 'articulate/collections' },
						{ label: 'Soft Deletes & Events', slug: 'articulate/events' },
					],
				},
			],
		}),
	],
});
