import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default defineConfig({
  plugins: [sveltekit()],
  resolve: {
    conditions: ['browser']
  },
  server: {
    proxy: {
      '/api': { target: 'http://observatory.local:8000', changeOrigin: true },
      '/ws':  { target: 'ws://observatory.local:8000', ws: true, changeOrigin: true }
    }
  },
  // @ts-expect-error vitest extends vite config with test key
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.test.ts', 'src/**/*.test.ts'],
    setupFiles: ['./tests/unit/setup.ts']
  }
});
