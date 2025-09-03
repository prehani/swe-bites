import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import alpinejs from '@astrojs/alpinejs';
import playformInline from '@playform/inline';
import mdx from '@astrojs/mdx';

export default defineConfig({
  // site: can be set in production
  base: '/',
  output: 'static',
  integrations: [
    alpinejs(),
    playformInline({ Beasties: true }),
    mdx(),
  ],
  devToolbar: { enabled: false },
  vite: {
    plugins: [tailwindcss()],
  },
});
