<template>
  <div style="border: 1px solid #ccc; height: 100%; display: flex; flex-direction: column; overflow: hidden;">
    <Toolbar
      :editor="editorRef"
      :defaultConfig="toolbarConfig"
      mode="default"
      style="flex-shrink: 0; border-bottom: 1px solid #ccc;"
    />
    <div style="flex: 1; overflow: hidden;">
      <Editor
        style="height: 100%; overflow-y: auto;"
        v-model="htmlValue"
        :defaultConfig="editorConfig"
        mode="default"
        @onCreated="handleCreated"
        @onChange="handleChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, onBeforeUnmount, watch } from 'vue'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import type { IDomEditor, IEditorConfig, IToolbarConfig } from '@wangeditor/editor'
import '@wangeditor/editor/dist/css/style.css'

interface Props {
  modelValue: string
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [value: string]
}>()

const editorRef = shallowRef<IDomEditor>()
const htmlValue = ref(props.modelValue || '')

// 监听外部值变化
watch(() => props.modelValue, (newVal) => {
  if (newVal !== htmlValue.value) {
    htmlValue.value = newVal
  }
})

// 工具栏配置 - 只保留必要的格式工具
const toolbarConfig: Partial<IToolbarConfig> = {
  // 配置工具栏，排除不需要的
  excludeKeys: [
    'group-image',   // 排除图片组（上传图片、插入图片）
    'group-video',   // 排除视频组
    'group-table',   // 排除表格
    'uploadImage',   // 排除上传图片
    'insertImage',   // 排除插入图片
    'uploadVideo',   // 排除上传视频
    'insertVideo',   // 排除插入视频
    'insertTable',   // 排除插入表格
    'group-link'     // 排除链接（可选）
  ]
}

// 编辑器配置
const editorConfig: Partial<IEditorConfig> = {
  placeholder: '请输入内容...',
  MENU_CONF: {
    // 配置字号
    fontSize: {
      fontSizeList: [
        '12px', '14px', '16px', '18px', '20px', '24px', '28px', '32px', '36px', '48px'
      ]
    },
    // 配置字体
    fontFamily: {
      fontFamilyList: [
        '黑体',
        '宋体',
        '楷体',
        '微软雅黑',
        'Arial',
        'Times New Roman',
        'Courier New'
      ]
    },
    // 配置颜色
    color: {
      colors: [
        '#000000', '#333333', '#666666', '#999999', '#cccccc', '#ffffff',
        '#ff0000', '#ff9900', '#ffff00', '#00ff00', '#00ffff', '#0000ff',
        '#9900ff', '#ff00ff', '#ffcccc', '#ffcc99', '#ffffcc', '#ccffcc',
        '#ccffff', '#ccccff', '#ffccff'
      ]
    },
    // 配置背景色
    bgColor: {
      colors: [
        '#000000', '#333333', '#666666', '#999999', '#cccccc', '#ffffff',
        '#ff0000', '#ff9900', '#ffff00', '#00ff00', '#00ffff', '#0000ff',
        '#9900ff', '#ff00ff', '#ffcccc', '#ffcc99', '#ffffcc', '#ccffcc',
        '#ccffff', '#ccccff', '#ffccff'
      ]
    },
    // 配置行高
    lineHeight: {
      lineHeightList: ['1', '1.5', '2', '2.5', '3']
    }
  }
}

// 编辑器创建完成
const handleCreated = (editor: IDomEditor) => {
  editorRef.value = editor
  console.log('编辑器创建成功', editor)
}

// 内容变化
const handleChange = (editor: IDomEditor) => {
  const html = editor.getHtml()
  htmlValue.value = html
  emit('update:modelValue', html)
  emit('change', html)
}

// 组件销毁时，也销毁编辑器
onBeforeUnmount(() => {
  const editor = editorRef.value
  if (editor == null) return
  editor.destroy()
})
</script>

<style>
/* 全局样式，确保工具栏和编辑器正常显示 */
.wang-editor-container {
  border: 1px solid #ccc;
}

.wang-editor-container .w-e-toolbar {
  background-color: #f1f1f1;
  border-bottom: 1px solid #ccc;
}

.wang-editor-container .w-e-text-container {
  background-color: #fff;
}

.wang-editor-container .w-e-text-container [data-slate-editor] p {
  margin: 10px 0;
}

.wang-editor-container .w-e-text-placeholder {
  color: #999;
  font-style: normal;
}
</style>
