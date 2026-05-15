import apiClient from './index'
import type { AgentStep } from './agent'

// 消息类型
export type MessageRole = 'user' | 'assistant'

// 消息接口
export interface Message {
  id: string
  role: MessageRole
  content: string
  sources: Source[]
  timestamp: string
  agentSteps?: AgentStep[]  // Agent 思考步骤
  mode?: 'standard' | 'agent'  // 消息模式标记
}

// 引用来源接口
export interface Source {
  id: string
  document_id: string
  document_name: string
  title: string
  content: string
  score: number
}

// 对话接口
export interface Conversation {
  id: string
  title: string
  folderId: string
  createdAt: string
  updatedAt: string
  messages: Message[]
}

// 问答API
export const chatApi = {
  // 提问（使用混合检索）
  ask: async (
    question: string,
    folderId: string,
    conversationId: string | undefined,
    taskId?: string,
    options?: {
      folderIds?: string[]  // 多个知识库ID
      documentIds?: string[]  // 多个文档ID
    }
  ): Promise<{
    answer: string
    sources: Source[]
  }> => {
    const response = await apiClient.post<{
      answer: string
      sources: Source[]
    }>(
      '/hybrid/ask',
      {
        question,
        folderId,
        conversationId,
        taskId,
        ...options
      },
      { timeout: 300000 }
    )
    return response.data
  },

  // 停止生成（使用混合检索）
  stopGeneration: async (taskId: string): Promise<{ message: string; taskId: string }> => {
    const response = await apiClient.post<{ message: string; taskId: string }>('/hybrid/stop', {
      taskId
    })
    return response.data
  },

  // 创建对话（并发送第一个问题，使用混合检索）
  createConversation: async (folderId: string, firstQuestion: string, taskId?: string): Promise<{
    conversationId: string
    answer: string
    sources: Source[]
  }> => {
    const response = await apiClient.post<{
      conversationId: string
      answer: string
      sources: Source[]
    }>(
      '/hybrid/conversations',
      {
        folderId,
        firstQuestion,
        taskId
      },
      { timeout: 300000 }
    )
    return response.data
  },

  // 获取对话列表（使用混合检索）
  listConversations: async (folderId: string, limit?: number): Promise<{
    conversations: Conversation[]
    total: number
  }> => {
    const response = await apiClient.get<{
      conversations: Conversation[]
      total: number
    }>('/hybrid/conversations', {
      params: { folderId, limit }
    })
    return response.data
  },

  // 获取对话详情（使用混合检索）
  getConversation: async (conversationId: string): Promise<Conversation> => {
    const response = await apiClient.get<Conversation>(`/hybrid/conversations/${conversationId}`)
    return response.data
  },

  // 删除对话（使用混合检索）
  deleteConversation: async (conversationId: string): Promise<void> => {
    await apiClient.delete(`/hybrid/conversations/${conversationId}`)
  }
}
