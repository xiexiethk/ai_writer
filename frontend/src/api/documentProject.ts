import apiClient from './index'

// 文档项目接口定义
export interface DocumentProject {
  id: string
  title: string
  folderIds: string[]
  outline: OutlineNode[] | null
  outlineLocked: boolean
  sections: Record<string, SectionContent>
  conversations?: ReportConversation[]
  createdAt: string
  updatedAt: string
}

export interface OutlineNode {
  id: string
  label: string
  children: OutlineNode[]
  key?: string
  level?: number
}

export interface SectionContent {
  sectionId: string
  paragraphs: Paragraph[]
  sources: Source[]
}

export interface Paragraph {
  id: string
  content: string
  timestamp: string
  versions?: ParagraphVersion[]
}

export interface ParagraphVersion {
  content: string
  timestamp: string
}

export interface GeneratedParagraph {
  paragraph_id: string
  section_id: string
  content: string
  sources: Source[]
  timestamp: string
  versions?: ParagraphVersion[]
}

export interface Source {
  id: string
  document_id: string
  document_name: string
  title: string
  content: string
  score: number
}

export interface ConversationContextMeta {
  usedSummary: boolean
  recentTurns: number
  retrievedMemories: number
  truncated: boolean
  estimatedInputTokens: number
}

export interface ReportConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  intentType: string
  appliedOperation: string
  tokenEstimate: number
  sourceRefs: string[]
  sources?: Source[]
  costTrace?: Record<string, any>
  summaryEligible?: boolean
  contextMeta?: ConversationContextMeta
  timestamp: string
}

export interface ReportConversation {
  id: string
  scopeType: 'project' | 'section'
  scopeId: string
  title: string
  rollingSummary: string
  summaryVersion: number
  compactedMessageCount: number
  recentWindow: number
  tokenBudget: number
  lastCompactedAt?: string | null
  memoryStatus?: Record<string, any>
  contextConfig?: Record<string, any>
  messages: ReportConversationMessage[]
  createdAt: string
  updatedAt: string
}

export interface ConversationListResponse {
  conversations: ReportConversation[]
  total: number
}

export interface SendConversationMessageResponse {
  assistantMessage: ReportConversationMessage
  sources: Source[]
  contextMeta: ConversationContextMeta
  appliedParagraph?: GeneratedParagraph | null
  conversation?: ReportConversation
}

export interface ProjectListResponse {
  projects: DocumentProject[]
  total: number
}

// 文档项目 API
export const documentProjectApi = {
  // 创建项目
  create: async (data: {
    title: string
    folderIds?: string[]
    outline?: OutlineNode[]
    content?: SectionContent[]
  }): Promise<DocumentProject> => {
    const response = await apiClient.post<DocumentProject>('/document-projects', data)
    return response.data
  },

  // 获取项目列表
  list: async (skip?: number, limit?: number): Promise<ProjectListResponse> => {
    const response = await apiClient.get<ProjectListResponse>('/document-projects', {
      params: { skip, limit },
    })
    return response.data
  },

  // 获取项目详情
  get: async (projectId: string): Promise<DocumentProject> => {
    const response = await apiClient.get<DocumentProject>(`/document-projects/${projectId}`)
    return response.data
  },

  // 更新大纲
  updateOutline: async (
    projectId: string,
    outline: OutlineNode[],
    locked: boolean
  ): Promise<DocumentProject> => {
    const response = await apiClient.put<DocumentProject>(
      `/document-projects/${projectId}/outline`,
      { outline, locked }
    )
    return response.data
  },

  // 生成大纲
  generateOutline: async (projectId: string, topic: string): Promise<DocumentProject> => {
    const response = await apiClient.post<DocumentProject>(
      `/document-projects/${projectId}/generate-outline`,
      { topic },
      { timeout: 300000 } // 5分钟超时
    )
    return response.data
  },

  // 删除项目
  delete: async (projectId: string): Promise<void> => {
    await apiClient.delete(`/document-projects/${projectId}`)
  },

  // 生成章节内容
  generateContent: async (
    projectId: string,
    sectionId: string,
    sectionTitle: string,
    contextSections?: string[]
  ): Promise<GeneratedParagraph> => {
    const response = await apiClient.post<GeneratedParagraph>(`/document-projects/${projectId}/generate-content`, {
      sectionId,
      sectionTitle,
      contextSections: contextSections || []
    }, { timeout: 300000 })
    return response.data
  },

  // 重新生成段落
  regenerateParagraph: async (
    projectId: string,
    sectionId: string,
    sectionTitle: string,
    contextSections?: string[],
    customPrompt?: string
  ): Promise<GeneratedParagraph> => {
    const response = await apiClient.post<GeneratedParagraph>(`/document-projects/${projectId}/regenerate-paragraph`, {
      sectionId,
      sectionTitle,
      contextSections: contextSections || [],
      customPrompt: customPrompt || ''
    }, { timeout: 300000 })
    return response.data
  },

  // 更新段落内容
  updateParagraph: async (
    projectId: string,
    sectionId: string,
    paragraphId: string,
    content: string
  ): Promise<{ message: string }> => {
    const response = await apiClient.put<{ message: string }>(
      `/document-projects/${projectId}/paragraph`,
      { sectionId, paragraphId, content }
    )
    return response.data
  },

  // 恢复段落版本
  restoreParagraphVersion: async (
    projectId: string,
    sectionId: string,
    paragraphId: string,
    versionIndex: number
  ): Promise<DocumentProject> => {
    const response = await apiClient.post<DocumentProject>(
      `/document-projects/${projectId}/restore-paragraph-version`,
      { sectionId, paragraphId, versionIndex }
    )
    return response.data
  },

  // 获取项目详情（别名）
  getProject: async (projectId: string): Promise<DocumentProject> => {
    const response = await apiClient.get<DocumentProject>(`/document-projects/${projectId}`)
    return response.data
  },

  // 导出为 Word 文档
  exportWord: async (projectId: string, title: string = '文档'): Promise<void> => {
    const response = await apiClient.get(`/document-projects/${projectId}/export-word`, {
      params: { title },  // 将 title 作为查询参数传递
      responseType: 'blob'
    })

    // 创建下载链接
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${title}.docx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  },

  // 获取预览HTML的URL（自动附带 token 以支持 iframe 预览）
  getPreviewHtmlUrl: (projectId: string): string => {
    const token = localStorage.getItem('token')
    const params = token ? `?token=${encodeURIComponent(token)}` : ''
    return `/api/document-projects/${projectId}/preview-html${params}`
  },

  // 列出写作会话
  listConversations: async (
    projectId: string,
    params?: { scopeType?: 'project' | 'section'; scopeId?: string }
  ): Promise<ConversationListResponse> => {
    const response = await apiClient.get<ConversationListResponse>(
      `/document-projects/${projectId}/conversations`,
      { params }
    )
    return response.data
  },

  // 创建写作会话
  createConversation: async (
    projectId: string,
    data: { scopeType: 'project' | 'section'; scopeId?: string; title?: string }
  ): Promise<ReportConversation> => {
    const response = await apiClient.post<ReportConversation>(
      `/document-projects/${projectId}/conversations`,
      data
    )
    return response.data
  },

  // 获取写作会话详情
  getConversation: async (projectId: string, conversationId: string): Promise<ReportConversation> => {
    const response = await apiClient.get<ReportConversation>(
      `/document-projects/${projectId}/conversations/${conversationId}`
    )
    return response.data
  },

  // 发送写作会话消息
  sendConversationMessage: async (
    projectId: string,
    conversationId: string,
    data: {
      message: string
      applyMode?: 'suggest_only' | 'apply_to_section'
      targetSectionId?: string
    }
  ): Promise<SendConversationMessageResponse> => {
    const response = await apiClient.post<any>(
      `/document-projects/${projectId}/conversations/${conversationId}/messages`,
      data,
      { timeout: 180000 }
    )

    return {
      assistantMessage: response.data.assistant_message,
      sources: response.data.sources || [],
      contextMeta: response.data.context_meta,
      appliedParagraph: response.data.applied_paragraph,
      conversation: response.data.conversation,
    }
  },

  // 更新项目内容（富文本编辑后保存）
  updateProjectContent: async (
    projectId: string,
    sections: Array<{
      sectionId: string
      title: string
      paragraphs: Array<{
        content: string
        sources?: Source[]
      }>
    }>
  ): Promise<DocumentProject> => {
    const response = await apiClient.put<DocumentProject>(
      `/document-projects/${projectId}/content`,
      { sections }
    )
    return response.data
  },

  // 更新完整的富文本内容
  updateFullHtml: async (projectId: string, fullHtml: string): Promise<DocumentProject> => {
    const response = await apiClient.put<DocumentProject>(
      `/document-projects/${projectId}/full-html`,
      { full_html: fullHtml }
    )
    return response.data
  },
}
