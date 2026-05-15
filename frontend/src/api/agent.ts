import apiClient from './index'
import type { Source, Conversation } from './chat'

// Agent 思考步骤接口
export interface AgentStep {
  type: 'thought' | 'action' | 'observation' | 'answer'
  content: string
  tool?: string
  status?: 'pending' | 'success' | 'error'
  timestamp: number
  details?: {
    input?: {
      query?: string
      queries?: string[]  // 用于 multi_query 和 step_back
      original_query?: string  // 用于 rewrite
      rewritten_query?: string  // 用于 rewrite
      document_ids?: string[]
      args?: Record<string, any>
      [key: string]: any
    }
    output?: {
      chunks?: Array<{
        id: string
        document_id: string
        title: string
        content: string
        score: number
        chunk_index?: number
        level?: number
        // 语义高亮相关字段
        highlighted_sentences?: string[]
        sentence_probabilities?: number[]
        compression_rate?: number
      }>
      count?: number
      summary?: string
    }
    summary?: string
    [key: string]: any
  }
}

// Agent 响应接口
export interface AgentResponse {
  answer: string
  sources: Source[]
  steps: AgentStep[]
  conversationId?: string
}

// Agent API
export const agentApi = {
  // Agent 问答接口
  ask: async (
    question: string,
    folderId: string,
    conversationId: string | undefined,
    taskId?: string,
    options?: {
      folderIds?: string[]
      documentIds?: string[]
      maxIterations?: number
    }
  ): Promise<AgentResponse> => {
    const response = await apiClient.post<AgentResponse>('/agent/ask', {
      question,
      folderId,
      conversationId,
      taskId,
      maxIterations: options?.maxIterations,
      ...(options?.folderIds && { folderIds: options.folderIds }),
      ...(options?.documentIds && { documentIds: options.documentIds })
    }, {
      timeout: 120000  // Agent 执行可能需要更长时间，设置为 120 秒
    })
    return response.data
  },

  // 停止生成
  stopGeneration: async (taskId: string): Promise<{ message: string; taskId: string }> => {
    const response = await apiClient.post<{ message: string; taskId: string }>('/agent/stop', {
      taskId
    })
    return response.data
  },

  // 创建对话（并发送第一个问题）
  createConversation: async (
    folderId: string,
    firstQuestion: string,
    taskId?: string,
    maxIterations?: number
  ): Promise<{
    conversationId: string
    answer: string
    sources: Source[]
    steps: AgentStep[]
  }> => {
    const response = await apiClient.post<{
      conversationId: string
      answer: string
      sources: Source[]
      steps: AgentStep[]
    }>('/agent/conversations', {
      folderId,
      firstQuestion,
      taskId,
      maxIterations
    }, {
      timeout: 120000  // Agent 执行可能需要更长时间，设置为 120 秒
    })
    return response.data as {
      conversationId: string
      answer: string
      sources: Source[]
      steps: AgentStep[]
    }
  },

  // 获取对话列表
  listConversations: async (folderId: string, limit?: number): Promise<{
    conversations: Conversation[]
    total: number
  }> => {
    const response = await apiClient.get<{
      conversations: Conversation[]
      total: number
    }>('/agent/conversations', {
      params: { folderId, limit }
    })
    return response.data as {
      conversations: Conversation[]
      total: number
    }
  },

  // 获取对话详情
  getConversation: async (conversationId: string): Promise<Conversation> => {
    const response = await apiClient.get<Conversation>(`/agent/conversations/${conversationId}`)
    return response.data
  },

  // 删除对话
  deleteConversation: async (conversationId: string): Promise<void> => {
    await apiClient.delete(`/agent/conversations/${conversationId}`)
  }
}
