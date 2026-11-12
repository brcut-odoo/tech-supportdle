import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// GitHub Pages project sites live under /<repo>/; CI sets BASE_PATH (e.g. "/tech-supportdle").
// Leave it empty for local dev or a host serving from the domain root.
const base = (process.env.BASE_PATH ?? '').replace(/\/+$/, '') as '' | `/${string}`;

export default defineConfig({
	plugins: [
		sveltekit({
			adapter: adapter({ pages: 'build', assets: 'build', fallback: undefined, strict: true }),
			paths: { base, relative: true }
		})
	],
	test: { include: ['tests/**/*.test.ts'] }
});
