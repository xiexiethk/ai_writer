<template>
  <div class="document-view">
    <n-layout has-sider style="height: calc(100vh - 120px)">
      <!-- 左侧：文档项目标签列表 -->
      <n-layout-sider
        bordered
        :width="240"
        content-style="padding: 12px; display: flex; flex-direction: column; overflow: hidden;"
      >
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 4px;">
          <n-text strong style="font-size: 14px;">文档项目</n-text>
          <n-button size="small" type="primary" @click="handleCreateNew">
            <template #icon>
              <n-icon :component="AddIcon" />
            </template>
            新建
          </n-button>
        </div>

        <n-spin :show="isLoadingProjects" style="flex: 1; overflow: hidden;">
          <n-scrollbar style="max-height: calc(100vh - 140px);">
            <div
              v-for="project in projects"
              :key="project.id"
              :class="['project-tab', { 'active': currentProjectId === project.id }]"
            >
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <div
                  style="flex: 1; min-width: 0; cursor: pointer;"
                  @click="loadProject(project)"
                >
                  <n-text
                    :style="{
                      fontSize: '13px',
                      fontWeight: currentProjectId === project.id ? 'bold' : 'normal'
                    }"
                    style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block;"
                  >
                    {{ project.title }}
                  </n-text>
                  <n-text depth="3" style="font-size: 11px; margin-top: 2px;">
                    {{ formatProjectTime(project.updatedAt || project.createdAt) }}
                  </n-text>
                </div>
                <n-button
                  quaternary
                  size="tiny"
                  type="error"
                  style="margin-left: 4px; flex-shrink: 0;"
                  @click.stop="handleDeleteProject(project)"
                >
                  <template #icon>
                    <n-icon :component="TrashIcon" />
                  </template>
                </n-button>
              </div>
            </div>
            <n-empty v-if="projects.length === 0" description="暂无项目" size="small">
              <template #extra>
                <n-button size="small" type="primary" @click="handleCreateNew">
                  创建第一个项目
                </n-button>
              </template>
            </n-empty>
          </n-scrollbar>
        </n-spin>
      </n-layout-sider>

      <!-- 中间：大纲编辑区 -->
      <n-layout-sider
        bordered
        :width="380"
        content-style="display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 16px;"
      >
        <div style="flex-shrink: 0; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <n-text strong>文档大纲</n-text>
            <n-space>
              <n-button
                size="tiny"
                @click="showUploadDrawer = true"
                :disabled="outlineLocked || isParsed"
              >
                <template #icon>
                  <n-icon :component="UploadIcon" />
                </template>
                上传文档
              </n-button>
              <n-button
                v-if="outline.length > 0"
                :type="outlineLocked ? 'warning' : 'primary'"
                size="tiny"
                @click="handleToggleLock"
              >
                {{ outlineLocked ? '解锁大纲' : '确认并锁定' }}
              </n-button>
            </n-space>
          </div>

          <n-alert v-if="outline.length === 0" type="info" size="small">
            <template #header>
              <n-space align="center">
                <n-text>开始创建纲要</n-text>
              </n-space>
            </template>
            <n-space vertical>
              <n-text>方式1：在底部输入框输入需求，AI 生成大纲</n-text>
              <n-text>方式2：右侧"上传文档"，导入Word中的大纲</n-text>
            </n-space>
          </n-alert>
          <n-alert v-else-if="!outlineLocked" type="info" size="small">
            大纲未锁定，可编辑调整
          </n-alert>
          <n-alert v-else type="success" size="small">
            大纲已锁定
          </n-alert>
        </div>

        <!-- 大纲树可滚动区域 -->
        <div style="flex: 1; overflow-y: auto;">
          <div v-if="outline.length > 0">
            <n-tree
              :data="normalizedOutline"
              :show-line="true"
              :selectable="true"
              :expanded-keys="expandedKeys"
              :selected-keys="selectedKeys"
              :render-label="renderTreeLabel"
              key-field="key"
              label-field="label"
              children-field="children"
              @update:selected-keys="handleSelectNode"
              @update:expanded-keys="expandedKeys = $event as string[]"
            />
          </div>
        </div>

        <!-- 编辑按钮固定在底部 -->
        <div v-if="outline.length > 0 && !outlineLocked" style="flex-shrink: 0; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--n-border-color);">
          <n-space>
            <n-button size="tiny" @click="handleAddNode">添加节点</n-button>
            <n-button size="tiny" @click="handleDeleteNode" :disabled="!selectedNode">删除</n-button>
            <n-button size="tiny" @click="openRenameModal" :disabled="!selectedNode">重命名</n-button>
          </n-space>
        </div>
      </n-layout-sider>

      <!-- 右侧：内容生成区 -->
      <n-layout content-style="display: flex; flex-direction: column; height: 100%; overflow: hidden;">
        <!-- 顶部操作按钮固定区域 -->
        <div v-if="generatedSections.length > 0" style="flex-shrink: 0; padding: 16px 24px; border-bottom: 1px solid var(--n-border-color);">
          <n-space>
            <n-button
              type="primary"
              @click="startGenerating"
            >
              {{ isGeneratingAll ? '停止生成' : '继续生成' }}
            </n-button>
            <n-button
              @click="openProjectConversationDrawer"
              :disabled="!currentProjectId"
            >
              项目助手
            </n-button>
            <n-button
              @click="handleExportWord"
              :disabled="isExporting"
              :loading="isExporting"
            >
              {{ isExporting ? '导出中...' : '导出 Word' }}
            </n-button>
            <n-button
              @click="previewMode = !previewMode"
              :disabled="!currentProjectId"
            >
              {{ previewMode ? '编辑模式' : '预览模式' }}
            </n-button>
          </n-space>
        </div>

        <!-- 内容滚动区域 -->
        <div style="flex: 1; overflow-y: auto; padding: 24px;">
          <!-- 未锁定且未生成内容时的提示 -->
          <n-card v-if="!outlineLocked && generatedSections.length === 0 && outline.length > 0" size="small">
            <n-space vertical>
              <n-text>请先锁定大纲，然后开始生成内容</n-text>
            </n-space>
          </n-card>

          <!-- 空项目提示 -->
          <n-card v-if="outline.length === 0" size="small">
            <n-space vertical>
              <n-text>在下方输入研究主题，选择知识库，开始生成文档大纲</n-text>
            </n-space>
          </n-card>

          <!-- 生成按钮和导出按钮 -->
          <n-card v-if="outlineLocked && generatedSections.length === 0" size="small">
            <n-space vertical>
              <n-text>大纲已锁定，开始生成文档内容</n-text>
              <n-space>
                <n-button
                  type="primary"
                  @click="startGenerating"
                >
                  {{ isGeneratingAll ? '停止生成' : '开始生成全部内容' }}
                </n-button>
                <n-button
                  @click="handleExportWord"
                  :disabled="isGeneratingAll"
                >
                  导出 Word
                </n-button>
              </n-space>
            </n-space>
          </n-card>

          <!-- 内容显示 -->
          <div v-if="!previewMode">
            <div
              v-for="section in generatedSections"
              :key="section.sectionId"
              :id="`section-${section.sectionId}`"
              style="margin-bottom: 32px; scroll-margin-top: 80px;"
            >
              <n-card size="small">
                <template #header>
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 8px; flex: 1;">
                      <n-text v-if="!section.isEditing" strong style="font-size: 18px;">{{ section.title }}</n-text>
                      <n-input
                        v-else
                        v-model:value="section.editingTitle"
                        size="small"
                        @blur="handleSectionTitleBlur(section)"
                        @keydown.enter="handleSectionTitleEnter(section)"
                        ref="titleInput"
                        style="max-width: 300px;"
                      />
                      <n-button
                        v-if="!outlineLocked"
                        text
                        size="tiny"
                        @click="toggleSectionEdit(section)"
                      >
                        {{ section.isEditing ? '取消' : '编辑' }}
                      </n-button>
                    </div>
                    <n-space>
                      <n-button
                        size="tiny"
                        @click="openSectionConversationDrawer(section)"
                      >
                        本章助手
                      </n-button>
                      <n-dropdown
                        v-if="section.paragraphs && section.paragraphs.length > 0"
                        trigger="click"
                        :options="[
                          { label: '直接重新生成', key: 'direct' },
                          { label: '自定义需求重新生成', key: 'custom' }
                        ]"
                        @select="(key: string) => handleRegenerateSelect(key, section)"
                        :disabled="isGeneratingAll"
                      >
                        <n-button
                          size="tiny"
                          :loading="regeneratingSectionId === section.sectionId"
                          :disabled="isGeneratingAll"
                        >
                          重新生成
                        </n-button>
                      </n-dropdown>
                    </n-space>
                  </div>
                </template>

                <div v-if="!section.paragraphs || section.paragraphs.length === 0">
                  <n-space>
                    <n-button size="small" @click="generateSection(section)" :loading="generatingSectionId === section.sectionId">
                      生成内容
                    </n-button>
                  </n-space>
                </div>

                <div v-else>
                  <!-- 获取所有段落版本 -->
                  <div
                    v-for="(paraInfo, idx) in getParagraphsWithVersions(section)"
                    :key="paraInfo.key"
                    style="margin-bottom: 16px;"
                  >
                    <MarkdownParagraph
                      :ref="el => setParagraphRef(el, section.sectionId, idx)"
                      :content="paraInfo.content"
                      :isEditing="paraInfo.isCurrent"
                      :backgroundColor="paraInfo.isCurrent ? 'var(--n-color)' : 'var(--n-color-modal)'"
                      @blur="paraInfo.isCurrent ? handleParagraphEdit(section, paraInfo, $event) : null"
                    />

                    <!-- 版本信息和操作按钮 -->
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
                      <n-space>
                        <n-text v-if="paraInfo.isCurrent" depth="3" style="font-size: 11px;">
                          当前版本
                        </n-text>
                        <n-text v-else depth="3" style="font-size: 11px;">
                          历史版本 {{ paraInfo.timestamp ? new Date(paraInfo.timestamp).toLocaleString() : '' }}
                        </n-text>
                      </n-space>
                      <n-button
                        v-if="!paraInfo.isCurrent"
                        size="tiny"
                        type="primary"
                        @click="restoreParagraphVersion(section, paraInfo)"
                      >
                        保留此版本
                      </n-button>
                    </div>

                    <!-- RAG引用 -->
                    <div v-if="paraInfo.sources && paraInfo.sources.length > 0" style="margin-top: 8px;">
                      <n-collapse arrow-placement="right">
                        <n-collapse-item title="引用来源" name="sources">
                          <div
                            v-for="source in paraInfo.sources"
                            :key="source.id"
                            style="margin-bottom: 8px; padding: 8px; background: var(--n-color-modal); border-radius: 4px;"
                          >
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                              <n-text strong style="font-size: 12px;">{{ source.document_name }}</n-text>
                              <n-tag size="tiny" type="info">
                                {{ (source.score * 100).toFixed(1) }}%
                              </n-tag>
                            </div>
                            <n-text depth="3" style="font-size: 12px; margin-bottom: 4px;">{{ source.title }}</n-text>
                            <n-text
                              depth="2"
                              style="font-size: 12px; cursor: pointer; color: var(--n-color-target);"
                              @click="showSourceSource(source)"
                            >
                              点击查看原文 →
                            </n-text>
                          </div>
                        </n-collapse-item>
                      </n-collapse>
                    </div>
                  </div>
                </div>
              </n-card>
            </div>
          </div>

          <!-- 预览模式 -->
          <div v-else style="display: flex; flex-direction: column; height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-shrink: 0;">
              <n-text>PDF 预览（打印或保存为 PDF）</n-text>
              <n-button
                type="primary"
                @click="handlePrintPdf"
              >
                打印/导出 PDF
              </n-button>
            </div>
            <div style="flex: 1; min-height: 0;">
              <iframe
                v-if="currentProjectId"
                :src="documentProjectApi.getPreviewHtmlUrl(currentProjectId)"
                style="width: 100%; height: 100%; border: 1px solid var(--n-border-color); border-radius: 4px;"
              ></iframe>
            </div>
          </div>
        </div>

        <!-- 底部：研究主题对话框（固定不滚动） -->
        <div style="border-top: 1px solid var(--n-border-color); padding: 16px; background: var(--n-color); flex-shrink: 0;">
          <!-- 知识库选择区域 -->
          <div style="margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <n-text depth="3" style="font-size: 12px;">知识库:</n-text>

              <!-- 已选择的标签 -->
              <n-tag
                v-for="folderId in selectedFolderIds"
                :key="folderId"
                type="primary"
                size="small"
                closable
                :disabled="outline.length > 0 && outlineLocked"
                @close="handleRemoveFolder(folderId)"
                style="margin: 2px;"
              >
                {{ getFolderName(folderId) }}
              </n-tag>

              <!-- 添加按钮 -->
              <n-dropdown
                trigger="click"
                :options="folderOptions.filter(opt => !selectedFolderIds.includes(opt.value))"
                placement="top-start"
                @select="(key: string) => { console.log('下拉菜单选择 key:', key); handleAddFolder(key) }"
              >
                <n-button
                  size="small"
                  :disabled="(outline.length > 0 && outlineLocked) || selectedFolderIds.length >= folderOptions.length"
                  style="margin: 2px;"
                >
                  <template #icon>
                    <span style="font-size: 16px; font-weight: bold;">+</span>
                  </template>
                </n-button>
              </n-dropdown>

              <n-text v-if="selectedFolderIds.length === 0" depth="3" style="font-size: 12px;">
                点击 + 添加知识库
              </n-text>
            </div>
          </div>

          <div style="display: flex; gap: 8px;">
            <n-input
              v-model:value="topicInput"
              type="textarea"
              placeholder="输入研究主题或需求描述，例如：撰写一篇关于计算机视觉中目标检测算法的综述文档"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :disabled="isGenerating || (outline.length > 0 && outlineLocked)"
              @keydown.enter.ctrl.prevent="handleGenerate"
            />
            <n-button
              type="primary"
              @click="handleGenerate"
              :loading="isGenerating"
              :disabled="!topicInput.trim() || selectedFolderIds.length === 0 || (outline.length > 0 && outlineLocked)"
              style="align-self: flex-end;"
            >
              {{ isGenerating ? '生成中...' : '发送' }}
            </n-button>
          </div>

          <n-text depth="3" style="font-size: 12px; margin-top: 8px; display: block;">
            提示：按 Ctrl + Enter 快速发送
          </n-text>
        </div>
      </n-layout>
    </n-layout>

    <n-drawer v-model:show="showConversationDrawer" :width="560" placement="right">
      <n-drawer-content :title="conversationDrawerTitle" closable>
        <div style="display: flex; flex-direction: column; height: 100%;">
          <div style="flex-shrink: 0; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px;">
              <n-space align="center">
                <n-tag size="small" :type="conversationScopeType === 'project' ? 'info' : 'success'">
                  {{ conversationScopeType === 'project' ? '项目级' : '章节级' }}
                </n-tag>
                <n-text depth="3">{{ conversationScopeTitle }}</n-text>
              </n-space>
              <n-button size="small" @click="createConversationForCurrentScope" :disabled="isLoadingConversationList">
                新建对话
              </n-button>
            </div>

            <n-spin :show="isLoadingConversationList">
              <n-scrollbar x-scrollable style="white-space: nowrap;">
                <n-space>
                  <n-button
                    v-for="conversation in conversationList"
                    :key="conversation.id"
                    size="small"
                    :type="activeConversation?.id === conversation.id ? 'primary' : 'default'"
                    @click="selectConversation(conversation.id)"
                  >
                    {{ conversation.title }}
                  </n-button>
                </n-space>
              </n-scrollbar>
            </n-spin>
          </div>

          <n-alert
            v-if="activeConversation?.rollingSummary"
            type="info"
            size="small"
            :closable="false"
            style="margin-bottom: 12px; flex-shrink: 0;"
          >
            已启用滚动摘要，历史消息会在预算超限时压缩。
          </n-alert>

          <div style="flex: 1; min-height: 0; border: 1px solid var(--n-border-color); border-radius: 8px; padding: 12px;">
            <n-spin :show="isLoadingConversationDetail">
              <n-scrollbar style="height: 100%;">
                <div v-if="activeConversation && activeConversation.messages.length > 0">
                  <div
                    v-for="messageItem in activeConversation.messages"
                    :key="messageItem.id"
                    :style="{
                      display: 'flex',
                      justifyContent: messageItem.role === 'user' ? 'flex-end' : 'flex-start',
                      marginBottom: '12px'
                    }"
                  >
                    <div
                      :style="{
                        maxWidth: '88%',
                        padding: '10px 12px',
                        borderRadius: '10px',
                        background: messageItem.role === 'user' ? 'var(--n-color-target)' : 'var(--n-color-modal)',
                        color: messageItem.role === 'user' ? '#fff' : 'inherit'
                      }"
                    >
                      <div style="font-size: 12px; opacity: 0.8; margin-bottom: 6px;">
                        {{ messageItem.role === 'user' ? '你' : '助手' }}
                        · {{ formatConversationTime(messageItem.timestamp) }}
                      </div>
                      <div style="white-space: pre-wrap; line-height: 1.7;">
                        {{ messageItem.content }}
                      </div>
                      <div
                        v-if="messageItem.role === 'assistant' && messageItem.contextMeta"
                        style="margin-top: 8px; font-size: 12px; opacity: 0.85;"
                      >
                        摘要={{ messageItem.contextMeta.usedSummary ? '是' : '否' }}
                        · 最近={{ messageItem.contextMeta.recentTurns }}
                        · 召回={{ messageItem.contextMeta.retrievedMemories }}
                        · 截断={{ messageItem.contextMeta.truncated ? '是' : '否' }}
                        · 估算输入={{ messageItem.contextMeta.estimatedInputTokens }}
                      </div>
                    </div>
                  </div>
                </div>
                <n-empty v-else description="还没有对话内容，先发一条消息开始写作协作" size="small" />
              </n-scrollbar>
            </n-spin>
          </div>

          <div style="flex-shrink: 0; margin-top: 12px;">
            <n-space vertical>
              <n-radio-group v-model:value="conversationApplyMode">
                <n-radio-button value="suggest_only">仅建议</n-radio-button>
                <n-radio-button value="apply_to_section">应用到章节</n-radio-button>
              </n-radio-group>

              <n-select
                v-if="conversationApplyMode === 'apply_to_section' && conversationScopeType === 'project'"
                v-model:value="conversationTargetSectionId"
                :options="conversationSectionOptions"
                placeholder="选择要应用的章节"
                clearable
              />

              <n-text v-if="conversationApplyMode === 'apply_to_section' && conversationScopeType === 'section'" depth="3" style="font-size: 12px;">
                当前会话会直接将结果应用到章节：{{ conversationScopeTitle }}
              </n-text>

              <n-input
                v-model:value="conversationInput"
                type="textarea"
                placeholder="例如：请把本章改得更学术、更精炼，补充方法对比，并保留已有结论。"
                :autosize="{ minRows: 3, maxRows: 6 }"
                @keydown.enter.ctrl.prevent="sendConversationMessage"
              />

              <div style="display: flex; justify-content: space-between; align-items: center;">
                <n-text depth="3" style="font-size: 12px;">
                  Ctrl + Enter 发送
                </n-text>
                <n-button
                  type="primary"
                  :loading="isSendingConversationMessage"
                  :disabled="!conversationInput.trim()"
                  @click="sendConversationMessage"
                >
                  发送
                </n-button>
              </div>
            </n-space>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <!-- 重命名弹窗 -->
    <n-modal v-model:show="showRenameModal" preset="dialog" title="重命名节点">
      <n-input
        v-model:value="newNodeLabel"
        placeholder="输入新的标题"
        @keydown.enter="handleRenameNode"
      />
      <template #action>
        <n-space>
          <n-button @click="showRenameModal = false">取消</n-button>
          <n-button type="primary" @click="handleRenameNode">确定</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Word 文档上传抽屉 -->
    <n-drawer v-model:show="showUploadDrawer" :width="500" placement="right">
      <n-drawer-content title="上传 Word 文档" closable>
        <n-space vertical size="large">
          <n-alert type="info" :closable="false">
            上传 Word 文档后，系统会自动解析文档结构，提取大纲和正文内容到左侧编辑区。如果不上传，可直接在底部输入框输入需求生成文档。
          </n-alert>

          <n-spin :show="isUploading || isParsing">
            <n-upload
              :custom-request="handleWordUpload"
              :show-file-list="false"
              accept=".doc,.docx"
              :max="1"
              :disabled="isParsing"
            >
              <n-upload-dragger>
                <div style="margin-bottom: 12px">
                  <n-icon size="48" :depth="3">
                    <CloudUploadIcon />
                  </n-icon>
                </div>
                <n-text style="font-size: 16px">
                  点击或拖拽 Word 文档到此区域上传
                </n-text>
                <n-p depth="3" style="margin: 8px 0 0 0">
                  支持 .doc、.docx 格式
                </n-p>
              </n-upload-dragger>
            </n-upload>
          </n-spin>

          <div v-if="uploadedDocument" style="margin-top: 12px;">
            <n-text>已上传: {{ uploadedDocument.fileName }}</n-text>
            <n-divider />
            <n-space>
              <n-button
                type="primary"
                @click="confirmUploadDocument"
                :loading="isParsing"
                :disabled="isParsed"
              >
                {{ isParsed ? '已导入' : '确认导入' }}
              </n-button>
              <n-button @click="clearUpload" :disabled="isParsing">
                清除
              </n-button>
            </n-space>
          </div>

          <n-divider />

          <n-text depth="3" style="font-size: 12px;">
            提示：不上传文档也可在底部输入框中输入需求来生成文档
          </n-text>
        </n-space>
      </n-drawer-content>
    </n-drawer>

    <!-- 来源查看抽屉 -->
    <n-drawer v-model:show="showSourceDrawer" :width="700" placement="right">
      <n-drawer-content title="原文片段" closable>
        <template v-if="selectedSource">
          <n-descriptions :column="1" bordered size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="文档名称">
              {{ selectedSource.document_name }}
            </n-descriptions-item>
            <n-descriptions-item label="章节标题">
              {{ selectedSource.title }}
            </n-descriptions-item>
            <n-descriptions-item label="相似度">
              <n-progress
                type="line"
                :percentage="parseFloat((selectedSource.score * 100).toFixed(1))"
                :show-indicator="true"
              />
            </n-descriptions-item>
          </n-descriptions>

          <n-divider />

          <n-card size="small" title="内容">
            <n-p style="white-space: pre-wrap; line-height: 1.8;">
              {{ selectedSource.content }}
            </n-p>
          </n-card>
        </template>
      </n-drawer-content>
    </n-drawer>

    <!-- 自定义需求对话框 -->
    <n-modal v-model:show="showCustomPromptDialog" preset="dialog" title="自定义生成需求">
      <n-space vertical>
        <n-text>请输入您的特殊需求，AI将根据您的需求生成内容：</n-text>
        <n-input
          v-model:value="customPromptInput"
          type="textarea"
          placeholder="例如：更加详细地介绍技术细节、增加实际案例分析、调整语言风格等..."
          :rows="4"
          maxlength="500"
          show-count
        />
      </n-space>
      <template #action>
        <n-space>
          <n-button @click="showCustomPromptDialog = false">取消</n-button>
          <n-button type="primary" @click="confirmCustomPrompt" :loading="!!regeneratingSectionId">
            开始生成
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, h, watch } from 'vue'
import { useMessage, NText, NScrollbar, NRadioButton, NRadioGroup } from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { documentApi } from '@/api/document'
import {
  documentProjectApi,
  type GeneratedParagraph,
  type OutlineNode,
  type ReportConversation,
  type Source,
} from '@/api/documentProject'
import {
  AddOutline as AddIcon,
  TrashOutline as TrashIcon,
  CloudUploadOutline as CloudUploadIcon,
  CloudUploadOutline as UploadIcon
} from '@vicons/ionicons5'
import MarkdownParagraph from '@/components/MarkdownParagraph.vue'

const message = useMessage()

// Word 文档上传相关
const showUploadDrawer = ref(false)
const uploadedDocument = ref<any>(null)
const isUploading = ref(false)
const isParsing = ref(false)
const isParsed = ref(false)

// 项目列表相关
const projects = ref<any[]>([])
const isLoadingProjects = ref(false)

// 自定义渲染节点标签
function renderTreeLabel({ option }: any) {
  const isSelected = selectedKeys.value.length === 1 && selectedKeys.value[0] === option.key
  console.log('renderTreeLabel for', option.key, 'isSelected:', isSelected, 'selectedKeys:', selectedKeys.value)

  return h(
    'div',
    {
      style: {
        padding: isSelected ? '4px 8px' : '4px 8px',
        borderRadius: '4px',
        // 使用 rgba 来控制背景色透明度，而不是整个元素的 opacity
        backgroundColor: isSelected ? 'rgba(24, 160, 88, 0.15)' : 'transparent',
        fontWeight: isSelected ? 'bold' : 'normal',
        margin: '2px 0',
        width: '100%'
      }
    },
    [option.label]
  )
}

const folders = ref<any[]>([])
const selectedFolderIds = ref<string[]>([])
const topicInput = ref('')
const isLoadingFolders = ref(false)
const isGenerating = ref(false)

const outlineGenerated = ref(false)
const outlineLocked = ref(false)
const outline = ref<OutlineNode[]>([])
const currentProjectId = ref<string | null>(null)

const expandedKeys = ref<string[]>([])
const selectedKeys = ref<string[]>([])
const selectedNode = ref<OutlineNode | null>(null)
const selectedKey = ref<string>('')

const showRenameModal = ref(false)
const newNodeLabel = ref('')

const generatedSections = ref<any[]>([])
const isGeneratingAll = ref(false)
const generatingSectionId = ref<string | null>(null)
const regeneratingSectionId = ref<string | null>(null)
const isExporting = ref(false)

const paragraphRefs = ref<Map<string, any>>(new Map())
const showSourceDrawer = ref(false)
const selectedSource = ref<Source | null>(null)

// 预览模式
const previewMode = ref(false)

// 自定义需求对话框
const showCustomPromptDialog = ref(false)
const customPromptInput = ref('')
const regeneratingSection = ref<any>(null)

// 写作会话抽屉
const showConversationDrawer = ref(false)
const conversationScopeType = ref<'project' | 'section'>('project')
const conversationScopeId = ref<string>('')
const conversationScopeTitle = ref('')
const conversationList = ref<ReportConversation[]>([])
const activeConversation = ref<ReportConversation | null>(null)
const isLoadingConversationList = ref(false)
const isLoadingConversationDetail = ref(false)
const isSendingConversationMessage = ref(false)
const conversationInput = ref('')
const conversationApplyMode = ref<'suggest_only' | 'apply_to_section'>('suggest_only')
const conversationTargetSectionId = ref<string | null>(null)

const conversationDrawerTitle = computed(() => {
  return conversationScopeType.value === 'project' ? '项目写作助手' : '章节写作助手'
})

const conversationSectionOptions = computed(() => {
  return generatedSections.value.map(section => ({
    label: section.title,
    value: section.sectionId
  }))
})

// 为 n-tree 组件规范化的数据（将 id 映射为 key）
const normalizedOutline = computed(() => {
  const normalizeNode = (node: OutlineNode): any => {
    const hasChildren = node.children && node.children.length > 0
    return {
      key: node.id,
      label: node.label,
      children: hasChildren ? node.children.map(normalizeNode) : undefined
    }
  }
  const result = outline.value.map(normalizeNode)
  console.log('normalizedOutline:', JSON.stringify(result, null, 2))
  return result
})

const folderOptions = computed(() => {
  return folders.value.map(folder => ({
    label: folder.name,
    key: folder.id,
    value: folder.id
  }))
})

// 获取知识库名称
function getFolderName(folderId: string) {
  const folder = folders.value.find(f => f.id === folderId)
  return folder ? folder.name : folderId
}

// 监控选择的知识库变化
watch(selectedFolderIds, (newVal) => {
  console.log('selectedFolderIds 变化:', newVal)
  console.log('folders 数据:', folders.value)
}, { deep: true })

// 添加知识库
function handleAddFolder(value: string) {
  console.log('添加知识库:', value)
  console.log('当前已选择:', selectedFolderIds.value)
  if (!selectedFolderIds.value.includes(value)) {
    selectedFolderIds.value.push(value)
    console.log('添加后的已选择:', selectedFolderIds.value)
  }
}

// 移除知识库
function handleRemoveFolder(folderId: string) {
  const index = selectedFolderIds.value.indexOf(folderId)
  if (index > -1) {
    selectedFolderIds.value.splice(index, 1)
  }
}

async function loadFolders() {
  try {
    isLoadingFolders.value = true
    const result = await documentApi.listFolders()
    folders.value = result
    console.log('知识库列表加载成功:', result)
  } catch (error) {
    message.error('加载知识库列表失败')
    console.error('加载知识库失败:', error)
  } finally {
    isLoadingFolders.value = false
  }
}

async function handleGenerate() {
  const topic = topicInput.value.trim()
  if (!topic) {
    message.warning('请输入研究主题')
    return
  }
  if (selectedFolderIds.value.length === 0) {
    message.warning('请选择至少一个知识库')
    return
  }

  try {
    isGenerating.value = true

    console.log('准备创建项目，主题:', topic)
    console.log('选择的知识库ID:', selectedFolderIds.value)
    console.log('选择的知识库详情:', selectedFolderIds.value.map(id => getFolderName(id)))

    // 1. 创建项目
    const project = await documentProjectApi.create({
      title: topic,
      folderIds: selectedFolderIds.value
    })
    currentProjectId.value = project.id
    console.log('项目创建成功，ID:', project.id)

    // 2. 生成大纲
    const updatedProject = await documentProjectApi.generateOutline(project.id, topic)

    // 3. 更新界面状态
    outline.value = updatedProject.outline || []
    console.log('原始 outline:', JSON.stringify(outline.value, null, 2))
    outlineGenerated.value = true
    outlineLocked.value = updatedProject.outlineLocked || false

    // 展开所有节点
    expandAllNodes()

    message.success('大纲生成成功')
    topicInput.value = ''

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    console.error('生成大纲失败，完整错误:', error)
    console.error('响应数据:', error.response?.data)
    const errorMsg = error.response?.data?.detail
      ? error.response.data.detail
      : (error.message || '生成大纲失败')
    message.error(typeof errorMsg === 'string' ? errorMsg : '生成大纲失败，请查看控制台')
  } finally {
    isGenerating.value = false
  }
}

// 切换锁定/解锁状态
async function handleToggleLock() {
  if (!currentProjectId.value || outline.value.length === 0) return

  try {
    const newLockedState = !outlineLocked.value

    await documentProjectApi.updateOutline(
      currentProjectId.value,
      outline.value,
      newLockedState
    )

    outlineLocked.value = newLockedState

    if (newLockedState) {
      message.success('大纲已锁定')
    } else {
      message.success('大纲已解锁，现在可以编辑')
    }

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '切换锁定状态失败')
    console.error(error)
  }
}

function handleSelectNode(keys: string[]) {
  console.log('handleSelectNode called with keys:', keys)
  console.log('selectedKeys before:', selectedKeys.value)

  if (keys.length > 0) {
    // 只保留第一个选中的 key，忽略其他
    const firstKey = keys[0]
    selectedKey.value = firstKey
    selectedKeys.value = [firstKey]  // 只保留一个 key
    selectedNode.value = findNodeById(outline.value, firstKey)

    console.log('selectedKeys after:', selectedKeys.value)
    console.log('selectedNode:', selectedNode.value)

    // 跳转到对应章节
    const node = findNodeById(outline.value, firstKey)
    if (node) {
      const sectionElement = document.getElementById(`section-${node.id}`)
      if (sectionElement) {
        sectionElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  } else {
    selectedKey.value = ''
    selectedKeys.value = []
    selectedNode.value = null
  }
}

// 扁平化大纲获取所有章节
function flattenOutline(nodes: OutlineNode[], parentPath: string[] = []): any[] {
  const sections: any[] = []
  for (const node of nodes) {
    const currentPath = [...parentPath, node.label]
    sections.push({
      id: node.id,
      title: node.label,
      sectionId: node.id,
      contextSections: parentPath,
      paragraphs: null,
      isEditing: false,
      editingTitle: ''
    })
    if (node.children && node.children.length > 0) {
      sections.push(...flattenOutline(node.children, currentPath))
    }
  }
  return sections
}

function hasGeneratedParagraphs(section: any): boolean {
  return !!(section?.paragraphs && Array.isArray(section.paragraphs) && section.paragraphs.length > 0)
}

// 开始生成全部内容
async function startGenerating() {
  // 如果正在生成，则是停止操作
  if (isGeneratingAll.value) {
    isGeneratingAll.value = false
    message.success('已停止生成')
    return
  }

  if (!currentProjectId.value) return

  const allSections = flattenOutline(outline.value)
  const existingSections = new Map(
    generatedSections.value.map(section => [section.sectionId, section])
  )

  generatedSections.value = allSections.map(section => {
    const existing = existingSections.get(section.sectionId)
    return {
      ...section,
      paragraphs: existing?.paragraphs || null,
      isEditing: existing?.isEditing || false,
      editingTitle: existing?.editingTitle || ''
    }
  })

  const pendingSections = generatedSections.value.filter(section => !hasGeneratedParagraphs(section))
  if (pendingSections.length === 0) {
    message.info('当前项目的所有章节都已生成完成')
    return
  }

  isGeneratingAll.value = true

  // 逐个生成
  for (const section of pendingSections) {
    // 检查是否被停止
    if (!isGeneratingAll.value) {
      message.info('生成已停止')
      break
    }
    await generateSection(section)
    // 添加小延迟，避免请求过于频繁
    await new Promise(resolve => setTimeout(resolve, 500))
  }

  // 检查是否正常完成
  const completed = isGeneratingAll.value
  isGeneratingAll.value = false

  if (completed) {
    message.success('全部内容生成完成')
  }

  // 刷新项目列表
  await loadProjects()
}

// 生成单个章节
async function generateSection(section: any) {
  if (!currentProjectId.value) return
  if (hasGeneratedParagraphs(section)) return

  generatingSectionId.value = section.sectionId

  try {
    const result = await documentProjectApi.generateContent(
      currentProjectId.value,
      section.sectionId,
      section.title,
      section.contextSections
    )

    // 更新 sections
    const sectionIndex = generatedSections.value.findIndex(s => s.sectionId === section.sectionId)
    if (sectionIndex >= 0) {
      generatedSections.value[sectionIndex].paragraphs = [result]
    }

    message.success(`"${section.title}" 生成完成`)
  } catch (error: any) {
    message.error(`"${section.title}" 生成失败: ${error.response?.data?.detail || error.message}`)
    console.error(error)
  } finally {
    generatingSectionId.value = null
  }
}

// 重新生成章节
async function regenerateSection(section: any, customPrompt?: string) {
  if (!currentProjectId.value) return

  regeneratingSectionId.value = section.sectionId

  try {
    const result = await documentProjectApi.regenerateParagraph(
      currentProjectId.value,
      section.sectionId,
      section.title,
      section.contextSections,
      customPrompt
    )

    // 更新 paragraphs（添加新段落到末尾）
    const sectionIndex = generatedSections.value.findIndex(s => s.sectionId === section.sectionId)
    if (sectionIndex >= 0) {
      if (!generatedSections.value[sectionIndex].paragraphs) {
        generatedSections.value[sectionIndex].paragraphs = []
      }
      generatedSections.value[sectionIndex].paragraphs.push(result)
    }

    message.success(`"${section.title}" 重新生成完成`)

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    message.error(`"${section.title}" 重新生成失败: ${error.response?.data?.detail || error.message}`)
    console.error(error)
  } finally {
    regeneratingSectionId.value = null
  }
}

// 处理重新生成下拉菜单选择
function handleRegenerateSelect(key: string, section: any) {
  if (key === 'direct') {
    // 直接重新生成
    regenerateSection(section)
  } else if (key === 'custom') {
    // 显示自定义需求对话框
    regeneratingSection.value = section
    customPromptInput.value = ''
    showCustomPromptDialog.value = true
  }
}

// 确认自定义需求并开始生成
async function confirmCustomPrompt() {
  if (!regeneratingSection.value) return

  const customPrompt = customPromptInput.value.trim()
  // 如果有输入才传递，否则传undefined
  const promptToUse = customPrompt ? customPrompt : undefined

  console.log('开始自定义生成，需求:', promptToUse)
  console.log('当前章节:', regeneratingSection.value)

  try {
    await regenerateSection(regeneratingSection.value, promptToUse)
    // 关闭对话框
    showCustomPromptDialog.value = false
    regeneratingSection.value = null
    customPromptInput.value = ''
  } catch (error) {
    console.error('自定义生成失败:', error)
    message.error('生成失败，请重试')
  }
}

// 设置段落引用
function setParagraphRef(el: any, sectionId: string, index: number) {
  if (el) {
    paragraphRefs.value.set(`${sectionId}-${index}`, el)
  }
}

// 获取段落及其所有版本
function getParagraphsWithVersions(section: any) {
  const paragraphs = section.paragraphs || []
  const result: any[] = []

  // 如果没有段落，返回空数组
  if (paragraphs.length === 0) {
    return result
  }

  // 获取最新段落作为当前版本
  const currentPara = paragraphs[paragraphs.length - 1]
  result.push({
    key: currentPara.paragraph_id,
    paragraph_id: currentPara.paragraph_id,
    content: currentPara.content,
    timestamp: currentPara.timestamp,
    sources: currentPara.sources,
    isCurrent: true,
    versionIndex: -1  // 当前版本，不在 versions 数组中
  })

  // 获取历史版本（从当前段落的 versions 字段）
  const versions = currentPara.versions || []
  versions.forEach((version: any, vIdx: number) => {
    result.push({
      key: `${currentPara.paragraph_id}-v${vIdx}`,
      paragraph_id: currentPara.paragraph_id,
      content: version.content,
      timestamp: version.timestamp,
      sources: version.sources || [],
      isCurrent: false,
      versionIndex: vIdx
    })
  })

  // 历史版本在前面，当前版本在后面
  return result.reverse()
}

// 段落编辑处理
async function handleParagraphEdit(section: any, paraInfo: any, event: Event) {
  const target = event.target as HTMLElement
  const content = target.innerText

  if (!currentProjectId.value) return

  try {
    const response = await documentProjectApi.updateParagraph(
      currentProjectId.value,
      section.sectionId,
      paraInfo.paragraph_id,
      content
    )

    if (response) {
      // 更新本地数据
      const sectionIndex = generatedSections.value.findIndex(s => s.sectionId === section.sectionId)
      if (sectionIndex >= 0 && generatedSections.value[sectionIndex].paragraphs) {
        const paragraphs = generatedSections.value[sectionIndex].paragraphs
        const paraIndex = paragraphs.findIndex((p: any) => p.paragraph_id === paraInfo.paragraph_id)
        if (paraIndex >= 0) {
          paragraphs[paraIndex].content = content
          paragraphs[paraIndex].timestamp = new Date().toISOString()
        }
      }
    }

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    message.error(`保存失败: ${error.response?.data?.detail || error.message}`)
    console.error(error)
  }
}

// 恢复段落版本
async function restoreParagraphVersion(section: any, paraInfo: any) {
  if (!currentProjectId.value) return

  try {
    await documentProjectApi.restoreParagraphVersion(
      currentProjectId.value,
      section.sectionId,
      paraInfo.paragraph_id,
      paraInfo.versionIndex
    )

    message.success('已恢复到此版本')

    // 刷新章节内容
    await loadSectionContent(section)

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    message.error(`恢复失败: ${error.response?.data?.detail || error.message}`)
    console.error(error)
  }
}

// 加载章节内容
async function loadSectionContent(section: any) {
  if (!currentProjectId.value) return

  try {
    const project = await documentProjectApi.getProject(currentProjectId.value)
    const sections = project.sections || {}
    const sectionData = sections[section.sectionId]

    if (sectionData && sectionData.paragraphs) {
      const sectionIndex = generatedSections.value.findIndex(s => s.sectionId === section.sectionId)
      if (sectionIndex >= 0) {
        generatedSections.value[sectionIndex].paragraphs = sectionData.paragraphs
      }
    }
  } catch (error: any) {
    console.error('加载章节内容失败:', error)
  }
}

// 显示来源
function showSourceSource(source: Source) {
  selectedSource.value = source
  showSourceDrawer.value = true
}

// 导出为 Word 文档
async function handleExportWord() {
  if (!currentProjectId.value) {
    message.warning('没有项目可以导出')
    return
  }

  try {
    isExporting.value = true
    const projectTitle = topicInput.value || '文档'
    await documentProjectApi.exportWord(currentProjectId.value, projectTitle)
    message.success('导出成功')
  } catch (error: any) {
    message.error(`导出失败: ${error.message || '未知错误'}`)
    console.error(error)
  } finally {
    isExporting.value = false
  }
}

// 打印PDF
function handlePrintPdf() {
  if (!currentProjectId.value) {
    message.warning('没有项目可以打印')
    return
  }

  const previewUrl = documentProjectApi.getPreviewHtmlUrl(currentProjectId.value)
  window.open(previewUrl, '_blank')
  message.info('在新窗口中打开，使用浏览器打印功能保存为PDF')
}

// 切换章节标题编辑状态
function toggleSectionEdit(section: any) {
  if (section.isEditing) {
    // 取消编辑
    section.isEditing = false
    section.editingTitle = ''
  } else {
    // 开始编辑
    section.isEditing = true
    section.editingTitle = section.title
    // 下一帧自动聚焦输入框
    nextTick(() => {
      const inputs = document.querySelectorAll<HTMLInputElement>('input[value]')
      inputs.forEach((input) => {
        if (input.value === section.title) {
          input.focus()
          input.select()
        }
      })
    })
  }
}

// 处理章节标题失焦
function handleSectionTitleBlur(section: any) {
  if (section.isEditing && section.editingTitle) {
    updateSectionTitle(section, section.editingTitle)
  }
  section.isEditing = false
}

// 处理章节标题按Enter
function handleSectionTitleEnter(section: any) {
  if (section.editingTitle) {
    updateSectionTitle(section, section.editingTitle)
  }
  section.isEditing = false
}

// 更新章节标题
async function updateSectionTitle(section: any, newTitle: string) {
  if (!newTitle.trim()) {
    message.warning('标题不能为空')
    return
  }

  if (newTitle === section.title) {
    return
  }

  const oldTitle = section.title
  section.title = newTitle

  // 更新大纲树中的标题
  updateOutlineNodeTitle(section.sectionId, newTitle)

  message.success(`标题已更新: "${oldTitle}" → "${newTitle}"`)
}

// 递归更新大纲节点标题
function updateOutlineNodeTitle(nodeId: string, newTitle: string) {
  const updateNode = (nodes: OutlineNode[]): boolean => {
    for (let i = 0; i < nodes.length; i++) {
      if (nodes[i].id === nodeId) {
        nodes[i].label = newTitle
        return true
      }
      if (nodes[i].children && nodes[i].children.length > 0) {
        if (updateNode(nodes[i].children!)) {
          return true
        }
      }
    }
    return false
  }

  updateNode(outline.value)
}

// 格式化项目时间
function formatProjectTime(timestamp: string) {
  const date = new Date(timestamp)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')

  return `${year}.${month}.${day} ${hour}h${minute}`
}

function formatConversationTime(timestamp: string) {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleString()
}

function upsertConversation(conversation: ReportConversation) {
  const list = [...conversationList.value]
  const index = list.findIndex(item => item.id === conversation.id)
  if (index >= 0) {
    list[index] = conversation
  } else {
    list.unshift(conversation)
  }
  list.sort((left, right) => {
    return new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime()
  })
  conversationList.value = list
}

function syncAppliedParagraph(sectionId: string, paragraph?: GeneratedParagraph | null) {
  if (!paragraph) return

  const sectionIndex = generatedSections.value.findIndex(section => section.sectionId === sectionId)
  if (sectionIndex >= 0) {
    generatedSections.value[sectionIndex].paragraphs = [paragraph]
    return
  }

  const outlineSection = flattenOutline(outline.value).find(section => section.sectionId === sectionId)
  if (outlineSection) {
    generatedSections.value.push({
      ...outlineSection,
      paragraphs: [paragraph],
      isEditing: false,
      editingTitle: ''
    })
  }
}

async function loadConversationList(autoSelect: boolean = true) {
  if (!currentProjectId.value) return

  try {
    isLoadingConversationList.value = true
    const result = await documentProjectApi.listConversations(currentProjectId.value, {
      scopeType: conversationScopeType.value,
      scopeId: conversationScopeId.value
    })
    conversationList.value = result.conversations || []

    if (!autoSelect) {
      return
    }

    const preferredId = activeConversation.value?.id
    const nextConversation = preferredId
      ? conversationList.value.find(item => item.id === preferredId)
      : conversationList.value[0]

    if (nextConversation) {
      await selectConversation(nextConversation.id)
    } else {
      activeConversation.value = null
    }
  } catch (error: any) {
    message.error(error.response?.data?.detail || '加载写作会话失败')
    console.error(error)
  } finally {
    isLoadingConversationList.value = false
  }
}

async function selectConversation(conversationId: string) {
  if (!currentProjectId.value) return

  try {
    isLoadingConversationDetail.value = true
    const conversation = await documentProjectApi.getConversation(currentProjectId.value, conversationId)
    activeConversation.value = conversation
    upsertConversation(conversation)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '加载会话详情失败')
    console.error(error)
  } finally {
    isLoadingConversationDetail.value = false
  }
}

async function createConversationForCurrentScope() {
  if (!currentProjectId.value) return null

  try {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const titlePrefix = conversationScopeType.value === 'project' ? '项目会话' : '章节会话'
    const conversation = await documentProjectApi.createConversation(currentProjectId.value, {
      scopeType: conversationScopeType.value,
      scopeId: conversationScopeId.value,
      title: `${titlePrefix} ${timestamp}`
    })
    upsertConversation(conversation)
    await selectConversation(conversation.id)
    return conversation
  } catch (error: any) {
    message.error(error.response?.data?.detail || '创建会话失败')
    console.error(error)
    return null
  }
}

async function ensureConversationReady() {
  await loadConversationList(false)
  if (conversationList.value.length === 0) {
    await createConversationForCurrentScope()
    return
  }
  await selectConversation(conversationList.value[0].id)
}

async function openProjectConversationDrawer() {
  if (!currentProjectId.value) {
    message.warning('请先选择一个项目')
    return
  }

  conversationScopeType.value = 'project'
  conversationScopeId.value = currentProjectId.value
  conversationScopeTitle.value = topicInput.value || projects.value.find(item => item.id === currentProjectId.value)?.title || '当前项目'
  conversationApplyMode.value = 'suggest_only'
  conversationTargetSectionId.value = selectedNode.value?.id || generatedSections.value[0]?.sectionId || null
  showConversationDrawer.value = true
  await ensureConversationReady()
}

async function openSectionConversationDrawer(section: any) {
  if (!currentProjectId.value) {
    message.warning('请先选择一个项目')
    return
  }

  conversationScopeType.value = 'section'
  conversationScopeId.value = section.sectionId
  conversationScopeTitle.value = section.title
  conversationApplyMode.value = 'apply_to_section'
  conversationTargetSectionId.value = section.sectionId
  showConversationDrawer.value = true
  await ensureConversationReady()
}

async function sendConversationMessage() {
  if (!currentProjectId.value) return
  const text = conversationInput.value.trim()
  if (!text) return

  let conversation = activeConversation.value
  if (!conversation) {
    conversation = await createConversationForCurrentScope()
    if (!conversation) return
  }

  if (conversationApplyMode.value === 'apply_to_section' && !conversationTargetSectionId.value) {
    message.warning('请选择要应用的章节')
    return
  }

  try {
    isSendingConversationMessage.value = true
    const response = await documentProjectApi.sendConversationMessage(
      currentProjectId.value,
      conversation.id,
      {
        message: text,
        applyMode: conversationApplyMode.value,
        targetSectionId: conversationApplyMode.value === 'apply_to_section'
          ? (conversationScopeType.value === 'section' ? conversationScopeId.value : conversationTargetSectionId.value || undefined)
          : undefined
      }
    )

    if (response.conversation) {
      activeConversation.value = response.conversation
      upsertConversation(response.conversation)
    } else {
      await selectConversation(conversation.id)
    }

    if (response.appliedParagraph) {
      const targetSectionId = conversationScopeType.value === 'section'
        ? conversationScopeId.value
        : conversationTargetSectionId.value
      if (targetSectionId) {
        syncAppliedParagraph(targetSectionId, response.appliedParagraph)
      }
      message.success('已生成并应用到章节')
    } else {
      message.success('写作建议已更新')
    }

    conversationInput.value = ''
    await loadProjects()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '发送写作消息失败')
    console.error(error)
  } finally {
    isSendingConversationMessage.value = false
  }
}

// 加载项目列表
async function loadProjects() {
  try {
    isLoadingProjects.value = true
    const result = await documentProjectApi.list(0, 50)
    projects.value = result.projects
  } catch (error: any) {
    message.error(`加载项目列表失败: ${error.message || '未知错误'}`)
    console.error(error)
  } finally {
    isLoadingProjects.value = false
  }
}

// 加载单个项目
async function loadProject(project: any) {
  try {
    console.log('开始加载项目:', project.id)
    const projectDetail = await documentProjectApi.get(project.id)
    console.log('项目详情:', projectDetail)

    // 设置项目状态
    currentProjectId.value = projectDetail.id
    topicInput.value = projectDetail.title
    outline.value = projectDetail.outline || []
    outlineLocked.value = projectDetail.outlineLocked || false
    selectedFolderIds.value = projectDetail.folderIds || []

    console.log('大纲:', outline.value)
    console.log('已锁定:', outlineLocked.value)

    // 加载已生成的内容
    if (projectDetail.outline && projectDetail.outline.length > 0) {
      const allSections = flattenOutline(outline.value)
      console.log('所有章节:', allSections)
      console.log('sections数据:', projectDetail.sections)

      generatedSections.value = allSections.map(section => {
        const sectionData = projectDetail.sections && projectDetail.sections[section.sectionId]
        console.log(`章节 ${section.sectionId} 数据:`, sectionData)

        return {
          ...section,
          paragraphs: sectionData && sectionData.paragraphs ? sectionData.paragraphs : null,
          isEditing: false,
          editingTitle: ''
        }
      })
    } else {
      generatedSections.value = []
    }

    console.log('生成的sections:', generatedSections.value)

    // 展开所有大纲节点
    if (outline.value.length > 0) {
      expandAllNodes()
    }

    conversationList.value = []
    activeConversation.value = null
    conversationInput.value = ''
    conversationScopeType.value = 'project'
    conversationScopeId.value = projectDetail.id
    conversationScopeTitle.value = projectDetail.title

    message.success(`已加载项目: ${projectDetail.title}`)
  } catch (error: any) {
    message.error(`加载项目失败: ${error.message || '未知错误'}`)
    console.error(error)
  }
}

// 新建项目
function handleCreateNew() {
  currentProjectId.value = null
  topicInput.value = ''
  outline.value = []
  outlineLocked.value = false
  selectedFolderIds.value = []
  generatedSections.value = []
  expandedKeys.value = []
  selectedKeys.value = []
  selectedNode.value = null
  selectedKey.value = ''

  // 清除上传状态
  uploadedDocument.value = null
  isParsed.value = false

  conversationList.value = []
  activeConversation.value = null
  conversationInput.value = ''
  conversationTargetSectionId.value = null
  showConversationDrawer.value = false

  // 显示上传抽屉
  showUploadDrawer.value = true
}

// 清除上传
function clearUpload() {
  uploadedDocument.value = null
  isParsed.value = false
}

// 处理 Word 文档上传
async function handleWordUpload(options: UploadCustomRequestOptions) {
  const { file, onProgress, onFinish, onError } = options

  isUploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', file.file as File)
    formData.append('folderId', 'root')

    const response = await fetch('/api/documents/upload', {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error('上传失败')
    }

    const result = await response.json()
    uploadedDocument.value = result

    onProgress({ percent: 100 })
    onFinish()

    message.success('上传成功！点击"确认导入"解析文档内容')
  } catch (error: any) {
    message.error(`上传失败: ${error.message}`)
    onError()
  } finally {
    isUploading.value = false
  }
}

// 确认导入文档
async function confirmUploadDocument() {
  if (!uploadedDocument.value) return

  isParsing.value = true

  try {
    message.info('正在处理文档，请稍候...')

    // Word 文档上传时已经转换为 Markdown，直接获取即可
    const doc = await documentApi.get(uploadedDocument.value.documentId)

    let currentDoc = doc

    // 检查是否已经有 Markdown
    if (!currentDoc.markdownContent) {
      // 如果没有 Markdown（比如 PDF），需要调用解析
      await documentApi.parse(uploadedDocument.value.documentId)

      // 轮询检查解析状态
      let parsed = false
      for (let i = 0; i < 60; i++) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        const updatedDoc = await documentApi.get(uploadedDocument.value.documentId)
        if (updatedDoc.parsed && updatedDoc.markdownContent) {
          currentDoc = updatedDoc
          parsed = true
          break
        }
      }

      if (!parsed) {
        throw new Error('文档解析超时，请稍后重试')
      }
    }

    // 获取 Markdown 内容
    const markdown = currentDoc.markdownContent
    if (!markdown) {
      throw new Error('未获取到文档内容')
    }

    // 解析 Markdown 提取大纲和内容
    const { outline: extractedOutline, sections: extractedSections } = parseMarkdownToOutline(markdown)

    // 设置标题
    topicInput.value = currentDoc.title

    // 设置大纲
    outline.value = extractedOutline
    outlineLocked.value = false // 允许用户编辑调整大纲
    outlineGenerated.value = true

    // 设置正文内容
    generatedSections.value = extractedSections

    // 展开所有大纲节点
    if (extractedOutline.length > 0) {
      expandedKeys.value = extractedOutline.map((node: OutlineNode) => node.id)
    }

    isParsed.value = true

    message.success('文档导入成功！大纲和内容已填充到编辑区')

    // 自动创建项目
    try {
      const project = await documentProjectApi.create({
        title: currentDoc.title,
        outline: extractedOutline,
        content: extractedSections
      })
      currentProjectId.value = project.id
      await loadProjects()
    } catch (error) {
      // 创建项目失败不影响导入
      console.warn('自动创建项目失败:', error)
    }

    // 关闭抽屉
    showUploadDrawer.value = false
  } catch (error: any) {
    message.error(`导入失败: ${error.message || error.response?.data?.detail}`)
    console.error(error)
  } finally {
    isParsing.value = false
  }
}

// 解析 Markdown 提取大纲和内容
function parseMarkdownToOutline(markdown: string) {
  const lines = markdown.split('\n')
  const outline: OutlineNode[] = []
  const sections: any[] = []

  let currentSection: any = null
  let currentContent: string[] = []
  const nodeStack: OutlineNode[] = []

  lines.forEach((line, index) => {
    // 匹配标题
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const title = headingMatch[2].trim()

      // 保存上一节的内容
      if (currentSection) {
        currentSection.paragraphs = [{
          content: currentContent.join('\n').trim(),
          sources: []
        }]
        sections.push(currentSection)
      }

      // 创建新节点
      const node: OutlineNode = {
        id: `section-${index}`,
        label: title,
        key: `section-${index}`,
        children: [],
        level
      }

      // 调整树结构
      while (nodeStack.length > 0) {
        const lastNode = nodeStack[nodeStack.length - 1]
        if (!lastNode || (lastNode.level ?? 0) < level) {
          break
        }
        nodeStack.pop()
      }

      if (nodeStack.length > 0) {
        nodeStack[nodeStack.length - 1].children!.push(node)
      } else {
        outline.push(node)
      }

      nodeStack.push(node)

      // 创建对应的内容节
      currentSection = {
        sectionId: `section-${index}`,
        title: title,
        paragraphs: []
      }
      currentContent = []
    } else {
      // 普通内容
      if (line.trim()) {
        currentContent.push(line)
      }
    }
  })

  // 保存最后一节
  if (currentSection) {
    currentSection.paragraphs = [{
      content: currentContent.join('\n').trim(),
      sources: []
    }]
    sections.push(currentSection)
  }

  return {
    outline,
    sections
  }
}

// 删除项目
async function handleDeleteProject(project: any) {
  if (!confirm(`确定要删除项目"${project.title}"吗？此操作不可恢复。`)) {
    return
  }

  try {
    await documentProjectApi.delete(project.id)
    message.success('项目已删除')

    // 如果删除的是当前项目，清空状态
    if (currentProjectId.value === project.id) {
      handleCreateNew()
    }

    // 刷新项目列表
    await loadProjects()
  } catch (error: any) {
    message.error(`删除失败: ${error.message || '未知错误'}`)
    console.error(error)
  }
}

// 计算节点的深度（层级）
function getNodeDepth(nodes: OutlineNode[], targetId: string, currentDepth: number = 0): number | null {
  for (const node of nodes) {
    if (node.id === targetId) {
      return currentDepth + 1
    }
    if (node.children && node.children.length > 0) {
      const found = getNodeDepth(node.children, targetId, currentDepth + 1)
      if (found !== null) {
        return found
      }
    }
  }
  return null
}

// 添加节点
function handleAddNode() {
  let label = '新章节'

  if (selectedKey.value) {
    const level = getNodeDepth(outline.value, selectedKey.value) || 1
    const parent = findNodeById(outline.value, selectedKey.value)
    if (!parent) return

    const nextNum = (parent.children?.length || 0) + 1

    if (level === 1) {
      label = `第${nextNum}节 新内容`
    } else if (level === 2) {
      let prefix = '1'
      const match1 = parent.label.match(/第(\d+)节/)
      if (match1) {
        prefix = match1[1]
      } else {
        const match2 = parent.label.match(/^(\d+\.\d+)/)
        if (match2) {
          prefix = match2[1]
        }
      }
      label = `${prefix}.${nextNum} 新要点`
    } else if (level >= 3) {
      let prefix = '1.1'
      const match = parent.label.match(/^(\d+\.\d+\.\d+)/)
      if (match) {
        prefix = match[1]
      } else {
        const match2 = parent.label.match(/^(\d+\.\d+)/)
        if (match2) {
          prefix = match2[1]
        }
      }
      label = `${prefix}.${nextNum} 新细节`
    } else {
      label = '新内容'
    }

    if (!parent.children) parent.children = []
    parent.children.push({
      id: `new-${Date.now()}`,
      label: label,
      children: []
    })

    if (!expandedKeys.value.includes(selectedKey.value)) {
      expandedKeys.value.push(selectedKey.value)
    }
  } else {
    const nextNum = outline.value.length + 1
    label = `第${nextNum}章 新章节`

    outline.value.push({
      id: `new-${Date.now()}`,
      label: label,
      children: []
    })
  }

  message.success(`已添加: ${label}`)
}

// 删除节点
function handleDeleteNode() {
  if (!selectedNode.value || !selectedKey.value) {
    message.warning('请先选择要删除的节点')
    return
  }

  const idToDelete = selectedKey.value
  const labelToDelete = selectedNode.value.label

  const deleteNode = (nodes: OutlineNode[], id: string): boolean => {
    for (let i = 0; i < nodes.length; i++) {
      if (nodes[i].id === id) {
        nodes.splice(i, 1)
        return true
      }
      if (nodes[i].children && nodes[i].children.length > 0) {
        if (deleteNode(nodes[i].children!, id)) {
          return true
        }
      }
    }
    return false
  }

  const success = deleteNode(outline.value, idToDelete)

  if (success) {
    // 清除选中状态
    selectedNode.value = null
    selectedKey.value = ''
    selectedKeys.value = []
    message.success(`"${labelToDelete}" 及其所有子节点已删除`)
  } else {
    message.error('删除失败：未找到对应的节点')
  }
}

// 打开重命名弹窗
function openRenameModal() {
  if (!selectedNode.value) return
  newNodeLabel.value = selectedNode.value.label
  showRenameModal.value = true
}

// 重命名节点
function handleRenameNode() {
  if (!selectedNode.value) return

  const newLabel = newNodeLabel.value.trim()
  if (!newLabel) {
    message.warning('请输入标题')
    return
  }

  const idToRename = selectedKey.value
  const oldLabel = selectedNode.value.label

  const renameNode = (nodes: OutlineNode[], id: string): boolean => {
    for (let i = 0; i < nodes.length; i++) {
      if (nodes[i].id === id) {
        nodes[i].label = newLabel
        return true
      }
      if (nodes[i].children && nodes[i].children.length > 0) {
        if (renameNode(nodes[i].children, id)) {
          return true
        }
      }
    }
    return false
  }

  const success = renameNode(outline.value, idToRename)

  if (success) {
    // 更新选中节点的label
    if (selectedNode.value) {
      selectedNode.value.label = newLabel
    }
    showRenameModal.value = false
    newNodeLabel.value = ''
    message.success(`"${oldLabel}" 已重命名为 "${newLabel}"`)
  } else {
    message.error('重命名失败：未找到对应的节点')
  }
}

function findNodeById(nodes: OutlineNode[], id: string): OutlineNode | null {
  for (const node of nodes) {
    if (node.id === id) {
      return node
    }
    if (node.children && node.children.length > 0) {
      const found = findNodeById(node.children, id)
      if (found) {
        return found
      }
    }
  }
  return null
}

function expandAllNodes() {
  const keys: string[] = []
  const collectKeys = (nodes: OutlineNode[]) => {
    nodes.forEach(node => {
      if (node.children && node.children.length > 0) {
        keys.push(node.id)
        collectKeys(node.children)
      }
    })
  }
  collectKeys(outline.value)
  expandedKeys.value = keys
}

onMounted(() => {
  loadFolders()
  loadProjects()
})
</script>

<style scoped>
.document-view {
  height: 100%;
}

.project-tab {
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.project-tab:hover {
  background-color: var(--n-color-modal);
}

.project-tab.active {
  background-color: rgba(255, 255, 255, 0.12) !important;
  border-radius: 8px;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: relative;
}

.project-tab.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background-color: var(--n-color-target);
  border-radius: 8px 0 0 8px;
}

[contenteditable] {
  outline: none;
}

[contenteditable]:focus {
  border-color: var(--n-color-target) !important;
}
</style>

<style>
/* 全局样式：完全禁用 Naive UI 树组件的默认选中样式 */
.n-tree-node-wrapper,
.n-tree-node-content,
.n-tree-node--selected > .n-tree-node-wrapper > .n-tree-node-content,
.n-tree-node--selected .n-tree-node-content,
.n-tree-node-content--selected,
.n-tree .n-tree-node > .n-tree-node-wrapper,
.n-tree .n-tree-node > .n-tree-node-wrapper > .n-tree-node-content {
  background-color: transparent !important;
}
</style>
