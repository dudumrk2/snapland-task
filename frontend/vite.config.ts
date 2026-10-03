/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: [
        'src/hooks/useDrawing.ts',
        'src/hooks/useWebSocket.ts',
        'src/services/map/LayerManager.ts',
        'src/services/websocket/WebSocketService.ts',
        'src/store/areasStore.ts',
        'src/store/collaborationStore.ts',
        'src/utils/areaCalculation.ts',
        'src/utils/escapeHtml.ts',
        'src/utils/geoUtils.ts',
      ],
      thresholds: {
        lines: 80,
      },
    },
  },
});
