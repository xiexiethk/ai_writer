import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/openwps/',
  server: {
    proxy: {
      // 仅把 API 与 SSE 路径转发给后端，HTML / JS / 资源由 vite 自己提供，
      // 否则 /openwps/ 会被后端的 dist/index.html 接管，导致 HMR 失效、改了代码不生效。
      '/openwps/api': {
        target: 'http://127.0.0.1:28000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:28000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 主包含 Mermaid 等重型库，其内部已通过动态 import() 做懒加载；
    // 这里只对稳定的顶层大依赖做拆分，阈值设高以避免 Mermaid 核心 chunk 的误报。
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      // 这些依赖只在 Node worker 路径上被动态 import（src/shared/document/tools.ts），
      // 浏览器构建里不应该被打包。标 external 让 rollup 在动态 import 处保留原始路径，
      // 浏览器代码也不会真的执行到这些分支。
      external: ['mammoth', 'playwright', /^node:/],
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // 不强行合并 Mermaid（它内部有大量 diagram 子模块，会自动懒加载）
            if (id.includes('prosemirror')) return 'prosemirror'
            if (id.includes('docx') || id.includes('mammoth') || id.includes('jszip')) return 'docx'
            if (id.includes('react') || id.includes('scheduler')) return 'react'
          }
        },
      },
    },
  },
})
