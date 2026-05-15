import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      'pdfjs-dist': resolve(__dirname, 'node_modules/pdfjs-dist'),
    },
  },
  server: {
    host: '0.0.0.0', // 监听所有网卡，允许外部访问
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:28000', // 后端在同一服务器
        changeOrigin: true,
      },
      '/openwps': {
        target: 'http://127.0.0.1:28000',
        changeOrigin: true,
        // SSE 长连接需要无限超时
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
