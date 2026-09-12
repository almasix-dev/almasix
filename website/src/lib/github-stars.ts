/**
 * Fetch the public star count once per docs build.
 *
 * SocialIcons is rendered on every page; without memoization that means one
 * unauthenticated api.github.com hit per HTML file — enough to exhaust the
 * shared Actions IP quota and drop the badge in production while local builds
 * still succeed.
 */

let cached: string | null | undefined;

function formatStars(count: number): string {
	if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1).replace(/\.0$/, '')}m`;
	if (count >= 1_000) return `${(count / 1_000).toFixed(1).replace(/\.0$/, '')}k`;
	return String(count);
}

export async function githubStarsLabel(repoUrl: string): Promise<string | null> {
	if (cached !== undefined) return cached;

	const match = repoUrl.match(/github\.com\/([^/]+)\/([^/#?]+)/);
	if (!match) {
		cached = null;
		return cached;
	}

	const headers: Record<string, string> = {
		Accept: 'application/vnd.github+json',
		'User-Agent': 'almasix-docs',
	};
	const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
	if (token) {
		headers.Authorization = `Bearer ${token}`;
	}

	try {
		const res = await fetch(`https://api.github.com/repos/${match[1]}/${match[2]}`, { headers });
		if (!res.ok) {
			cached = null;
			return cached;
		}
		const data = (await res.json()) as { stargazers_count?: number };
		cached = typeof data.stargazers_count === 'number' ? formatStars(data.stargazers_count) : null;
	} catch {
		// Offline / rate-limited builds still show the icon alone.
		cached = null;
	}
	return cached;
}
