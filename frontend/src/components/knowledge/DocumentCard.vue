<template>
  <n-card
    class="document-card"
    hoverable
    @click="$emit('click')"
  >
    <template #cover>
      <div class="thumbnail">
        <n-icon size="64" :component="FileIcon" />
      </div>
    </template>

    <template #header-extra>
      <n-dropdown :options="getOptions()" @select="handleSelect">
        <n-button circle quaternary size="small">
          <template #icon>
            <n-icon :component="EllipsisVerticalIcon" />
          </template>
        </n-button>
      </n-dropdown>
    </template>

    <n-ellipsis :line-clamp="2" style="font-weight: 600; margin-bottom: 8px;">
      {{ document.title }}
    </n-ellipsis>

    <n-space vertical size="small">
      <n-text depth="3" style="font-size: 12px;">
        {{ document.fileName }}
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

      <n-space justify="space-between" align="center">
        <n-tag
          size="small"
          :type="getStatusType()"
          :bordered="false"
        >
          {{ getStatusText() }}
        </n-tag>

        <n-text depth="3" style="font-size: 12px;">
          {{ formatFileSize(document.fileSize) }}
        </n-text>
      </n-space>
    </n-space>

    <template #action>
      <n-space>
        <n-button
          v-if="!document.parsed"
          type="primary"
          size="small"
          @click.stop="$emit('parse')"
        >
          解析
        </n-button>
        <n-button
          v-else
          size="small"
          @click.stop="handlePreview"
        >
          预览
        </n-button>
      </n-space>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import type { Document } from '@/types/document'
import {
  DocumentOutline as FileIcon,
  EllipsisVerticalOutline as EllipsisVerticalIcon,
} from '@vicons/ionicons5'
import type { DropdownOption } from 'naive-ui'

interface Props {
  document: Document
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
  parse: []
  delete: []
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

function getOptions(): DropdownOption[] {
  return [
    {
      label: '查看详情',
      key: 'view',
    },
    {
      label: '下载',
      key: 'download',
    },
    {
      type: 'divider',
    },
    {
      label: '删除',
      key: 'delete',
      props: {
        style: {
          color: 'var(--n-error-color)',
        },
      },
    },
  ]
}

function handleSelect(key: string) {
  switch (key) {
    case 'view':
      emit('click')
      break
    case 'download':
      // TODO: 实现下载
      break
    case 'delete':
      emit('delete')
      break
  }
}

function handlePreview() {
  emit('click')
}
</script>

<style scoped>
.document-card {
  cursor: pointer;
  transition: transform 0.24s ease, border-color 0.24s ease;
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid var(--aw-border);
  box-shadow: var(--aw-shadow);
}

.document-card:hover {
  transform: translateY(-3px);
  border-color: var(--aw-border-strong);
}

.thumbnail {
  height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    linear-gradient(135deg, rgba(201, 111, 69, 0.1), transparent 65%),
    var(--aw-paper);
  color: var(--aw-accent);
}
</style>
