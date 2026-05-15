import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Document, Folder, DocumentFilter } from '@/types/document'
import type { Ref } from 'vue'

export const useDocumentStore = defineStore('document', () => {
  // State
  const documents: Ref<Document[]> = ref([])
  const selectedDocument: Ref<Document | null> = ref(null)
  const folders: Ref<Folder[]> = ref([])
  const currentFolder: Ref<string | null> = ref(null)
  const filter = ref<DocumentFilter>({
    searchQuery: '',
    selectedTags: [],
    currentFolder: null,
  })
  const viewMode: Ref<'grid' | 'list'> = ref('grid')
  const isLoading = ref(false)

  // Computed
  const filteredDocuments = computed(() => {
    let result = documents.value

    // 文件夹筛选
    if (filter.value.currentFolder) {
      result = result.filter((doc) => doc.folderId === filter.value.currentFolder)
    }

    // 标签筛选
    if (filter.value.selectedTags.length > 0) {
      result = result.filter((doc) =>
        filter.value.selectedTags.some((tag) => doc.tags.includes(tag))
      )
    }

    // 搜索筛选
    if (filter.value.searchQuery) {
      const query = filter.value.searchQuery.toLowerCase()
      result = result.filter(
        (doc) =>
          doc.title.toLowerCase().includes(query) ||
          doc.fileName.toLowerCase().includes(query)
      )
    }

    // 文件类型筛选
    if (filter.value.fileType) {
      result = result.filter((doc) => doc.fileType === filter.value.fileType)
    }

    // 解析状态筛选
    if (filter.value.parseStatus) {
      result = result.filter((doc) => doc.parseStatus === filter.value.parseStatus)
    }

    return result
  })

  const allTags = computed(() => {
    const tagSet = new Set<string>()
    documents.value.forEach((doc) => {
      doc.tags.forEach((tag) => tagSet.add(tag))
    })
    return Array.from(tagSet)
  })

  const documentsByFolder = computed(() => {
    const map = new Map<string, Document[]>()
    documents.value.forEach((doc) => {
      const folderId = doc.folderId || 'root'
      if (!map.has(folderId)) {
        map.set(folderId, [])
      }
      map.get(folderId)!.push(doc)
    })
    return map
  })

  // Actions
  function setDocuments(docs: Document[]) {
    documents.value = docs
  }

  function addDocument(doc: Document) {
    documents.value.unshift(doc)
  }

  function updateDocument(id: string, updates: Partial<Document>) {
    const index = documents.value.findIndex((doc) => doc.id === id)
    if (index !== -1) {
      documents.value[index] = { ...documents.value[index], ...updates }
    }
  }

  function removeDocument(id: string) {
    const index = documents.value.findIndex((doc) => doc.id === id)
    if (index !== -1) {
      documents.value.splice(index, 1)
    }
    if (selectedDocument.value?.id === id) {
      selectedDocument.value = null
    }
  }

  function setSelectedDocument(doc: Document | null) {
    selectedDocument.value = doc
  }

  function setFolders(folderList: Folder[]) {
    folders.value = folderList
  }

  function addFolder(folder: Folder) {
    folders.value.push(folder)
  }

  function updateFolder(updatedFolder: Folder) {
    const index = folders.value.findIndex((f) => f.id === updatedFolder.id)
    if (index !== -1) {
      folders.value[index] = updatedFolder
    }
  }

  function removeFolder(folderId: string) {
    const index = folders.value.findIndex((f) => f.id === folderId)
    if (index !== -1) {
      folders.value.splice(index, 1)
    }
  }

  function setCurrentFolder(folderId: string | null) {
    currentFolder.value = folderId
    filter.value.currentFolder = folderId
  }

  function updateFilter(newFilter: Partial<DocumentFilter>) {
    filter.value = { ...filter.value, ...newFilter }
  }

  function setViewMode(mode: 'grid' | 'list') {
    viewMode.value = mode
  }

  return {
    // State
    documents,
    selectedDocument,
    folders,
    currentFolder,
    filter,
    viewMode,
    isLoading,
    // Computed
    filteredDocuments,
    allTags,
    documentsByFolder,
    // Actions
    setDocuments,
    addDocument,
    updateDocument,
    removeDocument,
    setSelectedDocument,
    setFolders,
    addFolder,
    updateFolder,
    removeFolder,
    setCurrentFolder,
    updateFilter,
    setViewMode,
  }
})
