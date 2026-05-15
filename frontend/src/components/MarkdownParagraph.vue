<template>
  <div class="markdown-paragraph-container">
    <!-- 预览模式（Markdown 渲染） - 默认显示 -->
    <div
      v-if="!isEditMode"
      class="markdown-preview"
      v-html="renderedContent"
      :style="previewStyle"
      @click="handleClickPreview"
    ></div>

    <!-- 编辑模式 -->
    <div
      v-else
      ref="editRef"
      contenteditable="true"
      @blur="handleBlur"
      @keydown="handleKeydown"
      class="markdown-editor"
      :style="editorStyle"
    >{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps<{
  content: string
  isEditing?: boolean
  minHeight?: string
  backgroundColor?: string
}>()

const emit = defineEmits<{
  blur: [event: FocusEvent, content: string]
}>()

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
})

const editRef = ref<HTMLDivElement>()
const isEditMode = ref(false)

const handleClickPreview = () => {
  if (props.isEditing) {
    isEditMode.value = true
  }
}

const handleBlur = (event: FocusEvent) => {
  // 立即获取编辑后的内容
  const content = editRef.value?.innerText || props.content

  // 延迟退出编辑模式
  setTimeout(() => {
    isEditMode.value = false
    // 发出 blur 事件，传递内容和事件
    emit('blur', event, content)
  }, 100)
}

const renderedContent = computed(() => {
  if (!props.content) return ''

  const formulas: { placeholder: string; latex: string; type: 'inline' | 'block' }[] = []
  let counter = 0
  let content = props.content

  content = content.replace(/\$\$([\s\S]+?)\$\$/g, (_match, formula) => {
    const placeholder = `MATHBLOCK${counter}PLACEHOLDER`
    formulas.push({ placeholder, latex: formula.trim(), type: 'block' })
    counter++
    return placeholder
  })

  content = content.replace(/\$([^\$\n]+?)\$/g, (_match, formula) => {
    const placeholder = `MATHINLINE${counter}PLACEHOLDER`
    formulas.push({ placeholder, latex: formula.trim(), type: 'inline' })
    counter++
    return placeholder
  })

  let rendered = md.render(content)

  formulas.forEach(({ placeholder, latex, type }) => {
    try {
      const html = katex.renderToString(latex, {
        displayMode: type === 'block',
        throwOnError: false,
      })
      rendered = rendered.replace(placeholder, html)
    } catch (e) {
      const errorHtml = type === 'block'
        ? `<div class="math-error">公式错误: ${latex}</div>`
        : `<span class="math-error">公式错误</span>`
      rendered = rendered.replace(placeholder, errorHtml)
    }
  })

  return rendered
})

const editorStyle = computed(() => ({
  padding: '12px',
  border: '1px solid var(--n-border-color)',
  borderRadius: '4px',
  minHeight: props.minHeight || '60px',
  whiteSpace: 'pre-wrap',
  lineHeight: '1.8',
  backgroundColor: props.backgroundColor || 'var(--n-color)',
  cursor: 'text',
  fontFamily: 'inherit',
  fontSize: 'inherit',
}))

const previewStyle = computed(() => ({
  padding: '12px',
  border: '1px solid var(--n-border-color)',
  borderRadius: '4px',
  minHeight: props.minHeight || '60px',
  lineHeight: '1.8',
  backgroundColor: props.backgroundColor || 'var(--n-color-modal)',
  opacity: '0.95',
  fontFamily: 'inherit',
  fontSize: 'inherit',
  cursor: props.isEditing ? 'text' : 'default',
}))

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    event.preventDefault()
    const selection = window.getSelection()
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0)
      const br = document.createElement('br')
      range.insertNode(br)
      range.setStartAfter(br)
      range.collapse(true)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }
}

watch(isEditMode, async (editing) => {
  if (editing) {
    await nextTick()
    if (editRef.value) {
      editRef.value.focus()
      const range = document.createRange()
      const selection = window.getSelection()
      if (selection && editRef.value) {
        range.selectNodeContents(editRef.value)
        range.collapse(false)
        selection.removeAllRanges()
        selection.addRange(range)
      }
    }
  }
})
</script>

<style scoped>
.markdown-paragraph-container {
  width: 100%;
  position: relative;
}

.markdown-editor,
.markdown-preview {
  width: 100%;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3),
.markdown-preview :deep(h4) {
  font-weight: bold;
  margin: 0.6em 0 0.3em 0;
}

.markdown-preview :deep(h1) {
  font-size: 1.6em;
  border-bottom: 2px solid var(--n-border-color);
  padding-bottom: 0.3em;
}

.markdown-preview :deep(h2) {
  font-size: 1.4em;
  border-bottom: 1px solid var(--n-border-color);
  padding-bottom: 0.3em;
}

.markdown-preview :deep(h3) {
  font-size: 1.2em;
}

.markdown-preview :deep(p) {
  margin: 0.5em 0;
}

.markdown-preview :deep(strong) {
  font-weight: bold;
}

.markdown-preview :deep(em) {
  font-style: italic;
}

.markdown-preview :deep(code) {
  background-color: var(--n-code-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-preview :deep(pre) {
  background-color: var(--n-code-color);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.8em 0;
}

.markdown-preview :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  margin: 0.5em 0;
  padding-left: 2em;
}

.markdown-preview :deep(li) {
  margin: 0.3em 0;
}

.markdown-preview :deep(blockquote) {
  border-left: 4px solid var(--n-primary-color);
  padding-left: 1em;
  margin: 0.8em 0;
  color: var(--n-text-color-2);
}

.markdown-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
}

.markdown-preview :deep(th),
.markdown-preview :deep(td) {
  border: 1px solid var(--n-border-color);
  padding: 8px 12px;
}

.markdown-preview :deep(th) {
  background-color: var(--n-th-color);
  font-weight: bold;
}

.markdown-preview :deep(a) {
  color: var(--n-primary-color);
  text-decoration: none;
}

.markdown-preview :deep(a:hover) {
  text-decoration: underline;
}

.markdown-preview :deep(.math-formula) {
  display: inline-block;
  padding: 8px 12px;
  background-color: var(--n-code-color);
  border-radius: 4px;
  font-family: 'Times New Roman', serif;
  font-style: italic;
}

.markdown-editor {
  outline: none;
}

.markdown-editor:empty:before {
  content: attr(placeholder);
  color: var(--n-placeholder-color);
}

.markdown-editor:focus {
  border-color: var(--n-primary-color) !important;
}

.markdown-preview :deep(.katex) {
  font-size: 1.1em;
}

.markdown-preview :deep(.katex-display) {
  margin: 1em 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.markdown-preview :deep(.math-error) {
  color: #ff4d4f;
  background-color: #fff2f0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
</style>
