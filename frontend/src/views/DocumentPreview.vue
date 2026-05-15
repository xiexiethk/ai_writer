<template>
  <div class="document-preview">
    <!-- 顶部工具栏 -->
    <n-layout-header bordered style="height: 60px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between;">
      <n-space align="center">
        <n-button text @click="goBack">
          <template #icon>
            <n-icon :component="ArrowBackIcon" />
          </template>
          返回
        </n-button>
        <n-divider vertical />
        <n-text strong>{{ document?.title || '加载中...' }}</n-text>
        <n-tag v-if="document" size="small" :type="document.parsed ? 'success' : 'warning'">
          {{ document.parsed ? '已解析' : '待解析' }}
        </n-tag>
      </n-space>

      <n-space>
        <n-button type="success" @click="openInAgent" :disabled="!document">
          <template #icon>
            <n-icon :component="ComposeIcon" />
          </template>
          在 Agent 中使用
        </n-button>
        <n-button @click="handleParse" :loading="isParsing" :disabled="!document || document.parsed">
          <template #icon>
            <n-icon :component="RefreshIcon" />
          </template>
          解析文档
        </n-button>
        <n-button @click="handleChunk" :loading="isChunking" :disabled="!document || !document.parsed">
          <template #icon>
            <n-icon :component="GridIcon" />
          </template>
          分块
        </n-button>
        <n-button @click="handleViewChunks" :disabled="!document || !document.chunked">
          <template #icon>
            <n-icon :component="GridIcon" />
          </template>
          查看分块结果
        </n-button>
        <n-button v-if="!isPreviewMode" type="primary" @click="handleSave" :loading="isSaving">
          <template #icon>
            <n-icon :component="SaveIcon" />
          </template>
          保存修改
        </n-button>
      </n-space>
    </n-layout-header>

    <!-- 主内容区：分屏显示 -->
    <n-layout-content style="height: calc(100vh - 60px);">
      <div class="split-view">
        <!-- 左侧：PDF 预览 -->
        <div class="left-panel">
          <div class="panel-header">
            <n-text strong>原文档 (PDF)</n-text>
          </div>
          <div class="pdf-container">
            <PDFViewer v-if="document" :document-id="document.id" />
            <n-empty v-else description="文档加载中..." />
          </div>
        </div>

        <!-- 右侧：Markdown 编辑器 -->
        <div class="right-panel">
          <div class="panel-header">
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-text strong>解析内容 (Markdown)</n-text>
              <n-switch v-model:value="isPreviewMode">
                <template #checked>
                  预览
                </template>
                <template #unchecked>
                  编辑
                </template>
              </n-switch>
            </n-space>
          </div>

          <!-- 编辑模式 -->
          <div v-if="!isPreviewMode" class="editor-container">
            <textarea
              v-model="markdownContent"
              class="markdown-editor"
              spellcheck="false"
              placeholder="文档尚未解析，请点击上方解析文档按钮开始解析..."
            ></textarea>
          </div>

          <!-- 预览模式 -->
          <div v-else class="preview-container">
            <div class="markdown-preview" v-html="renderedMarkdown"></div>
          </div>
        </div>
      </div>
    </n-layout-content>

    <!-- 分块预览抽屉 -->
    <n-drawer v-model:show="showChunkDrawer" :width="800" placement="right">
      <template #header>
        <n-space align="center">
          <n-icon :component="GridIcon" />
          <n-text strong>文档分块预览</n-text>
          <n-tag v-if="chunks.length > 0" type="info" size="small">
            {{ chunks.length }} 个块
          </n-tag>
        </n-space>
      </template>

      <n-spin :show="isChunking">
        <div v-if="chunks.length === 0 && !isChunking" class="empty-chunks">
          <n-empty description="暂无分块数据">
            <template #extra>
              <n-button @click="handleChunk" type="primary">
                开始分块
              </n-button>
            </template>
          </n-empty>
        </div>

        <div v-else class="chunks-list">
          <n-collapse>
            <n-collapse-item
              v-for="chunk in chunks"
              :key="chunk.id"
              :title="`${chunk.title || '无标题'} (Level ${chunk.level})`"
            >
              <template #header-extra>
                <n-tag size="tiny" :bordered="false">
                  #{{ chunk.chunk_index }}
                </n-tag>
              </template>

              <div class="chunk-content">
                <n-descriptions :column="2" size="small" bordered>
                  <n-descriptions-item label="块标题">
                    {{ chunk.title }}
                  </n-descriptions-item>
                  <n-descriptions-item label="层级">
                    Level {{ chunk.level }}
                  </n-descriptions-item>
                </n-descriptions>

                <n-divider />

                <div class="chunk-text">
                  <pre>{{ chunk.content }}</pre>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>
      </n-spin>

      <template #footer>
        <n-space justify="space-between">
          <n-text depth="3">提示：点击分块按钮开始分析文档结构</n-text>
          <n-button @click="showChunkDrawer = false">关闭</n-button>
        </n-space>
      </template>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
// 导入代码高亮样式
import 'highlight.js/styles/github-dark.css'
import {
  ArrowBackOutline as ArrowBackIcon,
  RefreshOutline as RefreshIcon,
  SaveOutline as SaveIcon,
  GridOutline as GridIcon,
  CreateOutline as ComposeIcon,
} from '@vicons/ionicons5'
import { documentApi, type Chunk } from '@/api/document'
import type { Document } from '@/types/document'
import PDFViewer from '@/components/common/PDFViewer.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

// 配置 Markdown-it
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  highlight: function (str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (__) {}
    }
    return ''
  }
})

const documentId = ref(route.params.id as string)
const document = ref<Document | null>(null)
const markdownContent = ref('')
const isSaving = ref(false)
const isParsing = ref(false)
const isLoading = ref(false)
const isPreviewMode = ref(false)

// 分块相关状态
const isChunking = ref(false)
const showChunkDrawer = ref(false)
const chunks = ref<Chunk[]>([])

// 轮询定时器
let pollingInterval: ReturnType<typeof setInterval> | null = null

// 自定义图片渲染规则（在 computed 之前定义）
const defaultImageRender = md.renderer.rules.image || function(tokens, idx, options, _env, self) {
  return self.renderToken(tokens, idx, options)
}

md.renderer.rules.image = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  const src = token.attrGet('src')
  const resolvedSrc = resolveDocumentImageSrc(src)

  if (resolvedSrc) {
    token.attrSet('src', resolvedSrc)
  }

  // 使用默认渲染器
  return defaultImageRender(tokens, idx, options, env, self)
}

function buildDocumentImageUrl(imageName: string) {
  const authToken = localStorage.getItem('token')
  return authToken
    ? `/api/documents/${documentId.value}/images/${imageName}?token=${encodeURIComponent(authToken)}`
    : `/api/documents/${documentId.value}/images/${imageName}`
}

function resolveDocumentImageSrc(src?: string | null) {
  if (!src) return null

  if (src.startsWith('images/')) {
    return buildDocumentImageUrl(src.replace('images/', ''))
  }

  if (src.includes('parsed_output') || src.includes('images/')) {
    const match = src.match(/([a-f0-9]{64}\.(?:jpg|png|jpeg))/i)
    if (match) {
      return buildDocumentImageUrl(match[1])
    }
  }

  return null
}

function normalizeMarkdownForPreview(content: string) {
  return content.replace(/!\[([^\]]*)\]\(([^)\n]+)\)/g, (full, altText, rawSrc) => {
    const resolvedSrc = resolveDocumentImageSrc(rawSrc)
    if (!resolvedSrc) {
      return full
    }
    const safeAlt = String(altText || '').replace(/"/g, '&quot;')
    return `<img src="${resolvedSrc}" alt="${safeAlt}" />`
  })
}

// 渲染 Markdown
const renderedMarkdown = computed(() => {
  if (!markdownContent.value) return ''
  try {
    return md.render(normalizeMarkdownForPreview(markdownContent.value))
  } catch (error) {
    console.error('Markdown 渲染失败:', error)
    return markdownContent.value
  }
})

function isVectorizeCompleted(status?: string, chunked?: boolean) {
  return Boolean(chunked) || status === 'completed' || status === 'success'
}

async function loadDocument() {
  try {
    isLoading.value = true
    const doc = await documentApi.get(documentId.value)
    document.value = doc

    // 确保 markdownContent 被正确赋值
    const content = doc.markdownContent || ''
    markdownContent.value = content

    if ((doc.parseStatus === 'parsing' || doc.parseStatus === 'queued') && pollingInterval === null) {
      isParsing.value = true
      pollParseStatus()
    } else if ((doc.vectorizeStatus === 'processing' || doc.vectorizeStatus === 'queued') && pollingInterval === null) {
      isChunking.value = true
      pollVectorizeStatus(ref(false))
    }
  } catch (error) {
    console.error('加载文档失败:', error)
    message.error('加载文档失败: ' + (error as Error).message)
  } finally {
    isLoading.value = false
  }
}

function goBack() {
  router.back()
}

function openInAgent() {
  if (!document.value) return
  router.push({
    name: 'OpenWps',
    query: {
      documentId: document.value.id,
      documentTitle: document.value.title,
      folderId: document.value.folderId,
    },
  })
}

async function handleSave() {
  if (!document.value) return

  try {
    isSaving.value = true
    const updatedDoc = await documentApi.updateContent(document.value.id, markdownContent.value)
    message.success('保存成功')

    // 更新本地文档状态
    document.value = updatedDoc
    markdownContent.value = updatedDoc.markdownContent || markdownContent.value
  } catch (error) {
    console.error('保存失败:', error)
    message.error('保存失败: ' + (error as Error).message)
  } finally {
    isSaving.value = false
  }
}

async function handleParse() {
  if (!document.value) return

  // 清除之前的轮询
  if (pollingInterval !== null) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }

  try {
    isParsing.value = true
    message.info('解析任务已启动，正在后台处理，请耐心等待...', {
      duration: 5000
    })

    // 启动解析任务
    await documentApi.parse(document.value.id)

    // 开始轮询解析状态
    pollParseStatus()
  } catch (error) {
    console.error('启动解析任务失败:', error)
    message.error('启动解析任务失败：' + (error as Error).message)
    isParsing.value = false
  }
}

async function handleChunk() {
  if (!document.value) return

  // 防止重复点击
  if (isChunking.value || document.value.vectorizeStatus === 'processing' || document.value.vectorizeStatus === 'queued') {
    if (!isChunking.value) {
      isChunking.value = true
      pollVectorizeStatus(ref(false))
    }
    message.warning('向量化任务正在进行中，请耐心等待...')
    return
  }

  // 清除之前的轮询
  if (pollingInterval !== null) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }

  // 添加完成标志，防止重复弹窗
  const hasCompleted = ref(false)

  try {
    isChunking.value = true
    // 只在控制台显示，不弹窗打扰用户
    console.log('向量化任务已启动，正在后台处理...')

    // 启动向量化任务
    await documentApi.vectorize(document.value.id)

    // 开始轮询向量化状态
    pollVectorizeStatus(hasCompleted)
  } catch (error) {
    console.error('启动向量化任务失败:', error)
    message.error('启动向量化任务失败：' + (error as Error).message)
    isChunking.value = false
  }
}

async function handleViewChunks() {
  if (!document.value) return

  try {
    // 显示加载状态
    isChunking.value = true

    // 获取分块结果
    const chunksResult = await documentApi.getChunks(document.value.id)
    chunks.value = chunksResult.chunks || []

    // 打开分块抽屉
    showChunkDrawer.value = true

    message.success(`加载了 ${chunks.value.length} 个分块`)
  } catch (error) {
    console.error('获取分块结果失败:', error)
    message.error('获取分块结果失败：' + (error as Error).message)
  } finally {
    isChunking.value = false
  }
}

// 轮询向量化状态
function pollVectorizeStatus(hasCompleted: Ref<boolean>) {
  const currentDocumentId = document.value?.id
  if (!currentDocumentId) return

  const maxAttempts = 300 // 最多轮询10分钟（每2秒一次）
  let attempts = 0
  let consecutiveErrors = 0 // 连续错误次数

  pollingInterval = setInterval(async () => {
    attempts++

    try {
      const status = await documentApi.getVectorizeStatus(currentDocumentId)

      console.log('向量化状态:', status)

      // 重置错误计数
      consecutiveErrors = 0

      // 更新文档状态
      if (document.value) {
        document.value.vectorizeStatus = status.status
        document.value.chunked = Boolean(status.chunked)
        document.value.chunkCount = status.chunkCount || 0
        document.value.errorMessage = status.errorMessage
      }

      if (isVectorizeCompleted(status.status, status.chunked) && !hasCompleted.value) {
        // 标记为已完成，防止重复弹窗
        hasCompleted.value = true

        stopPolling()
        const chunkCount = status.chunkCount || 0
        message.success(`向量化完成！共生成 ${chunkCount} 个块,已存储到向量数据库`)
        await loadDocument()
        // 获取分块结果预览
        try {
          const chunksResult = await documentApi.getChunks(currentDocumentId)
          chunks.value = chunksResult.chunks || []
          showChunkDrawer.value = true
        } catch (error) {
          console.error('获取分块结果失败:', error)
          // 即使获取分块失败也继续
        }
      } else if (status.status === 'error') {
        stopPolling()
        message.error(status.errorMessage || '向量化失败，请查看日志')
      } else if (attempts >= maxAttempts) {
        stopPolling()
        message.warning('向量化时间较长，请稍后手动刷新查看结果')
      }
    } catch (error) {
      consecutiveErrors++
      console.log(`获取向量化状态中... (${consecutiveErrors}/5)`) // 只在控制台显示，不弹窗

      // 连续失败5次才停止轮询（容错处理）
      if (consecutiveErrors >= 5) {
        stopPolling()
        message.error('获取向量化状态失败，请稍后重试')
      }
      // 否则继续轮询，不弹窗
    }
  }, 2000) // 每2秒轮询一次
}

// 轮询解析状态
function pollParseStatus() {
  const currentDocumentId = document.value?.id
  if (!currentDocumentId) return

  const maxAttempts = 300 // 最多轮询10分钟（每2秒一次）
  let attempts = 0
  let consecutiveErrors = 0 // 连续错误次数

  pollingInterval = setInterval(async () => {
    attempts++

    try {
      const status = await documentApi.getParseStatus(currentDocumentId)

      console.log('解析状态:', status)

      // 重置错误计数
      consecutiveErrors = 0

      // 更新文档状态
      if (document.value) {
        document.value.parseStatus = status.status
        document.value.parsed = status.parsed
      }

      if (status.status === 'success' || status.parsed) {
        stopPolling()
        message.success('解析成功！')
        await loadDocument()
      } else if (status.status === 'error') {
        stopPolling()
        message.error('解析失败，请查看日志')
      } else if (attempts >= maxAttempts) {
        stopPolling()
        message.warning('解析时间较长，请稍后手动刷新查看结果')
      }
    } catch (error) {
      consecutiveErrors++
      console.error(`获取解析状态失败 (第${consecutiveErrors}次):`, error)

      // 连续失败5次才停止轮询（容错处理）
      if (consecutiveErrors >= 5) {
        stopPolling()
        message.error('获取解析状态失败，请稍后重试')
      }
      // 否则继续轮询
    }
  }, 2000) // 每2秒轮询一次
}

// 停止轮询
function stopPolling() {
  if (pollingInterval !== null) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
  // 同时停止解析和分块的加载状态
  isParsing.value = false
  isChunking.value = false
}

onMounted(() => {
  loadDocument()
})

onUnmounted(() => {
  stopPolling()
})

// 监听路由参数变化
watch(() => route.params.id, (newId) => {
  if (newId) {
    stopPolling()
    documentId.value = newId as string
    loadDocument()
  }
})
</script>

<style scoped>
.document-preview {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.split-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.left-panel,
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.left-panel {
  border-right: 1px solid var(--n-border-color);
  background-color: #525659;
}

.right-panel {
  background-color: var(--n-color);
}

.panel-header {
  padding: 10px 16px;
  border-bottom: 1px solid var(--n-border-color);
  background-color: var(--n-color-modal);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.pdf-container {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.editor-container {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.preview-container {
  flex: 1;
  overflow: auto;
  position: relative;
  padding: 20px;
}

.markdown-editor {
  width: 100%;
  height: 100%;
  border: none;
  resize: none;
  padding: 20px;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.8;
  background-color: var(--n-color);
  color: var(--n-text-color);
  outline: none;
  box-sizing: border-box;
}

.markdown-preview {
  width: 100%;
  font-size: 15px;
  line-height: 1.8;
  color: var(--n-text-color);
}

.markdown-preview h1,
.markdown-preview h2,
.markdown-preview h3,
.markdown-preview h4,
.markdown-preview h5,
.markdown-preview h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-preview h1 {
  font-size: 2em;
  border-bottom: 1px solid var(--n-border-color);
  padding-bottom: 8px;
}

.markdown-preview h2 {
  font-size: 1.5em;
  border-bottom: 1px solid var(--n-border-color);
  padding-bottom: 8px;
}

.markdown-preview p {
  margin-bottom: 16px;
}

.markdown-preview code {
  background-color: var(--n-code-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.9em;
}

.markdown-preview pre {
  background-color: var(--n-code-color);
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin-bottom: 16px;
}

.markdown-preview pre code {
  background-color: transparent;
  padding: 0;
}

.markdown-preview ul,
.markdown-preview ol {
  padding-left: 2em;
  margin-bottom: 16px;
}

.markdown-preview li {
  margin-bottom: 4px;
}

.markdown-preview img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 16px 0;
}

.markdown-preview table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 16px;
}

.markdown-preview table th,
.markdown-preview table td {
  border: 1px solid var(--n-border-color);
  padding: 8px 12px;
}

.markdown-preview table th {
  background-color: var(--n-th-color);
  font-weight: 600;
}

.markdown-preview blockquote {
  border-left: 4px solid var(--n-border-color);
  padding-left: 16px;
  margin: 16px 0;
  color: var(--n-text-color3);
}

.markdown-editor:focus {
  outline: none;
}

.markdown-editor::placeholder {
  color: #999;
}

/* 分块相关样式 */
.empty-chunks {
  padding: 40px 20px;
  text-align: center;
}

.chunks-list {
  padding: 16px;
}

.chunk-content {
  padding: 12px 0;
}

.chunk-text {
  margin-top: 12px;
}

.chunk-text pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  background-color: var(--n-color-modal);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  max-height: 300px;
  overflow-y: auto;
}
</style>
