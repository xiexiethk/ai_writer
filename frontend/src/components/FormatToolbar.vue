<template>
  <div v-if="visible" class="format-toolbar">
    <div class="toolbar-container">
      <!-- 字体选择 -->
      <select v-model="fontFamily" @change="applyFontFamily" class="toolbar-select" title="字体">
        <option value="inherit">默认</option>
        <option value="SimSun">宋体</option>
        <option value="SimHei">黑体</option>
        <option value="Microsoft YaHei">微软雅黑</option>
        <option value="KaiTi">楷体</option>
        <option value="Arial">Arial</option>
        <option value="Times New Roman">Times New Roman</option>
      </select>

      <!-- 字号选择 -->
      <select v-model="fontSize" @change="applyFontSize" class="toolbar-select" title="字号">
        <option value="12px">12</option>
        <option value="14px">14</option>
        <option value="16px">16</option>
        <option value="18px">18</option>
        <option value="20px">20</option>
        <option value="24px">24</option>
        <option value="28px">28</option>
        <option value="32px">32</option>
      </select>

      <div class="toolbar-divider"></div>

      <!-- 加粗 -->
      <button
        class="toolbar-btn"
        :class="{ active: isBold }"
        @click="toggleBold"
        title="加粗 (Ctrl+B)"
      >
        <strong>B</strong>
      </button>

      <!-- 斜体 -->
      <button
        class="toolbar-btn"
        :class="{ active: isItalic }"
        @click="toggleItalic"
        title="斜体 (Ctrl+I)"
      >
        <em>I</em>
      </button>

      <!-- 下划线 -->
      <button
        class="toolbar-btn"
        :class="{ active: isUnderline }"
        @click="toggleUnderline"
        title="下划线 (Ctrl+U)"
      >
        <u>U</u>
      </button>

      <!-- 删除线 -->
      <button
        class="toolbar-btn"
        :class="{ active: isStrikeThrough }"
        @click="toggleStrikeThrough"
        title="删除线"
      >
        <s>S</s>
      </button>

      <div class="toolbar-divider"></div>

      <!-- 文字颜色 -->
      <div class="toolbar-color-wrapper">
        <button class="toolbar-btn" title="文字颜色">
          <span class="color-icon" style="background: linear-gradient(to bottom, red, orange, yellow, green, blue, purple);">A</span>
        </button>
        <input
          type="color"
          v-model="textColor"
          @input="applyTextColor"
          class="color-input"
        />
      </div>

      <!-- 背景颜色 -->
      <div class="toolbar-color-wrapper">
        <button class="toolbar-btn" title="背景颜色">
          <span class="color-icon bg-color-icon">🎨</span>
        </button>
        <input
          type="color"
          v-model="bgColor"
          @input="applyBgColor"
          class="color-input"
        />
      </div>

      <div class="toolbar-divider"></div>

      <!-- 左对齐 -->
      <button
        class="toolbar-btn"
        :class="{ active: textAlign === 'left' }"
        @click="setAlignLeft"
        title="左对齐"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 4h18v2H3V4zm0 4h12v2H3V8zm0 4h18v2H3v-2zm0 4h12v2H3v-2zm0 4h18v2H3v-2z"/>
        </svg>
      </button>

      <!-- 居中对齐 -->
      <button
        class="toolbar-btn"
        :class="{ active: textAlign === 'center' }"
        @click="setAlignCenter"
        title="居中对齐"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 4h18v2H3V4zm3 4h12v2H6V8zm-3 4h18v2H3v-2zm3 4h12v2H6v-2zm-3 4h18v2H3v-2z"/>
        </svg>
      </button>

      <!-- 右对齐 -->
      <button
        class="toolbar-btn"
        :class="{ active: textAlign === 'right' }"
        @click="setAlignRight"
        title="右对齐"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 4h18v2H3V4zm6 4h12v2H9V8zm-6 4h18v2H3v-2zm6 4h12v2H9v-2zm-6 4h18v2H3v-2z"/>
        </svg>
      </button>

      <div class="toolbar-divider"></div>

      <!-- 无序列表 -->
      <button
        class="toolbar-btn"
        @click="toggleUnorderedList"
        title="无序列表"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z"/>
          <circle cx="2" cy="7" r="1"/>
          <circle cx="2" cy="12" r="1"/>
          <circle cx="2" cy="17" r="1"/>
        </svg>
      </button>

      <!-- 有序列表 -->
      <button
        class="toolbar-btn"
        @click="toggleOrderedList"
        title="有序列表"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M2 17h2v2H2v-2zm1-3H2v-2h1v2zm-1-4h2v2H2v-2zm1-3H2V5h1v2z"/>
          <path d="M20 5H4v2h16V5zm0 4H4v2h16V9zm0 4H4v2h16v-2zm0 4H4v2h16v-2z"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  visible: boolean
  editorRef?: HTMLDivElement
}>()

const fontFamily = ref('inherit')
const fontSize = ref('14px')
const textColor = ref('#000000')
const bgColor = ref('#ffffff')
const isBold = ref(false)
const isItalic = ref(false)
const isUnderline = ref(false)
const isStrikeThrough = ref(false)
const textAlign = ref('left')

// 执行格式化命令
const execCommand = (command: string, value: any = null) => {
  document.execCommand(command, false, value)
}

// 应用字体
const applyFontFamily = () => {
  if (fontFamily.value !== 'inherit') {
    execCommand('fontName', fontFamily.value)
  }
}

// 应用字号
const applyFontSize = () => {
  const size = parseInt(fontSize.value)
  const fontSizeMap: Record<number, string> = {
    12: '1',
    14: '2',
    16: '3',
    18: '4',
    20: '5',
    24: '6',
    28: '6',
    32: '7'
  }
  const fontSizeValue = fontSizeMap[size] || '3'
  execCommand('fontSize', fontSizeValue)
}

// 切换加粗
const toggleBold = () => {
  execCommand('bold')
  isBold.value = !isBold.value
}

// 切换斜体
const toggleItalic = () => {
  execCommand('italic')
  isItalic.value = !isItalic.value
}

// 切换下划线
const toggleUnderline = () => {
  execCommand('underline')
  isUnderline.value = !isUnderline.value
}

// 切换删除线
const toggleStrikeThrough = () => {
  execCommand('strikeThrough')
  isStrikeThrough.value = !isStrikeThrough.value
}

// 应用文字颜色
const applyTextColor = () => {
  if (textColor.value) {
    execCommand('foreColor', textColor.value)
  }
}

// 应用背景颜色
const applyBgColor = () => {
  if (bgColor.value) {
    execCommand('hiliteColor', bgColor.value)
  }
}

// 左对齐
const setAlignLeft = () => {
  execCommand('justifyLeft')
  textAlign.value = 'left'
}

// 居中对齐
const setAlignCenter = () => {
  execCommand('justifyCenter')
  textAlign.value = 'center'
}

// 右对齐
const setAlignRight = () => {
  execCommand('justifyRight')
  textAlign.value = 'right'
}

// 切换有序列表
const toggleOrderedList = () => {
  execCommand('insertOrderedList')
}

// 切换无序列表
const toggleUnorderedList = () => {
  execCommand('insertUnorderedList')
}
</script>

<style scoped>
.format-toolbar {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  background: white;
  padding: 8px 12px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border: 1px solid #e0e0e0;
  animation: slideDown 0.2s ease-out;
}

.toolbar-container {
  display: flex;
  align-items: center;
  gap: 6px;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

.toolbar-select {
  padding: 4px 8px;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: white;
  font-size: 13px;
  cursor: pointer;
  outline: none;
}

.toolbar-select:hover {
  border-color: #18a058;
}

.toolbar-select:focus {
  border-color: #18a058;
  box-shadow: 0 0 0 2px rgba(24, 160, 88, 0.1);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
  padding: 0;
  font-size: 14px;
  color: #333;
}

.toolbar-btn:hover {
  background: #f5f5f5;
  border-color: #18a058;
}

.toolbar-btn.active {
  background: #18a058;
  color: white;
  border-color: #18a058;
}

.toolbar-btn:active {
  transform: scale(0.95);
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #e0e0e0;
  margin: 0 4px;
}

.toolbar-color-wrapper {
  position: relative;
  display: inline-block;
}

.color-input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.color-icon {
  font-size: 14px;
  font-weight: bold;
  display: inline-block;
  color: transparent;
  background-clip: text;
  -webkit-background-clip: text;
}

.bg-color-icon {
  color: #333;
  font-size: 16px;
}
</style>
