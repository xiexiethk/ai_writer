<template>
  <div class="knowledge-view">
    <n-layout has-sider class="knowledge-shell" style="height: calc(100vh - 120px)">
      <!-- 左侧知识库列表 -->
      <n-layout-sider
        bordered
        class="knowledge-sider"
        :width="280"
        content-style="padding: 16px;"
      >
        <n-space vertical size="large">
          <!-- 标题和新建按钮 -->
          <n-space justify="space-between" align="center">
            <n-text strong>知识库</n-text>
            <n-space :size="8">
              <n-dropdown :options="dropdownOptions" @select="handleDropdownSelect">
                <n-button size="small" quaternary>
                  <template #icon>
                    <n-icon :component="SettingsIcon" />
                  </template>
                  管理
                </n-button>
              </n-dropdown>
              <n-button size="small" type="primary" @click="showCreateFolderModal = true">
                <template #icon>
                  <n-icon :component="AddIcon" />
                </template>
                新建
              </n-button>
            </n-space>
          </n-space>

          <!-- 知识库列表 -->
          <n-list v-if="folders.length > 0" hoverable clickable>
            <n-list-item
              v-for="folder in folders"
              :key="folder.id"
              :class="{ 'is-active': currentFolderId === folder.id }"
              @click="selectFolder(folder.id)"
            >
              <template #prefix>
                <n-icon :component="FolderIcon" />
              </template>
              <n-space vertical :size="4" style="width: 100%">
                <n-space justify="space-between" align="center">
                  <n-text>{{ folder.name }}</n-text>
                  <n-space :size="4">
                    <n-button
                      size="tiny"
                      quaternary
                      type="info"
                      @click.stop="handleStartRename(folder)"
                    >
                      <template #icon>
                        <n-icon :component="EditIcon" />
                      </template>
                    </n-button>
                    <n-button
                      size="tiny"
                      quaternary
                      type="error"
                      @click.stop="handleDeleteFolder(folder)"
                    >
                      <template #icon>
                        <n-icon :component="TrashIcon" />
                      </template>
                    </n-button>
                  </n-space>
                </n-space>
                <n-text depth="3" style="font-size: 11px">
                  {{ formatFolderTime(folder.createdAt) }}
                </n-text>
              </n-space>
            </n-list-item>
          </n-list>

          <n-empty v-else description="暂无知识库" size="small">
            <template #extra>
              <n-button size="small" @click="showCreateFolderModal = true">
                创建第一个知识库
              </n-button>
            </template>
          </n-empty>
        </n-space>
      </n-layout-sider>

      <!-- 右侧文档列表 -->
      <n-layout class="knowledge-content" content-style="padding: 16px;">
        <n-space vertical size="large" class="knowledge-panel">
          <!-- 顶部工具栏 -->
          <n-space justify="space-between" class="knowledge-toolbar">
            <n-space>
              <n-input
                v-model:value="searchQuery"
                placeholder="搜索文档..."
                clearable
                style="width: 300px"
                @input="handleSearch"
              >
                <template #prefix>
                  <n-icon :component="SearchIcon" />
                </template>
              </n-input>
            </n-space>

            <n-space>
              <n-tooltip :disabled="!!currentFolderId" placement="bottom">
                <template #trigger>
                  <n-button
                    type="primary"
                    class="agent-entry-button"
                    :disabled="!currentFolderId"
                    @click="openCurrentFolderInAgent"
                  >
                    <template #icon>
                      <n-icon :component="DocumentIcon" />
                    </template>
                    进入 Agent 写作
                  </n-button>
                </template>
                请先选择一个知识库
              </n-tooltip>
              <n-tooltip :disabled="!!currentFolderId" placement="bottom">
                <template #trigger>
                  <n-button
                    type="info"
                    :disabled="!currentFolderId"
                    :loading="batchVectorizingFolders.includes(currentFolderId || '')"
                    @click="showBatchVectorizeModal = true"
                  >
                    <template #icon>
                      <n-icon :component="GridIcon" />
                    </template>
                    批量向量化
                  </n-button>
                </template>
                请先选择一个知识库
              </n-tooltip>
              <n-tooltip :disabled="!!currentFolderId" placement="bottom">
                <template #trigger>
                  <n-button
                    type="primary"
                    :disabled="!currentFolderId"
                    @click="handleUploadClick"
                  >
                    <template #icon>
                      <n-icon :component="UploadIcon" />
                    </template>
                    上传文档
                  </n-button>
                </template>
                请先选择一个知识库
              </n-tooltip>
            </n-space>
          </n-space>

          <!-- 当前知识库信息 -->
          <n-card v-if="currentFolder" size="small" class="knowledge-meta-card">
            <n-space>
              <n-icon :component="FolderIcon" />
              <n-text strong>{{ currentFolder.name }}</n-text>
              <n-text depth="3">
                {{ filteredDocuments.length }} 个文档
              </n-text>
            </n-space>
          </n-card>

          <!-- 文档列表 -->
          <n-spin :show="isLoading">
            <div v-if="!currentFolderId" class="empty-state">
              <n-empty description="请选择或创建一个知识库">
                <template #icon>
                  <n-icon :component="FolderOpenIcon" />
                </template>
                <template #extra>
                  <n-button type="primary" @click="showCreateFolderModal = true">
                    创建知识库
                  </n-button>
                </template>
              </n-empty>
            </div>

            <div v-else-if="filteredDocuments.length === 0" class="empty-state">
              <n-empty description="此知识库暂无文档">
                <template #icon>
                  <n-icon :component="DocumentIcon" />
                </template>
                <template #extra>
                  <n-button type="primary" @click="handleUploadClick">
                    上传第一个文档
                  </n-button>
                </template>
              </n-empty>
            </div>

            <div v-else class="document-list">
              <div
                v-for="doc in filteredDocuments"
                :key="doc.id"
                class="document-item"
                @click="handleViewDocument(doc)"
              >
                <n-space justify="space-between" align="center" style="width: 100%">
                  <n-space align="center">
                    <n-text>{{ doc.title }}</n-text>
                  </n-space>

                  <n-space align="center">
                    <n-space :size="4">
                      <n-tag
                        :type="doc.parsed ? 'success' : 'default'"
                        size="small"
                        :bordered="false"
                      >
                        {{ doc.parsed ? '已解析' : '待解析' }}
                      </n-tag>
                      <n-tag
                        v-if="doc.parsed && doc.chunked"
                        type="info"
                        size="small"
                        :bordered="false"
                      >
                        已分块
                      </n-tag>
                    </n-space>
                    <n-text depth="3" style="font-size: 12px">
                      {{ formatTime(doc.uploadTime) }}
                    </n-text>
                    <n-button
                      size="tiny"
                      quaternary
                      type="error"
                      class="delete-btn"
                      @click.stop="handleDeleteDocument(doc)"
                    >
                      <template #icon>
                        <n-icon :component="TrashIcon" />
                      </template>
                    </n-button>
                  </n-space>
                </n-space>
              </div>
            </div>
          </n-spin>
        </n-space>
      </n-layout>
    </n-layout>

    <!-- 新建知识库对话框 -->
    <n-modal v-model:show="showCreateFolderModal" preset="card" title="新建知识库" style="width: 500px">
      <n-input
        v-model:value="newFolderName"
        placeholder="请输入知识库名称"
        @keydown.enter="handleCreateFolder"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreateFolderModal = false">取消</n-button>
          <n-button type="primary" @click="handleCreateFolder">创建</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 重命名知识库对话框 -->
    <n-modal v-model:show="showRenameFolderModal" preset="card" title="重命名知识库" style="width: 500px">
      <n-input
        v-model:value="newFolderRename"
        placeholder="请输入新的知识库名称"
        @keydown.enter="handleRenameFolder"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="showRenameFolderModal = false">取消</n-button>
          <n-button type="primary" @click="handleRenameFolder">确定</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 上传文档对话框 -->
    <n-modal v-model:show="showUploadModal" preset="card" title="上传文档" style="width: 600px">
      <n-space vertical>
        <n-form-item label="选择目标知识库" label-placement="top" required>
          <n-select
            v-model:value="selectedFolderForUpload"
            :options="folderOptions"
            placeholder="请选择知识库"
          />
        </n-form-item>

        <n-alert v-if="selectedFolderForUpload" type="info" :closable="false">
          将上传到：<strong>{{ getFolderName(selectedFolderForUpload) }}</strong>
        </n-alert>

        <n-spin :show="isUploading">
          <file-uploader
            :disabled="!selectedFolderForUpload"
            :folder-id="selectedFolderForUpload"
            @upload-start="handleUploadStart"
            @uploaded="handleFileUploaded"
            @queue-complete="handleUploadQueueComplete"
          />
        </n-spin>
      </n-space>
    </n-modal>

    <!-- 批量处理模式选择对话框 -->
    <n-modal
      v-model:show="showBatchVectorizeModal"
      preset="card"
      title="批量处理"
      class="batch-process-modal"
      style="width: 520px"
    >
      <n-space vertical size="large" class="batch-process-body">
        <div class="batch-folder-banner">
          <n-icon :component="FolderIcon" />
          <n-text>知识库：</n-text>
          <n-text strong>{{ currentFolder?.name }}</n-text>
        </div>

        <div class="batch-section-heading">
          请选择批量处理模式
        </div>

        <div class="batch-mode-list">
          <div
            class="mode-option"
            :class="{ 'is-selected': batchVectorizeMode === 'parse' }"
            @click="batchVectorizeMode = 'parse'"
          >
            <n-radio :checked="batchVectorizeMode === 'parse'" @update:checked="batchVectorizeMode = 'parse'">
              <n-space vertical :size="4" class="mode-copy">
                <n-text strong>批量解析（MinerU）</n-text>
                <n-text depth="3" class="mode-desc">
                  对文档进行 MinerU 解析，提取文本、表格、公式等内容
                </n-text>
              </n-space>
            </n-radio>
          </div>

          <div
            class="mode-option"
            :class="{ 'is-selected': batchVectorizeMode === 'incremental' }"
            @click="batchVectorizeMode = 'incremental'"
          >
            <n-radio :checked="batchVectorizeMode === 'incremental'" @update:checked="batchVectorizeMode = 'incremental'">
              <n-space vertical :size="4" class="mode-copy">
                <n-text strong>增量向量化（推荐）</n-text>
                <n-text depth="3" class="mode-desc">
                  只处理未向量化的文档，保留已完成的处理结果
                </n-text>
              </n-space>
            </n-radio>
          </div>

          <div
            class="mode-option"
            :class="{ 'is-selected': batchVectorizeMode === 'full' }"
            @click="batchVectorizeMode = 'full'"
          >
            <n-radio :checked="batchVectorizeMode === 'full'" @update:checked="batchVectorizeMode = 'full'">
              <n-space vertical :size="4" class="mode-copy">
                <n-text strong>清空重建</n-text>
                <n-text depth="3" class="mode-desc">
                  删除所有现有的分块和向量化结果，重新处理所有文档
                </n-text>
              </n-space>
            </n-radio>
          </div>
        </div>

        <n-alert v-if="batchVectorizeMode === 'full'" type="warning" :closable="false">
          警告：清空重建将删除所有现有的分块和向量化结果，此操作不可恢复！
        </n-alert>
        <n-alert v-if="batchVectorizeMode === 'parse'" type="success" :closable="false">
          说明：批量解析只对未解析或解析失败的文档进行处理
        </n-alert>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showBatchVectorizeModal = false">取消</n-button>
          <n-button type="primary" @click="handleBatchProcessCurrentFolder">
            开始处理
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 合并知识库对话框 -->
    <n-modal v-model:show="showMergeModal" preset="card" title="合并知识库" style="width: 600px">
      <n-space vertical size="large">
        <n-alert type="info" :closable="false">
          将多个知识库的文档合并到一个目标知识库
        </n-alert>

        <n-form-item label="目标知识库" required>
          <n-select
            v-model:value="mergeTargetFolder"
            :options="folderOptions"
            placeholder="选择目标知识库"
          />
        </n-form-item>

        <n-form-item label="源知识库" required>
          <n-select
            v-model:value="mergeSourceFolders"
            :options="folderOptions.filter(f => f.value !== mergeTargetFolder)"
            multiple
            placeholder="选择要合并的源知识库"
          />
        </n-form-item>

        <n-form-item label="合并后是否删除源知识库">
          <n-radio-group v-model:value="mergeDeleteSource">
            <n-radio :value="false">
              否（保留源知识库，仅移动文档）
            </n-radio>
            <n-radio :value="true">
              是（删除源知识库）
            </n-radio>
          </n-radio-group>
        </n-form-item>

        <n-alert v-if="mergeDeleteSource" type="warning" :closable="false">
          警告：选择"是"后，源知识库将被删除，所有文档将移动到目标知识库！
        </n-alert>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showMergeModal = false">取消</n-button>
          <n-button type="primary" @click="handleMerge">开始合并</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 拆分知识库对话框 -->
    <n-modal v-model:show="showSplitModal" preset="card" title="拆分知识库" style="width: 900px">
      <n-space vertical :size="16">
        <!-- 显示要拆分的知识库信息 -->
        <n-card size="small" :bordered="false" style="background-color: var(--n-color-modal);">
          <n-space align="center" :size="8">
            <n-icon :component="FolderIcon" />
            <n-text strong>源知识库：</n-text>
            <n-text>{{ currentFolder?.name || '未选择' }}</n-text>
            <n-divider vertical style="margin: 0 8px;" />
            <n-text depth="3">{{ filteredDocuments.length }} 个文档</n-text>
          </n-space>
        </n-card>

        <!-- 拆分选项 -->
        <n-form-item label="拆分后是否删除源知识库" label-placement="left" label-style="min-width: 180px;">
          <n-radio-group v-model:value="splitDeleteSource">
            <n-radio :value="false">保留源知识库</n-radio>
            <n-radio :value="true">删除源知识库</n-radio>
          </n-radio-group>
        </n-form-item>

        <!-- 拆分规则 -->
        <div v-for="(split, index) in splitSplits" :key="index" style="position: relative; padding: 12px; border: 1px solid var(--n-border-color); border-radius: 8px;">
          <n-space vertical :size="12">
            <n-space justify="space-between" align="center">
              <n-text strong>新知识库 #{{ index + 1 }}</n-text>
              <n-button
                v-if="splitSplits.length > 1"
                size="tiny"
                quaternary
                type="error"
                @click="removeSplitItem(index)"
              >
                <template #icon>
                  <n-icon :component="TrashIcon" />
                </template>
                删除
              </n-button>
            </n-space>

            <n-input
              v-model:value="split.name"
              placeholder="输入新知识库名称"
              size="small"
            />

            <!-- 智能搜索功能 -->
            <n-space vertical :size="12">
              <n-text strong style="font-size: 14px;">智能选择文档</n-text>

              <!-- 搜索输入框 + 阈值设置 -->
              <div style="display: flex; align-items: center; gap: 12px; width: 100%;">
                <!-- 搜索输入框 -->
                <n-input
                  v-model:value="split.searchQuery"
                  placeholder="输入主题关键词，系统将自动推荐相关文档"
                  size="medium"
                  clearable
                  style="flex: 1 1 auto; min-width: 0;"
                  @keydown.enter="handleSearchDocuments(index)"
                >
                  <template #prefix>
                    <n-icon :component="SearchIcon" />
                  </template>
                  <template #suffix>
                    <n-button
                      type="primary"
                      size="small"
                      @click="handleSearchDocuments(index)"
                      :loading="split.isSearching"
                      :disabled="!split.searchQuery || split.searchQuery.trim().length === 0"
                    >
                      <template #icon>
                        <n-icon :component="SearchIcon" />
                      </template>
                      搜索
                    </n-button>
                  </template>
                </n-input>

                <!-- 阈值设置 -->
                <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
                  <n-text depth="3" style="font-size: 12px; white-space: nowrap;">相关性阈值:</n-text>

                  <!-- 当前值显示 -->
                  <n-tag size="small" :bordered="false" type="info" style="min-width: 50px; justify-content: center;">
                    {{ Math.round((split.scoreThreshold || 0.4) * 100) }}%
                  </n-tag>

                  <!-- 快捷按钮 -->
                  <n-button-group size="small">
                    <n-button
                      size="tiny"
                      :type="Math.abs((split.scoreThreshold ?? 0)- 0.2) < 0.01 ? 'primary' : 'default'"
                      @click="split.scoreThreshold = 0.2"
                    >
                      20%
                    </n-button>
                    <n-button
                      size="tiny"
                      :type="Math.abs((split.scoreThreshold ?? 0) - 0.3) < 0.01 ? 'primary' : 'default'"
                      @click="split.scoreThreshold = 0.3"
                    >
                      30%
                    </n-button>
                    <n-button
                      size="tiny"
                      :type="Math.abs((split.scoreThreshold ?? 0) - 0.4) < 0.01 ? 'primary' : 'default'"
                      @click="split.scoreThreshold = 0.4"
                    >
                      40%
                    </n-button>
                    <n-button
                      size="tiny"
                      :type="Math.abs((split.scoreThreshold ?? 0) - 0.5) < 0.01 ? 'primary' : 'default'"
                      @click="split.scoreThreshold = 0.5"
                    >
                      50%
                    </n-button>
                    <n-button
                      size="tiny"
                      :type="Math.abs((split.scoreThreshold ?? 0) - 0.6) < 0.01 ? 'primary' : 'default'"
                      @click="split.scoreThreshold = 0.6"
                    >
                      60%
                    </n-button>
                  </n-button-group>

                  <!-- 自定义阈值输入 -->
                  <n-input-number
                    :value="getThresholdDisplay(split)"
                    :min="0"
                    :max="100"
                    :step="1"
                    size="small"
                    placeholder="自定义"
                    style="width: 75px;"
                    @update:value="(val: number | null) => updateThreshold(split, val)"
                    clearable
                  >
                    <template #suffix>
                      %
                    </template>
                  </n-input-number>
                </div>
              </div>

              <!-- 搜索结果 -->
              <div v-if="split.searchResults && split.searchResults.length > 0">
                <!-- 固定工具栏 -->
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border: 1px solid var(--n-border-color); border-radius: 8px 8px 0 0; background: var(--n-color-modal); border-bottom: 1px solid var(--n-border-color);">
                  <n-space align="center" :size="6">
                    <n-icon :component="FileIcon" :size="16" style="color: var(--n-color-target);" />
                    <n-text strong style="font-size: 13px;">
                      找到 {{ split.searchResults.length }} 个相关文档
                    </n-text>
                    <n-tag size="tiny" :bordered="false" type="info">
                      ≥{{ ((split.scoreThreshold || 0.4) * 100).toFixed(0) }}%
                    </n-tag>
                  </n-space>
                  <n-space :size="6">
                    <n-button
                      size="small"
                      @click="handleSelectAllSearchResults(index)"
                      :type="split.searchResults.every(doc => split.documentIds.includes(doc.id)) ? 'warning' : 'primary'"
                    >
                      <template #icon>
                        <n-icon :component="split.searchResults.every(doc => split.documentIds.includes(doc.id)) ? EditIcon : GridIcon" />
                      </template>
                      {{ split.searchResults.every(doc => split.documentIds.includes(doc.id)) ? '取消全选' : '全选' }}
                    </n-button>
                    <n-button size="small" quaternary type="error" @click="handleClearSearchResults(index)">
                      <template #icon>
                        <n-icon :component="TrashIcon" />
                      </template>
                      清空
                    </n-button>
                  </n-space>
                </div>

                <!-- 可滚动的文档列表 -->
                <div style="max-height: 240px; overflow-y: auto; border: 1px solid var(--n-border-color); border-radius: 0 0 8px 8px; border-top: none; padding: 12px; background: var(--n-color-modal);">
                  <n-space vertical :size="8">
                    <div
                      v-for="(doc, idx) in split.searchResults"
                      :key="doc.id"
                      style="padding: 10px; border-radius: 6px; background: var(--n-color); cursor: pointer; transition: all 0.2s; border: 2px solid transparent;"
                      :style="{
                        borderColor: split.documentIds.includes(doc.id) ? 'var(--n-color-target)' : 'transparent',
                        backgroundColor: split.documentIds.includes(doc.id) ? 'var(--n-color-modal)' : 'var(--n-color)'
                      }"
                      @click="toggleDocumentSelection(split, doc.id)"
                    >
                      <n-space align="center" justify="space-between">
                        <n-space align="center" :size="10">
                          <n-text :depth="3" style="font-size: 12px; min-width: 24px; text-align: center; font-weight: 600;">
                            {{ idx + 1 }}
                          </n-text>
                          <n-checkbox
                            :checked="split.documentIds.includes(doc.id)"
                            @update:checked="() => toggleDocumentSelection(split, doc.id)"
                            @click.stop
                          />
                          <n-text style="font-size: 13px; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            {{ doc.title }}
                          </n-text>
                        </n-space>
                        <n-tag
                          :type="doc.score >= 0.8 ? 'success' : doc.score >= 0.6 ? 'info' : doc.score >= 0.4 ? 'warning' : 'default'"
                          size="small"
                          :bordered="false"
                          style="min-width: 50px; text-align: center; font-weight: 500;"
                        >
                          {{ (doc.score * 100).toFixed(0) }}%
                        </n-tag>
                      </n-space>
                    </div>
                  </n-space>
                </div>
              </div>

              <!-- 已选择的文档 -->
              <div v-if="split.documentIds.length > 0" style="padding: 12px; background: rgba(24, 160, 88, 0.1); border-radius: 8px; border: 1.5px solid rgba(24, 160, 88, 0.3);">
                <n-space vertical :size="8">
                  <n-space align="center" :size="6">
                    <n-icon :component="GridIcon" :size="16" style="color: #18a058;" />
                    <n-text strong style="font-size: 13px; color: #18a058;">
                      已选择 {{ split.documentIds.length }} 个文档
                    </n-text>
                  </n-space>
                  <n-space :size="8" style="flex-wrap: wrap;">
                    <n-tag
                      v-for="docId in split.documentIds.slice(0, 5)"
                      :key="docId"
                      closable
                      size="medium"
                      type="success"
                      @close="toggleDocumentSelection(split, docId)"
                      :bordered="false"
                      round
                      style="padding: 4px 10px; height: auto; line-height: 1.8;"
                    >
                      <template #icon>
                        <n-icon :component="FileIcon" />
                      </template>
                      <span style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block;">
                        {{ getDocumentTitle(docId) }}
                      </span>
                    </n-tag>
                    <n-tag
                      v-if="split.documentIds.length > 5"
                      size="medium"
                      :bordered="false"
                      type="info"
                      round
                      style="padding: 4px 10px; height: auto; line-height: 1.8;"
                    >
                      +{{ split.documentIds.length - 5 }} 个文档
                    </n-tag>
                  </n-space>
                </n-space>
              </div>
            </n-space>
          </n-space>
        </div>

        <n-button dashed @click="addSplitItem" size="small">
          <template #icon>
            <n-icon :component="AddIcon" />
          </template>
          添加拆分规则
        </n-button>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showSplitModal = false">取消</n-button>
          <n-button type="primary" @click="handleSplit">开始拆分</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 文档详情抽屉 -->
    <n-drawer v-model:show="showDocumentDrawer" :width="1200" placement="right">
      <template #header>
        <n-space align="center">
          <n-icon :component="FileIcon" />
          <n-text strong>{{ selectedDocument?.title }}</n-text>
        </n-space>
      </template>

      <n-tabs type="line" animated>
        <n-tab-pane name="pdf" tab="PDF 预览">
          <div v-if="selectedDocument" class="pdf-viewer-container">
            <iframe
              :src="getDocumentPreviewSrc(selectedDocument.id)"
              class="pdf-iframe"
              type="application/pdf"
            ></iframe>
          </div>
        </n-tab-pane>

        <n-tab-pane name="content" tab="解析内容">
          <div v-if="selectedDocument && selectedDocument.markdownContent" class="markdown-content">
            <div v-html="selectedDocument.markdownContent"></div>
          </div>
          <n-empty v-else description="暂无解析内容" />
        </n-tab-pane>

        <n-tab-pane name="info" tab="文档信息">
          <n-descriptions v-if="selectedDocument" :column="2" bordered>
            <n-descriptions-item label="文档标题">
              {{ selectedDocument.title }}
            </n-descriptions-item>
            <n-descriptions-item label="文件名">
              {{ selectedDocument.fileName }}
            </n-descriptions-item>
            <n-descriptions-item label="文件类型">
              {{ selectedDocument.fileType.toUpperCase() }}
            </n-descriptions-item>
            <n-descriptions-item label="文件大小">
              {{ formatFileSize(selectedDocument.fileSize) }}
            </n-descriptions-item>
            <n-descriptions-item label="上传时间">
              {{ formatFullTime(selectedDocument.uploadTime) }}
            </n-descriptions-item>
            <n-descriptions-item label="解析状态">
              <n-tag
                :type="selectedDocument.parsed ? 'success' : 'warning'"
                size="small"
              >
                {{ selectedDocument.parsed ? '已解析' : '待解析' }}
              </n-tag>
            </n-descriptions-item>
          </n-descriptions>
        </n-tab-pane>
      </n-tabs>

      <template #footer>
        <n-space justify="space-between">
          <n-space>
            <n-button
              v-if="selectedDocument && !selectedDocument.parsed"
              type="primary"
              @click="handleParse(selectedDocument)"
            >
              解析文档
            </n-button>
          </n-space>
          <n-button @click="showDocumentDrawer = false">关闭</n-button>
        </n-space>
      </template>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useDocumentStore } from '@/stores/document'
import type { Document, Folder } from '@/types/document'
import { documentApi } from '@/api/document'
import { folderApi, type SplitItem, type SearchResult } from '@/api/folder'
import {
  SearchOutline as SearchIcon,
  CloudUploadOutline as UploadIcon,
  FolderOutline as FolderIcon,
  FolderOpenOutline as FolderOpenIcon,
  DocumentTextOutline as DocumentIcon,
  AddOutline as AddIcon,
  DocumentOutline as FileIcon,
  TrashOutline as TrashIcon,
  GridOutline as GridIcon,
  CreateOutline as EditIcon,
  SettingsOutline as SettingsIcon,
} from '@vicons/ionicons5'
import FileUploader from '@/components/knowledge/FileUploader.vue'

const message = useMessage()
const router = useRouter()
const documentStore = useDocumentStore()

const searchQuery = ref('')
const showCreateFolderModal = ref(false)
const showUploadModal = ref(false)
const showRenameFolderModal = ref(false)
const newFolderName = ref('')
const renamingFolder = ref<Folder | null>(null)
const newFolderRename = ref('')
const currentFolderId = ref<string | null>(null)
const selectedFolderForUpload = ref<string | null>(null)
const isLoading = ref(false)
const isUploading = ref(false)
const showDocumentDrawer = ref(false)
const selectedDocument = ref<Document | null>(null)
const batchVectorizingFolders = ref<string[]>([])
const showBatchVectorizeModal = ref(false)
const batchVectorizeMode = ref<'parse' | 'incremental' | 'full'>('incremental')
const folderPollingTimers = new Map<string, number>()

// 合并与拆分相关状态
const showMergeModal = ref(false)
const showSplitModal = ref(false)
const mergeSourceFolders = ref<string[]>([])
const mergeTargetFolder = ref<string | null>(null)
const mergeDeleteSource = ref(false)
const splitDeleteSource = ref(false)

interface LocalSplitItem {
  name: string
  documentIds: string[]
  searchQuery?: string
  isSearching?: boolean
  searchResults?: SearchResult[]
  scoreThreshold?: number
}

const splitSplits = ref<LocalSplitItem[]>([
  { name: '', documentIds: [], searchQuery: '', isSearching: false, searchResults: [], scoreThreshold: 0.4 }
])

const selectedDocsForSplit = ref<string[]>([])

const folders = computed(() => (documentStore.folders || []).filter((f) => f.id !== 'root'))
const currentFolder = computed(() =>
  (documentStore.folders || []).find((f) => f.id === currentFolderId.value)
)
const filteredDocuments = computed(() => documentStore.filteredDocuments)

const folderOptions = computed(() =>
  folders.value.map((f) => ({ label: f.name, value: f.id }))
)

// 下拉菜单选项
const dropdownOptions = [
  {
    label: '合并知识库',
    key: 'merge'
  },
  {
    label: '拆分知识库',
    key: 'split'
  }
]

function handleDropdownSelect(key: string) {
  if (key === 'merge') {
    openMergeModal()
  } else if (key === 'split') {
    openSplitModal()
  }
}

function getFolderName(folderId: string | null) {
  if (!folderId) return ''
  const folder = folders.value.find((f) => f.id === folderId)
  return folder?.name || ''
}

function openCurrentFolderInAgent() {
  if (!currentFolderId.value || !currentFolder.value) {
    message.warning('请先选择一个知识库')
    return
  }
  router.push({
    name: 'OpenWps',
    query: {
      folderId: currentFolderId.value,
      folderName: currentFolder.value.name,
    },
  })
}

function formatFolderTime(timestamp: string) {
  const date = new Date(timestamp)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')

  return `${year}.${month}.${day} ${hour}h${minute}`
}

function formatTime(timestamp: string) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return date.toLocaleDateString('zh-CN')
}

async function selectFolder(folderId: string) {
  currentFolderId.value = folderId
  documentStore.setCurrentFolder(folderId)
  await loadDocuments()
}

function handleSearch(query: string) {
  documentStore.updateFilter({ searchQuery: query })
}

function handleViewDocument(doc: Document) {
  router.push({ name: 'DocumentPreview', params: { id: doc.id } })
}

function formatFullTime(timestamp: string) {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFileSize(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

function getDocumentPreviewSrc(documentId: string) {
  const token = window.localStorage.getItem('token')
  const params = new URLSearchParams({ format: 'pdf' })
  if (token) params.set('token', token)
  return `/api/documents/${documentId}/download?${params.toString()}`
}

async function handleParse(doc: Document) {
  try {
    await documentApi.parse(doc.id)
    message.success('开始解析文档')
    await loadDocuments()
    // 刷新当前文档信息
    const updatedDoc = await documentApi.get(doc.id)
    selectedDocument.value = updatedDoc
  } catch (error) {
    message.error('解析失败')
  }
}

async function loadDocuments() {
  try {
    isLoading.value = true
    const result = await documentApi.list({
      folder: currentFolderId.value || undefined,
    })
    documentStore.setDocuments(result.documents)
  } catch (error) {
    message.error('加载文档列表失败')
  } finally {
    isLoading.value = false
  }
}

async function loadFolders() {
  try {
    const folderList = await documentApi.listFolders()
    documentStore.setFolders(folderList)

    if (folderList.length > 0 && !currentFolderId.value) {
      const userFolder = folderList.find((f) => f.id !== 'root')
      if (userFolder) {
        selectFolder(userFolder.id)
      }
    }
  } catch (error) {
    message.error('加载知识库列表失败')
  }
}

async function handleCreateFolder() {
  if (!newFolderName.value.trim()) {
    message.warning('请输入知识库名称')
    return
  }

  try {
    const folder = await documentApi.createFolder(newFolderName.value)
    documentStore.addFolder(folder)
    showCreateFolderModal.value = false
    newFolderName.value = ''
    message.success('知识库创建成功')

    selectFolder(folder.id)
  } catch (error) {
    message.error('创建知识库失败')
  }
}

function handleStartRename(folder: Folder) {
  renamingFolder.value = folder
  newFolderRename.value = folder.name
  showRenameFolderModal.value = true
}

async function handleRenameFolder() {
  if (!renamingFolder.value || !newFolderRename.value.trim()) {
    message.warning('请输入知识库名称')
    return
  }

  try {
    const updatedFolder = await documentApi.renameFolder(renamingFolder.value.id, newFolderRename.value)
    documentStore.updateFolder(updatedFolder)
    showRenameFolderModal.value = false
    renamingFolder.value = null
    newFolderRename.value = ''
    message.success('知识库重命名成功')

    // 如果重命名的是当前选中的知识库，刷新列表
    await loadFolders()
  } catch (error) {
    message.error('重命名失败')
  }
}

function handleUploadClick() {
  selectedFolderForUpload.value = currentFolderId.value
  showUploadModal.value = true
}

function handleUploadStart() {
  isUploading.value = true
}

function handleFileUploaded() {
  // 保持上传弹窗打开直到整个队列结束
}

async function handleUploadQueueComplete(payload: { successCount: number; errorCount: number }) {
  isUploading.value = false
  await loadDocuments()

  if (payload.successCount > 0 && payload.errorCount === 0) {
    message.success(`上传完成，共 ${payload.successCount} 个文档`)
    showUploadModal.value = false
    selectedFolderForUpload.value = null
    return
  }

  if (payload.successCount > 0 && payload.errorCount > 0) {
    message.warning(`上传完成，成功 ${payload.successCount} 个，失败 ${payload.errorCount} 个`)
    return
  }

  message.error('上传失败')
}

function stopFolderPolling(folderId: string) {
  const timer = folderPollingTimers.get(folderId)
  if (timer !== undefined) {
    clearInterval(timer)
    folderPollingTimers.delete(folderId)
  }
}

function stopAllFolderPolling() {
  folderPollingTimers.forEach((timer) => clearInterval(timer))
  folderPollingTimers.clear()
}

function startFolderPolling(folderId: string, mode: 'parse' | 'vectorize') {
  stopFolderPolling(folderId)

  const startedAt = Date.now()
  const maxDurationMs = 15 * 60 * 1000

  const timer = window.setInterval(async () => {
    await loadDocuments()

    const docs = documentStore.documents.filter((doc) => doc.folderId === folderId)
    const hasProcessing = mode === 'parse'
      ? docs.some((doc) => doc.parseStatus === 'parsing' || doc.parseStatus === 'queued')
      : docs.some((doc) => doc.vectorizeStatus === 'processing' || doc.vectorizeStatus === 'queued')

    if (!hasProcessing) {
      stopFolderPolling(folderId)
      batchVectorizingFolders.value = batchVectorizingFolders.value.filter((id) => id !== folderId)
      message.success(mode === 'parse' ? '批量解析完成' : '批量向量化完成')
      return
    }

    if (Date.now() - startedAt >= maxDurationMs) {
      stopFolderPolling(folderId)
      batchVectorizingFolders.value = batchVectorizingFolders.value.filter((id) => id !== folderId)
      message.warning(mode === 'parse' ? '批量解析仍在后台执行，请稍后刷新' : '批量向量化仍在后台执行，请稍后刷新')
    }
  }, 5000)

  folderPollingTimers.set(folderId, timer)
}

async function handleDeleteDocument(doc: Document) {
  if (!confirm(`确定要删除文档"${doc.title}"吗？此操作不可恢复。`)) {
    return
  }

  try {
    await documentApi.delete(doc.id)
    message.success('删除成功')

    // 如果删除的是当前打开的文档，关闭抽屉
    if (selectedDocument.value?.id === doc.id) {
      showDocumentDrawer.value = false
      selectedDocument.value = null
    }

    await loadDocuments()
  } catch (error) {
    message.error('删除失败')
  }
}

async function handleDeleteFolder(folder: Folder) {
  if (!confirm(`确定要删除知识库"${folder.name}"吗？此操作将同时删除该知识库下的所有文档，且不可恢复。`)) {
    return
  }

  try {
    await documentApi.deleteFolder(folder.id)
    message.success('知识库删除成功')

    // 如果删除的是当前选中的知识库，清空选择
    if (currentFolderId.value === folder.id) {
      currentFolderId.value = null
      documentStore.setCurrentFolder(null)
      documentStore.setDocuments([])
    }

    await loadFolders()
  } catch (error) {
    message.error('删除失败')
  }
}

async function handleBatchProcessCurrentFolder() {
  if (!currentFolderId.value) {
    message.warning('请先选择一个知识库')
    return
  }

  const folder = folders.value.find(f => f.id === currentFolderId.value)
  if (!folder) return

  try {
    // 关闭对话框
    showBatchVectorizeModal.value = false

    // 添加到正在处理的列表
    batchVectorizingFolders.value = [...batchVectorizingFolders.value, folder.id]

    let result

    // 根据模式调用不同的API
    if (batchVectorizeMode.value === 'parse') {
      // 批量解析
      result = await documentApi.batchParseFolder(folder.id, { mode: 'incremental' })
      message.success(result.message || '批量解析任务已启动')
      if (result.pendingParse > 0) {
        startFolderPolling(folder.id, 'parse')
      } else {
        batchVectorizingFolders.value = batchVectorizingFolders.value.filter(id => id !== folder.id)
      }
    } else {
      // 批量向量化
      result = await documentApi.batchVectorizeFolder(folder.id, { mode: batchVectorizeMode.value })
      message.success(result.message || '批量向量化任务已启动')
      if (result.pendingVectorization > 0) {
        startFolderPolling(folder.id, 'vectorize')
      } else {
        batchVectorizingFolders.value = batchVectorizingFolders.value.filter(id => id !== folder.id)
      }
    }

    // 重置模式选择
    batchVectorizeMode.value = 'incremental'
  } catch (error) {
    const mode = batchVectorizeMode.value === 'parse' ? '批量解析' : '批量向量化'
    message.error(`${mode}失败：` + (error as Error).message)
    batchVectorizingFolders.value = batchVectorizingFolders.value.filter(id => id !== folder.id)
    stopFolderPolling(folder.id)
  }
}

onMounted(() => {
  loadFolders()
})

onUnmounted(() => {
  stopAllFolderPolling()
})

// 合并与拆分功能
function openMergeModal() {
  mergeSourceFolders.value = []
  mergeTargetFolder.value = currentFolderId.value
  // 不要重置 mergeDeleteSource，保持用户之前的选择
  showMergeModal.value = true
}

function openSplitModal() {
  if (!currentFolderId.value) {
    message.warning('请先选择一个知识库')
    return
  }
  splitSplits.value = [{ name: '', documentIds: [], searchQuery: '', isSearching: false, searchResults: [], scoreThreshold: 0.4 } as LocalSplitItem]
  selectedDocsForSplit.value = []
  splitDeleteSource.value = false
  showSplitModal.value = true
}

function addSplitItem() {
  splitSplits.value.push({ name: '', documentIds: [], searchQuery: '', isSearching: false, searchResults: [], scoreThreshold: 0.4 } as LocalSplitItem)
}

// 获取阈值显示值（0-100）
function getThresholdDisplay(split: LocalSplitItem) {
  return Math.round((split.scoreThreshold || 0.4) * 100)
}

// 更新阈值（从显示值转换为实际值）
function updateThreshold(split: LocalSplitItem, displayValue: number | null) {
  if (displayValue !== null && displayValue >= 0 && displayValue <= 100) {
    split.scoreThreshold = displayValue / 100
  }
}

// 搜索相关文档
async function handleSearchDocuments(index: number) {
  const split = splitSplits.value[index]
  if (!split.searchQuery || split.searchQuery.trim().length === 0) {
    message.warning('请输入搜索关键词')
    return
  }

  if (!currentFolderId.value) {
    message.warning('知识库不存在')
    return
  }

  try {
    split.isSearching = true
    console.log('开始搜索:', currentFolderId.value, split.searchQuery.trim())
    const response = await folderApi.search(currentFolderId.value, split.searchQuery.trim(), 50)
    console.log('搜索响应:', response)

    if (response.results.length === 0) {
      message.info('未找到相关文档，请尝试其他关键词')
      split.searchResults = []
    } else {
      // 根据阈值过滤结果
      const threshold = split.scoreThreshold || 0.4
      const filteredResults = response.results.filter(doc => doc.score >= threshold)
      split.searchResults = filteredResults
      console.log('设置 searchResults 后:', split.searchResults)
      if (filteredResults.length < response.results.length) {
        message.info(`找到 ${response.results.length} 个相关文档，其中 ${filteredResults.length} 个符合阈值 (${(threshold * 100).toFixed(0)}%)`)
      } else {
        message.success(`找到 ${filteredResults.length} 个相关文档`)
      }
    }
  } catch (error: any) {
    console.error('搜索失败:', error)
    message.error('搜索失败：' + (error.response?.data?.detail || error.message || '未知错误'))
    split.searchResults = []
  } finally {
    split.isSearching = false
  }
}

// 一键全选/取消全选搜索结果
function handleSelectAllSearchResults(index: number) {
  const split = splitSplits.value[index]
  if (!split.searchResults || split.searchResults.length === 0) {
    message.warning('没有可选择的文档')
    return
  }

  // 检查是否所有搜索结果都已被选中
  const allSelected = split.searchResults.every(doc => split.documentIds.includes(doc.id))

  if (allSelected) {
    // 取消全选：移除所有搜索结果的ID
    const searchResultIds = new Set(split.searchResults.map(doc => doc.id))
    split.documentIds = split.documentIds.filter(id => !searchResultIds.has(id))
    message.info('已取消全选')
  } else {
    // 全选：添加所有搜索结果的ID到documentIds
    const allIds = split.searchResults.map(doc => doc.id)
    // 合并去重
    split.documentIds = Array.from(new Set([...split.documentIds, ...allIds]))
    message.success(`已选择 ${split.documentIds.length} 个文档`)
  }
}

// 清空搜索结果
function handleClearSearchResults(index: number) {
  const split = splitSplits.value[index]
  split.searchResults = []
  split.searchQuery = ''
  message.info('已清空搜索结果')
}

// 切换文档选择状态
function toggleDocumentSelection(split: any, docId: string) {
  const index = split.documentIds.indexOf(docId)
  if (index > -1) {
    split.documentIds.splice(index, 1)
  } else {
    split.documentIds.push(docId)
  }
}

// 获取文档标题
function getDocumentTitle(docId: string) {
  const doc = filteredDocuments.value.find(d => d.id === docId)
  return doc ? doc.title : docId
}

function removeSplitItem(index: number) {
  if (splitSplits.value.length > 1) {
    splitSplits.value.splice(index, 1)
  }
}

async function handleMerge() {
  if (!mergeTargetFolder.value) {
    message.warning('请选择目标知识库')
    return
  }
  if (mergeSourceFolders.value.length === 0) {
    message.warning('请选择至少一个源知识库')
    return
  }
  if (mergeSourceFolders.value.includes(mergeTargetFolder.value)) {
    message.warning('源知识库和目标知识库不能相同')
    return
  }

  try {
    const result = await folderApi.merge({
      source_folder_ids: mergeSourceFolders.value,
      target_folder_id: mergeTargetFolder.value,
      delete_source: mergeDeleteSource.value
    })

    message.success(`合并成功！移动了 ${result.movedDocumentCount} 个文档`)
    showMergeModal.value = false

    // 刷新文档和文件夹列表
    await loadFolders()
    if (currentFolderId.value) {
      await loadDocuments()
    }
  } catch (error) {
    message.error('合并失败：' + (error as Error).message)
  }
}

async function handleSplit() {
  if (!currentFolderId.value) return

  // 验证每个拆分项
  const validSplits: SplitItem[] = []
  for (const split of splitSplits.value) {
    if (!split.name || split.documentIds.length === 0) {
      continue
    }
    validSplits.push({
      target_folder_name: split.name,
      document_ids: split.documentIds
    })
  }

  if (validSplits.length === 0) {
    message.warning('请至少设置一个有效的拆分规则')
    return
  }

  try {
    const result = await folderApi.split(currentFolderId.value, {
      source_folder_id: currentFolderId.value,
      splits: validSplits,
      delete_source: splitDeleteSource.value
    })

    const deleteMsg = result.deletedSource ? '，已删除源知识库' : ''
    message.success(`拆分成功！移动了 ${result.movedDocumentCount} 个文档，创建了 ${result.createdFolders.length} 个新知识库${deleteMsg}`)
    showSplitModal.value = false

    // 刷新文档和文件夹列表
    await loadFolders()
    await loadDocuments()
  } catch (error) {
    message.error('拆分失败：' + (error as Error).message)
  }
}
</script>

<style scoped>
.knowledge-view {
  height: 100%;
}

.knowledge-shell,
.knowledge-sider,
.knowledge-content {
  background: transparent;
}

.knowledge-sider {
  border-radius: 24px 0 0 24px;
}

.knowledge-sider :deep(.n-layout-sider__border) {
  background-color: var(--aw-border);
}

.knowledge-sider :deep(.n-layout-sider-scroll-container),
.knowledge-content :deep(.n-layout-scroll-container) {
  background: transparent;
}

.knowledge-panel {
  min-height: 0;
}

.knowledge-toolbar {
  padding: 18px 20px;
  border: 1px solid var(--aw-border);
  border-radius: 24px;
  background: var(--aw-shell);
  box-shadow: var(--aw-shadow);
}

.knowledge-meta-card {
  border-radius: 22px;
  background: var(--aw-shell);
  border: 1px solid var(--aw-border);
  box-shadow: none;
}

.agent-entry-button {
  min-width: 146px;
}

.knowledge-view :deep(.n-list-item) {
  position: relative;
  margin-bottom: 8px;
  border-radius: 18px;
  border: 1px solid transparent;
  transition: all 0.24s ease;
}

.knowledge-view :deep(.n-list-item:hover) {
  background: var(--aw-paper);
  border-color: var(--aw-border);
}

.is-active {
  background-color: var(--aw-paper) !important;
  border: 1px solid var(--aw-border) !important;
  border-radius: 18px;
  font-weight: 500;
  box-shadow: 0 16px 34px rgba(89, 67, 45, 0.08);
}

.is-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background-color: var(--aw-accent);
  border-radius: 18px 0 0 18px;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  border-radius: 26px;
  border: 1px dashed var(--aw-border-strong);
  background: rgba(255, 251, 244, 0.36);
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.document-item {
  padding: 16px 18px;
  background: var(--aw-shell);
  border: 1px solid var(--aw-border);
  border-radius: 22px;
  cursor: pointer;
  box-shadow: var(--aw-shadow);
  transition: transform 0.22s ease, border-color 0.22s ease, background-color 0.22s ease;
}

.document-item:hover {
  transform: translateY(-2px);
  background: var(--aw-paper-strong);
  border-color: var(--aw-border-strong);
}

.pdf-viewer-container {
  width: 100%;
  height: calc(100vh - 200px);
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 8px;
}

.markdown-content {
  padding: 16px;
  line-height: 1.8;
}

.document-item {
  position: relative;
}

.delete-btn {
  opacity: 0.58;
  transition: opacity 0.2s;
}

.delete-btn:hover {
  opacity: 1 !important;
}

.document-item:hover .delete-btn {
  opacity: 0.8;
}

/* 批量向量化模式选择样式 */
.batch-process-body {
  padding-top: 4px;
}

.batch-folder-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--aw-success-soft);
  border: 1px solid rgba(83, 125, 98, 0.2);
}

.batch-section-heading {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--n-text-color);
}

.batch-mode-list {
  display: grid;
  gap: 12px;
}

.mode-option {
  padding: 14px 16px;
  border: 1px solid var(--aw-border);
  border-radius: 18px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--aw-paper-strong);
}

.mode-option:hover {
  background-color: var(--aw-paper);
  border-color: var(--aw-border-strong);
}

.mode-option.is-selected {
  background-color: var(--aw-paper);
  border-color: var(--aw-accent);
  border-width: 2px;
  box-shadow: 0 0 0 1px rgba(201, 111, 69, 0.12);
}

.mode-copy {
  width: 100%;
}

.mode-desc {
  font-size: 12px;
  line-height: 1.6;
}

.mode-option :deep(.n-radio) {
  width: 100%;
}

.mode-option :deep(.n-radio__label) {
  width: 100%;
}

@media (max-width: 900px) {
  .knowledge-toolbar {
    padding: 14px;
  }

  .knowledge-view {
    overflow: auto;
  }
}

</style>
