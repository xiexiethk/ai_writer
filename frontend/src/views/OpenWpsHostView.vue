<template>
  <div class="openwps-host">
    <iframe :src="iframeSrc" class="openwps-frame" title="OpenWPS Agent Workspace" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

function firstQueryValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    const first = value.find(item => typeof item === 'string' && item.trim())
    return typeof first === 'string' ? first.trim() : null
  }
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function listQueryValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .flatMap(item => typeof item === 'string' ? item.split(',') : [])
      .map(item => item.trim())
      .filter(Boolean)
  }
  if (typeof value === 'string' && value.trim()) {
    return value.split(',').map(item => item.trim()).filter(Boolean)
  }
  return []
}

const iframeSrc = computed(() => {
  const params = new URLSearchParams()

  const folderId = firstQueryValue(route.query.folderId)
  const documentId = firstQueryValue(route.query.documentId)
  const folderName = firstQueryValue(route.query.folderName)
  const documentTitle = firstQueryValue(route.query.documentTitle)
  const folderIds = listQueryValues(route.query.folderIds)
  const documentIds = listQueryValues(route.query.documentIds)

  if (folderId) params.set('folderId', folderId)
  if (documentId) params.set('documentId', documentId)
  if (folderName) params.set('folderName', folderName)
  if (documentTitle) params.set('documentTitle', documentTitle)
  folderIds.forEach(item => params.append('folderIds', item))
  documentIds.forEach(item => params.append('documentIds', item))

  const query = params.toString()
  return query ? `/openwps/?${query}` : '/openwps/'
})
</script>

<style scoped>
.openwps-host {
  width: 100%;
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.openwps-frame {
  width: 100%;
  flex: 1;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--aw-border);
  border-radius: 8px;
  background: var(--aw-paper);
}
</style>
