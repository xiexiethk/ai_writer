<template>
  <div class="document-list-item" @click="$emit('click')">
    <n-space align="center" style="width: 100%">
      <n-icon size="32" :component="FileIcon" />

      <div style="flex: 1; min-width: 0">
        <n-space vertical size="small" style="width: 100%">
          <n-space justify="space-between" align="center">
            <n-text strong>{{ document.title }}</n-text>
            <n-tag size="small" :type="getStatusType()" :bordered="false">
              {{ getStatusText() }}
            </n-tag>
          </n-space>

          <n-text depth="3" style="font-size: 12px">
            {{ document.fileName }} · {{ formatFileSize(document.fileSize) }}
          </n-text>

          <n-space size="small">
            <n-tag
              v-for="tag in document.tags"
              :key="tag"
              size="small"
              :bordered="false"
              type="info"
            >
              {{ tag }}
            </n-tag>
          </n-space>
        </n-space>
      </div>

      <n-button-group>
        <n-button v-if="!document.parsed" type="primary" size="small" @click.stop="$emit('parse')">
          解析
        </n-button>
        <n-button v-else size="small" @click.stop="handlePreview">
          预览
        </n-button>
      </n-button-group>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import type { Document } from '@/types/document'
import { DocumentOutline as FileIcon } from '@vicons/ionicons5'

interface Props {
  document: Document
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
  parse: []
}>()

function getStatusType() {
  switch (props.document.parseStatus) {
    case 'success':
      return 'success'
    case 'error':
      return 'error'
    case 'queued':
      return 'info'
    case 'parsing':
      return 'warning'
    default:
      return 'default'
  }
}

function getStatusText() {
  switch (props.document.parseStatus) {
    case 'success':
      return '已解析'
    case 'error':
      return '解析失败'
    case 'queued':
      return '排队中...'
    case 'parsing':
      return '解析中...'
    case 'pending':
    default:
      return '待解析'
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function handlePreview() {
  emit('click')
}
</script>

<style scoped>
.document-list-item {
  cursor: pointer;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--aw-border);
  border-radius: 20px;
  background: var(--aw-shell);
  transition: transform 0.22s ease, border-color 0.22s ease, background-color 0.22s ease;
}

.document-list-item:hover {
  transform: translateY(-2px);
  background-color: var(--aw-paper-strong);
  border-color: var(--aw-border-strong);
}
</style>
