// @ts-check
import { defineConfig } from 'astro/config';

// GitHub Pages: the deploy workflow (.github/workflows/pages.yml) passes --site and --base
// (https://<owner>.github.io/<repo>/), so nothing repo-specific is hardcoded here and
// `npm run dev` serves the page at http://localhost:4321/.
export default defineConfig({});
