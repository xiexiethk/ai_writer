<template>
  <n-upload
    :custom-request="handleUpload"
    :show-file-list="false"
    :disabled="disabled || !folderId"
    accept=".pdf,.doc,.docx"
    multiple
    directory-dnd
  >
    <n-upload-dragger>
      <div style="margin-bottom: 12px">
        <n-icon size="48" :depth="3">
          <CloudUploadOutline />
        </n-icon>
      </div>
      <n-text style="font-size: 16px">
        点击或拖拽文件到此区域上传
      </n-text>
      <n-p depth="3" style="margin: 8px 0 0 0">
        支持文档格式（PDF、Word等）
      </n-p>
    </n-upload-dragger>
  </n-upload>

  <n-divider />

  <div v-if="uploadingFiles.length > 0">
    <n-text depth="3" style="font-size: 12px;">上传队列</n-text>
    <n-list>
      <n-list-item v-for="file in uploadingFiles" :key="file.fileName">
        <n-space vertical style="width: 100%">
          <n-space justify="space-between">
            <n-text>{{ file.fileName }}</n-text>
            <n-text v-if="file.progress < 100" depth="3" style="font-size: 12px">
              {{ file.progress }}%
            </n-text>
            <n-tag v-else size="small" type="success">完成</n-tag>
          </n-space>
          <n-progress
            type="line"
            :percentage="file.progress"
            :status="file.status === 'error' ? 'error' : undefined"
          />
        </n-space>
      </n-list-item>
    </n-list>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { CloudUploadOutline } from '@vicons/ionicons5'
import type { UploadProgress } from '@/types/document'
import { documentApi } from '@/api/document'

interface Props {
  disabled?: boolean
  folderId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  uploadStart: []
  uploaded: [{ fileName: string; documentId: string }]
  queueComplete: [{ successCount: number; errorCount: number }]
}>()

const uploadingFiles = ref<UploadProgress[]>([])
const activeUploads = ref(0)
const successCount = ref(0)
const errorCount = ref(0)

async function handleUpload(options: UploadCustomRequestOptions) {
  const { file, onProgress, onFinish, onError } = options

  const uploadFile: UploadProgress = {
    fileName: file.name,
    progress: 0,
    status: 'uploading',
  }

  uploadingFiles.value.push(uploadFile)
  if (activeUploads.value === 0) {
    successCount.value = 0
    errorCount.value = 0
    emit('uploadStart')
  }
  activeUploads.value += 1

  try {
    if (!props.folderId) {
      throw new Error('请选择目标知识库')
    }

    const response = await documentApi.upload(file.file as File, props.folderId, (progress) => {
      uploadFile.progress = progress
      onProgress({ percent: progress })
    })

    uploadFile.progress = 100
    uploadFile.status = 'success'
    successCount.value += 1

    onFinish()
    emit('uploaded', { fileName: file.name, documentId: response.documentId })

    // 3秒后移除
    setTimeout(() => {
      const index = uploadingFiles.value.indexOf(uploadFile)
      if (index > -1) {
        uploadingFiles.value.splice(index, 1)
      }
    }, 3000)
  } catch (error) {
    uploadFile.progress = 100
    uploadFile.status = 'error'
    errorCount.value += 1
    onError()
  } finally {
    activeUploads.value -= 1
    if (activeUploads.value === 0) {
      emit('queueComplete', {
        successCount: successCount.value,
        errorCount: errorCount.value,
      })
    }
  }
}
</script>

<style scoped>
:deep(.n-upload-dragger) {
  padding: 40px 20px;
}
</style>
