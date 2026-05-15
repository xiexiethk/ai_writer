<template>
  <div class="pdf-viewer-wrapper">
    <div v-if="error" class="error-message">
      <n-empty description="PDF 加载失败">
        <template #extra>
          <n-text depth="3">{{ error }}</n-text>
        </template>
      </n-empty>
    </div>
    <div v-else class="pdf-content">
      <n-spin :show="loading" description="加载 PDF 中...">
        <div
          v-if="pdfPages.length > 0"
          ref="containerRef"
          class="pdf-pages"
        >
          <canvas
            v-for="(_page, index) in pdfPages"
            :key="index"
            :ref="el => setCanvasRef(el, index)"
            class="pdf-canvas"
          ></canvas>
        </div>
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'

interface Props {
  documentId: string
}

const props = defineProps<Props>()

// 配置 PDF.js worker - 使用本地文件
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js'

const loading = ref(true)
const error = ref('')
const pdfPages = ref<number[]>([])
const canvasRefs = ref<(HTMLCanvasElement | null)[]>([])
const containerRef = ref<HTMLDivElement | null>(null)

let pdfDoc: pdfjsLib.PDFDocumentProxy | null = null

function setCanvasRef(el: any, index: number) {
  canvasRefs.value[index] = el ?? null
}

async function loadPDF() {
  try {
    loading.value = true
    error.value = ''
    pdfPages.value = []
    canvasRefs.value = []

    // 使用base64端点获取PDF数据（带认证头）
    const token = localStorage.getItem('token')
    const headers: HeadersInit = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const response = await fetch(`/api/documents/${props.documentId}/pdf-base64`, { headers })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    if (!data.base64) {
      throw new Error('未收到PDF数据')
    }

    // 将base64转换为二进制数据
    const pdfData = atob(data.base64)
    const arrayBuffer = new ArrayBuffer(pdfData.length)
    const view = new Uint8Array(arrayBuffer)
    for (let i = 0; i < pdfData.length; i++) {
      view[i] = pdfData.charCodeAt(i)
    }

    // 加载PDF
    const loadingTask = pdfjsLib.getDocument({
      data: arrayBuffer,
      verbosity: pdfjsLib.VerbosityLevel.ERRORS,
    })
    pdfDoc = await loadingTask.promise

    // 创建页面占位数组
    pdfPages.value = Array.from({ length: pdfDoc.numPages }, (_, i) => i + 1)
    await nextTick()

    // 渲染所有页面
    await renderAllPages()
  } catch (err: any) {
    console.error('PDF 加载失败:', err)
    error.value = err.message || '未知错误'
  } finally {
    loading.value = false
  }
}

async function renderAllPages() {
  if (!pdfDoc) return

  const scale = 1.5
  for (let i = 1; i <= pdfDoc.numPages; i++) {
    await renderPage(i, scale)
  }
}

async function renderPage(pageNum: number, scale: number) {
  if (!pdfDoc) return

  try {
    const page = await pdfDoc.getPage(pageNum)
    const viewport = page.getViewport({ scale })

    const canvas = canvasRefs.value[pageNum - 1]
    if (!canvas) {
      await nextTick()
    }

    const targetCanvas = canvasRefs.value[pageNum - 1]
    if (!targetCanvas) {
      return
    }

    const context = targetCanvas.getContext('2d')
    if (!context) return

    targetCanvas.height = viewport.height
    targetCanvas.width = viewport.width

    await page.render({
      canvasContext: context,
      viewport: viewport,
    }).promise
  } catch (err) {
    console.error(`渲染第 ${pageNum} 页失败:`, err)
  }
}

onMounted(() => {
  loadPDF()
})

onUnmounted(() => {
  pdfDoc = null
})
</script>

<style scoped>
.pdf-viewer-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #525659;
  overflow: hidden;
}

.error-message {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pdf-content {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.pdf-pages {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.pdf-canvas {
  max-width: 100%;
  height: auto;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  background-color: #fff;
}
</style>
