<template>
  <div class="pdf-viewer">
    <n-spin :show="isLoading">
      <iframe
        v-if="pdfUrl"
        :src="pdfUrl"
        class="pdf-iframe"
        type="application/pdf"
      ></iframe>
      <n-empty v-else description="无法加载 PDF 文件" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Document } from '@/types/document'

interface Props {
  document: Document
}

const props = defineProps<Props>()
const isLoading = ref(false)

// 构建预览 URL
const pdfUrl = computed(() => {
  const token = localStorage.getItem('token')
  const params = new URLSearchParams({ format: 'pdf' })
  if (token) {
    params.set('token', token)
  }
  return `/api/documents/${props.document.id}/download?${params.toString()}`
})

watch(() => props.document.id, () => {
  isLoading.value = true
  setTimeout(() => {
    isLoading.value = false
  }, 500)
}, { immediate: true })
</script>

<style scoped>
.pdf-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 8px;
}
</style>
