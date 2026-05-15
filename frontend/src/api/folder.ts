/**
 * 知识库（文件夹）相关 API
 */
import axios from 'axios'

const BASE_URL = '/api/folders'

export interface Folder {
  id: string
  name: string
  parentId: string | null
  createdAt: string
  updatedAt?: string
}

export interface FolderStats {
  folderId: string
  folderName: string
  totalDocuments: number
  parsedDocuments: number
  vectorizedDocuments: number
  totalSize: number
  createdAt: string
  updatedAt: string
}

export interface MergeRequest {
  source_folder_ids: string[]
  target_folder_id: string
  delete_source?: boolean
}

export interface SplitItem {
  target_folder_id?: string
  target_folder_name?: string
  document_ids: string[]
}

export interface SplitRequest {
  source_folder_id: string
  splits: SplitItem[]
  delete_source?: boolean
}

export interface SearchResult {
  id: string
  title: string
  score: number
  uploadTime: string
  fileSize: number
  parsed: boolean
  vectorized: boolean
}

export interface SearchResponse {
  query: string
  folderId: string
  folderName: string
  totalDocuments: number
  resultCount: number
  results: SearchResult[]
}

export const folderApi = {
  // 获取所有知识库
  async list(): Promise<Folder[]> {
    const response = await axios.get(BASE_URL)
    return response.data
  },

  // 创建知识库
  async create(name: string, parentId: string | null = null): Promise<Folder> {
    const response = await axios.post(BASE_URL, { name, parentId })
    return response.data
  },

  // 更新知识库（重命名）
  async update(folderId: string, name: string): Promise<Folder> {
    const response = await axios.put(`${BASE_URL}/${folderId}`, { name })
    return response.data
  },

  // 删除知识库
  async delete(folderId: string): Promise<{ message: string }> {
    const response = await axios.delete(`${BASE_URL}/${folderId}`)
    return response.data
  },

  // 合并知识库
  async merge(data: MergeRequest): Promise<{
    message: string
    targetFolderId: string
    targetFolderName: string
    sourceFolderIds: string[]
    movedDocumentCount: number
    deletedSourceFolders: string[]
  }> {
    const response = await axios.post(`${BASE_URL}/merge`, data)
    return response.data
  },

  // 拆分知识库
  async split(folderId: string, data: SplitRequest): Promise<{
    message: string
    sourceFolderId: string
    sourceFolderName: string
    movedDocumentCount: number
    createdFolders: Array<{ id: string; name: string }>
    folderMapping: Record<string, number>
    deletedSource: boolean
  }> {
    const response = await axios.post(`${BASE_URL}/${folderId}/split`, data)
    return response.data
  },

  // 获取知识库统计信息
  async getStats(folderId: string): Promise<FolderStats> {
    const response = await axios.get(`${BASE_URL}/${folderId}/stats`)
    return response.data
  },

  // 搜索知识库中的相关文档
  async search(folderId: string, query: string, topK: number = 20): Promise<SearchResponse> {
    const response = await axios.post(`${BASE_URL}/${folderId}/search`, null, {
      params: { query, top_k: topK }
    })
    return response.data
  }
}
