<template>
  <div class="markdown-renderer" v-html="renderedMarkdown" @click="handleClick"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import type { Source } from '@/api/chat'

const props = defineProps<{
  content: string
  sources?: Source[]
}>()

const emit = defineEmits<{
  sourceClick: [source: Source]
}>()

// 初始化 markdown-it
const md = new MarkdownIt({
  html: false,        // 禁用 HTML 标签
  linkify: true,      // 自动转换 URL 为链接
  typographer: true,  // 启用一些语言中立的替换和引号美化
  breaks: true,       // 转换换行符为 <br>
})

function withSourceLinks(content: string): string {
  const sources = props.sources || []
  if (!content || sources.length === 0) return content

  let linked = content

  linked = linked.replace(/引用(\d+)/g, (match, indexStr) => {
    const index = Number(indexStr)
    if (!Number.isInteger(index) || index < 1 || index > sources.length) {
      return match
    }
    return `[引用${index}](source://${index})`
  })

  linked = linked.replace(/\[(\d+)\]/g, (match, indexStr) => {
    const index = Number(indexStr)
    if (!Number.isInteger(index) || index < 1 || index > sources.length) {
      return match
    }
    return `[[${index}]](source://${index})`
  })

  return linked
}

const renderedMarkdown = computed(() => {
  if (!props.content) return ''
  return md.render(withSourceLinks(props.content))
})

function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  const anchor = target?.closest('a')
  if (!anchor) return

  const href = anchor.getAttribute('href') || ''
  if (!href.startsWith('source://')) return

  event.preventDefault()
  const index = Number(href.replace('source://', ''))
  if (!Number.isInteger(index) || index < 1) return

  const source = props.sources?.[index - 1]
  if (source) {
    emit('sourceClick', source)
  }
}
</script>

<style scoped>
.markdown-renderer {
  line-height: 1.8;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* Markdown 样式 */
.markdown-renderer :deep(h1) {
  font-size: 1.8em;
  font-weight: bold;
  margin: 0.8em 0 0.4em 0;
  border-bottom: 2px solid var(--n-border-color);
  padding-bottom: 0.3em;
}

.markdown-renderer :deep(h2) {
  font-size: 1.5em;
  font-weight: bold;
  margin: 0.8em 0 0.4em 0;
  border-bottom: 1px solid var(--n-border-color);
  padding-bottom: 0.3em;
}

.markdown-renderer :deep(h3) {
  font-size: 1.3em;
  font-weight: bold;
  margin: 0.6em 0 0.3em 0;
}

.markdown-renderer :deep(h4) {
  font-size: 1.1em;
  font-weight: bold;
  margin: 0.6em 0 0.3em 0;
}

.markdown-renderer :deep(p) {
  margin: 0.5em 0;
}

.markdown-renderer :deep(strong) {
  font-weight: bold;
}

.markdown-renderer :deep(em) {
  font-style: italic;
}

.markdown-renderer :deep(code) {
  background-color: var(--n-code-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-renderer :deep(pre) {
  background-color: var(--n-code-color);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.8em 0;
}

.markdown-renderer :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown-renderer :deep(ul),
.markdown-renderer :deep(ol) {
  margin: 0.5em 0;
  padding-left: 2em;
}

.markdown-renderer :deep(li) {
  margin: 0.3em 0;
}

.markdown-renderer :deep(blockquote) {
  border-left: 4px solid var(--n-primary-color);
  padding-left: 1em;
  margin: 0.8em 0;
  color: var(--n-text-color-2);
}

.markdown-renderer :deep(a) {
  color: var(--n-primary-color);
  text-decoration: none;
}

.markdown-renderer :deep(a:hover) {
  text-decoration: underline;
}

.markdown-renderer :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
}

.markdown-renderer :deep(th),
.markdown-renderer :deep(td) {
  border: 1px solid var(--n-border-color);
  padding: 8px 12px;
}

.markdown-renderer :deep(th) {
  background-color: var(--n-th-color);
  font-weight: bold;
}

.markdown-renderer :deep(img) {
  max-width: 100%;
  height: auto;
}
</style>
