<template>
  <div class="agent-process">
    <n-collapse arrow-placement="right">
      <n-collapse-item>
        <template #header>
          <n-space align="center" size="small">
            <n-icon :component="BrainIcon" color="#18a058" />
            <n-text depth="3" style="font-size: 12px">
              Agent 思考链 ({{ steps.length }} 步)
            </n-text>
            <n-tag v-if="loading" size="small" type="primary" :bordered="false">
              <template #icon><n-spin size="small" /></template>
              思考中...
            </n-tag>
          </n-space>
        </template>

        <n-timeline style="margin-top: 12px; padding: 0 16px;">
          <n-timeline-item
            v-for="(step, index) in steps"
            :key="index"
            :type="getStepType(step)"
            :title="getStepTitle(step)"
            :time="formatTime(step.timestamp)"
          >
            <!-- Thought 步骤 -->
            <div v-if="step.type === 'thought'" class="step-content">
              <n-text depth="3" style="font-size: 12px; white-space: pre-wrap;">
                {{ step.content }}
              </n-text>
            </div>

            <!-- Action 步骤 -->
            <div v-else-if="step.type === 'action'" class="step-content">
              <n-text depth="3" style="font-size: 12px; margin-bottom: 8px; display: block;">
                {{ step.content }}
              </n-text>
              <!-- 显示检索关键词 -->
              <div v-if="step.details?.input?.query || step.details?.input?.queries" class="query-tags">
                <n-tag
                  v-for="(query, idx) in getQueries(step)"
                  :key="idx"
                  size="small"
                  type="info"
                  :bordered="false"
                  style="margin-right: 6px; margin-bottom: 4px;"
                >
                  🔍 {{ query }}
                </n-tag>
              </div>
              <!-- 显示重写前后的查询 -->
              <div v-if="step.details?.input?.original_query && step.details?.input?.rewritten_query" class="query-tags">
                <n-tag size="small" type="warning" :bordered="false" style="margin-right: 6px; margin-bottom: 4px;">
                  原查询: {{ step.details.input.original_query }}
                </n-tag>
                <n-tag size="small" type="success" :bordered="false" style="margin-right: 6px; margin-bottom: 4px;">
                  重写后: {{ step.details.input.rewritten_query }}
                </n-tag>
              </div>
            </div>

            <!-- Observation 步骤 -->
            <div v-else-if="step.type === 'observation'" class="step-content">
              <n-text depth="3" style="font-size: 12px; margin-bottom: 8px; display: block;">
                {{ getObservationSummary(step) }}
              </n-text>
              <!-- 查看详情按钮 -->
              <div v-if="hasChunks(step)" class="detail-section">
                <n-button
                  text
                  type="primary"
                  size="small"
                  @click="toggleDetail(index)"
                  style="margin-bottom: 8px;"
                >
                  {{ expandedDetails.has(index) ? '收起详情' : '查看详情' }}
                </n-button>
                <!-- 详情展开 -->
                <n-collapse-transition :show="expandedDetails.has(index)" style="margin-top: 8px;">
                  <div class="chunks-list">
                    <n-card
                      v-for="(chunk, chunkIdx) in step.details?.output?.chunks"
                      :key="chunkIdx"
                      size="small"
                      style="margin-bottom: 8px;"
                    >
                      <template #header>
                        <n-space align="center" size="small" justify="space-between">
                          <n-space align="center" size="small">
                            <n-text strong style="font-size: 13px;">{{ chunk.title || '无标题' }}</n-text>
                            <n-tag size="tiny" type="info" :bordered="false">
                              相关性: {{ (chunk.score * 100).toFixed(1) }}%
                            </n-tag>
                            <!-- 语义高亮统计信息 -->
                            <n-tag 
                              v-if="chunk.highlighted_sentences && chunk.highlighted_sentences.length > 0" 
                              size="tiny" 
                              type="success" 
                              :bordered="false"
                            >
                              高亮: {{ chunk.highlighted_sentences.length }} 句
                            </n-tag>
                            <n-tag 
                              v-if="chunk.compression_rate !== undefined && chunk.compression_rate > 0" 
                              size="tiny" 
                              type="warning" 
                              :bordered="false"
                            >
                              压缩率: {{ (chunk.compression_rate * 100).toFixed(1) }}%
                            </n-tag>
                          </n-space>
                        </n-space>
                      </template>
                      
                      <!-- 内容模式切换（仅在有高亮句子时显示） -->
                      <div 
                        v-if="hasHighlightedSentences(chunk)" 
                        style="margin-bottom: 12px;"
                      >
                        <n-radio-group
                          :value="getContentMode(index, chunkIdx)"
                          @update:value="(value) => setContentMode(index, chunkIdx, value as 'original' | 'highlighted')"
                          size="small"
                        >
                          <n-radio value="highlighted">高亮内容</n-radio>
                          <n-radio value="original">原始内容</n-radio>
                        </n-radio-group>
                      </div>
                      
                      <!-- 高亮内容模式 -->
                      <div v-if="getContentMode(index, chunkIdx) === 'highlighted' && chunk.highlighted_sentences">
                        <div class="highlighted-sentences">
                          <div
                            v-for="(sentence, sentIdx) in chunk.highlighted_sentences"
                            :key="sentIdx"
                            class="highlighted-sentence"
                          >
                            <n-text depth="3" style="font-size: 12px; line-height: 1.6;">
                              {{ sentence }}
                            </n-text>
                            <!-- 显示句子概率（如果存在） -->
                            <n-tag
                              v-if="chunk.sentence_probabilities && chunk.sentence_probabilities[sentIdx] !== undefined"
                              size="tiny"
                              type="info"
                              :bordered="false"
                              style="margin-left: 8px;"
                            >
                              {{ (chunk.sentence_probabilities[sentIdx] * 100).toFixed(1) }}%
                            </n-tag>
                          </div>
                        </div>
                      </div>
                      
                      <!-- 原始内容模式 -->
                      <div v-else>
                        <n-text depth="3" style="font-size: 12px; white-space: pre-wrap; line-height: 1.6;">
                          {{ truncateContent(chunk.content, 300) }}
                        </n-text>
                      </div>
                      
                      <template #footer>
                        <n-text depth="3" style="font-size: 11px;">
                          文档ID: {{ chunk.document_id }}
                        </n-text>
                      </template>
                    </n-card>
                  </div>
                </n-collapse-transition>
              </div>
            </div>

            <!-- Answer 步骤 -->
            <div v-else-if="step.type === 'answer'" class="step-content">
              <n-text depth="3" style="font-size: 12px; white-space: pre-wrap;">
                {{ step.content }}
              </n-text>
            </div>
          </n-timeline-item>
        </n-timeline>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  NCollapse,
  NCollapseItem,
  NTimeline,
  NTimelineItem,
  NSpace,
  NIcon,
  NText,
  NTag,
  NSpin,
  NButton,
  NCard,
  NCollapseTransition,
  NRadioGroup,
  NRadio
} from 'naive-ui'
import { BulbOutline } from '@vicons/ionicons5'
import type { AgentStep } from '@/api/agent'

const props = defineProps<{
  steps: AgentStep[]
  loading?: boolean
}>()

const BrainIcon = BulbOutline
// 管理展开的详情索引
const expandedDetails = ref<Set<number>>(new Set())

// 管理每个文档块的内容展示模式：'original' | 'highlighted'
// key: `${stepIndex}-${chunkIndex}`, value: 'original' | 'highlighted'
const contentModes = ref<Map<string, 'original' | 'highlighted'>>(new Map())

function toggleDetail(index: number) {
  if (expandedDetails.value.has(index)) {
    expandedDetails.value.delete(index)
  } else {
    expandedDetails.value.add(index)
    // 展开时初始化内容模式
    const step = props.steps[index]
    if (step.details?.output?.chunks) {
      initializeContentMode(index, step.details.output.chunks)
    }
  }
}

function getStepType(step: AgentStep): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (step.status === 'error') return 'error'
  if (step.status === 'pending') return 'warning'
  return 'success'
}

function getStepTitle(step: AgentStep): string {
  const toolName = step.tool ? step.tool.replace('t_', '').replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : ''
  
  switch (step.type) {
    case 'thought':
      return '🧠 思考'
    case 'action':
      return `🛠️ 执行工具${toolName ? `: ${toolName}` : ''}`
    case 'observation':
      return `👀 观察结果${toolName ? ` (${toolName})` : ''}`
    case 'answer':
      return '✅ 生成答案'
    default:
      return '步骤'
  }
}

function formatTime(timestamp: number): string {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

function getQueries(step: AgentStep): string[] {
  if (!step.details?.input) return []
  
  // 优先使用 queries 数组（multi_query, step_back）
  if (step.details.input.queries && Array.isArray(step.details.input.queries)) {
    return step.details.input.queries
  }
  
  // 使用单个 query
  if (step.details.input.query) {
    return [step.details.input.query]
  }
  
  return []
}

function getObservationSummary(step: AgentStep): string {
  if (step.details?.summary) {
    return step.details.summary
  }
  
  if (step.details?.output?.summary) {
    return step.details.output.summary
  }
  
  const count = step.details?.output?.count || 0
  if (count > 0) {
    return `找到 ${count} 个相关片段`
  }
  
  return step.content
}

function hasChunks(step: AgentStep): boolean {
  return !!(step.details?.output?.chunks && step.details.output.chunks.length > 0)
}

function truncateContent(content: string, maxLength: number): string {
  if (!content) return ''
  if (content.length <= maxLength) return content
  return content.substring(0, maxLength) + '...'
}

// 检查文档块是否有高亮句子
function hasHighlightedSentences(chunk: any): boolean {
  return !!(chunk.highlighted_sentences && chunk.highlighted_sentences.length > 0)
}

// 获取内容展示模式
function getContentMode(stepIndex: number, chunkIndex: number): 'original' | 'highlighted' {
  const key = `${stepIndex}-${chunkIndex}`
  const mode = contentModes.value.get(key)
  if (mode) {
    return mode
  }
  // 如果没有设置模式，根据是否有高亮句子决定默认模式
  const step = props.steps[stepIndex]
  const chunk = step.details?.output?.chunks?.[chunkIndex]
  if (chunk && hasHighlightedSentences(chunk)) {
    return 'highlighted'
  }
  return 'original'
}

// 设置内容展示模式
function setContentMode(stepIndex: number, chunkIndex: number, mode: 'original' | 'highlighted') {
  const key = `${stepIndex}-${chunkIndex}`
  contentModes.value.set(key, mode)
}

// 初始化内容模式（当展开详情时，如果有高亮句子，默认使用高亮模式）
function initializeContentMode(stepIndex: number, chunks: any[]) {
  chunks.forEach((chunk, chunkIndex) => {
    const key = `${stepIndex}-${chunkIndex}`
    if (!contentModes.value.has(key) && hasHighlightedSentences(chunk)) {
      contentModes.value.set(key, 'highlighted')
    } else if (!contentModes.value.has(key)) {
      contentModes.value.set(key, 'original')
    }
  })
}
</script>

<style scoped>
.agent-process {
  margin-bottom: 12px;
}

.step-content {
  margin-top: 4px;
}

.query-tags {
  display: flex;
  flex-wrap: wrap;
  margin-top: 6px;
}

.detail-section {
  margin-top: 8px;
}

.chunks-list {
  margin-top: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.highlighted-sentences {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.highlighted-sentence {
  background-color: #fff3cd;
  border-left: 3px solid #ffc107;
  padding: 8px 12px;
  border-radius: 4px;
  line-height: 1.6;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
