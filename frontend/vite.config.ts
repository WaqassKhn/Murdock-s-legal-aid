import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  define: {
    __TEMPORARY_SESSION__: JSON.stringify(
      process.env.VERCEL === '1' || process.env.LEGALLENS_TEMPORARY_SESSION === 'true',
    ),
  },
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
        // Preserve the browser origin for the same-origin session endpoint.
        changeOrigin: false,
      },
    },
  },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', include: ['src/**/*.test.tsx'] },
});
