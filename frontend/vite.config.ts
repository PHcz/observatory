import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/api': { target: 'http://observatory.local:8000', changeOrigin: true },
      '/ws':  { target: 'ws://observatory.local:8000', ws: true, changeOrigin: true }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.test.ts'],
    setupFiles: ['./tests/unit/setup.ts']
  }
});
