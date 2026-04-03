<script setup lang="ts">
/**
 * VisualEditor.vue - 基于 WangEditor 的可视化编辑器
 * 支持富文本编辑、格式工具栏、样式隔离
 */
import { ref, shallowRef, onBeforeUnmount, watch, nextTick } from 'vue'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
// WangEditor CSS 在 index.html 中通过 link 标签引入，避免污染全局

interface Props {
  modelValue: string
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '开始编辑文章内容...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// 使用 shallowRef 保存编辑器实例（Toolbar 需要直接访问实例）
const editorIns = shallowRef<any>(null)

// 编辑器状态
const isFullscreen = ref(false)

// 工具栏配置 - 基础功能
const toolbarConfig = {
  excludeKeys: [
    'group-video',      // 排除视频（微信公众号不支持）
    'insertVideo',      // 排除视频插入
    'uploadVideo',      // 排除视频上传
  ],
}

// 编辑器配置
const editorConfig = {
  placeholder: props.placeholder,
  MENU_CONF: {
    // 上传图片配置
    uploadImage: {
      // 已有 base64，暂时禁用上传
      showLinkImg: false,
    },
  },
}

// 监听外部内容变化（只更新非编辑器触发的变化）
let isEditorUpdating = false

watch(
  () => props.modelValue,
  (newVal) => {
    if (!editorIns.value) return

    const currentHtml = editorIns.value.getHtml()
    // 只有内容真正不同时才更新（避免循环更新）
    if (newVal !== currentHtml && !isEditorUpdating) {
      editorIns.value.setHtml(newVal)
    }
  }
)

// 编辑器变化回调
function handleCreated(editor: any) {
  editorIns.value = editor

  // 监听内容变化
  editor.on('change', () => {
    const html = editor.getHtml()
    isEditorUpdating = true
    emit('update:modelValue', html)
    nextTick(() => {
      isEditorUpdating = false
    })
  })
}

function handleDestroyed() {
  editorIns.value = null
}

// 全屏切换
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

// 获取纯文本（用于复制）
function getText(): string {
  return editorIns.value?.getText() || ''
}

// 获取 HTML
function getHtml(): string {
  return editorIns.value?.getHtml() || ''
}

// 插入内容
function insertContent(content: string) {
  if (editorIns.value) {
    editorIns.value.insertText(content)
  }
}

// 聚焦
function focus() {
  editorIns.value?.focus()
}

// 失焦
function blur() {
  editorIns.value?.blur()
}

// 组件销毁前清理
onBeforeUnmount(() => {
  if (editorIns.value) {
    editorIns.value.destroy()
  }
})

// 暴露方法给父组件
defineExpose({
  getText,
  getHtml,
  insertContent,
  focus,
  blur,
})
</script>

<template>
  <div class="visual-editor" :class="{ fullscreen: isFullscreen }">
    <!-- 工具栏 -->
    <div class="editor-toolbar">
      <Toolbar
        :default-config="toolbarConfig"
        :editor="editorIns"
        mode="default"
      />
      <div class="toolbar-actions">
        <button
          class="action-btn"
          :class="{ active: isFullscreen }"
          @click="toggleFullscreen"
          title="全屏编辑"
        >
          {{ isFullscreen ? '⤓ 退出全屏' : '⤒ 全屏' }}
        </button>
      </div>
    </div>

    <!-- 编辑器主体 -->
    <div class="editor-container">
      <Editor
        :default-config="editorConfig"
        :mode="isFullscreen ? 'simple' : 'default'"
        @on-created="handleCreated"
        @on-destroyed="handleDestroyed"
      />
    </div>
  </div>
</template>

<style scoped>
.visual-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.visual-editor.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
}

/* 工具栏样式 */
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
  flex-shrink: 0;
}

.editor-toolbar :deep(.w-e-toolbar) {
  border: none;
  background: transparent;
  flex-wrap: wrap;
  padding: 4px 8px;
}

.editor-toolbar :deep(.w-e-toolbar .w-e-item) {
  padding: 4px 6px;
}

.editor-toolbar :deep(.w-e-toolbar .w-e-menu:hover) {
  background: #f0f0f0;
}

.toolbar-actions {
  padding: 0 12px;
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f5f5f5;
  border-color: #667eea;
  color: #667eea;
}

.action-btn.active {
  background: #667eea;
  border-color: #667eea;
  color: #fff;
}

/* 编辑器容器 */
.editor-container {
  flex: 1;
  overflow: hidden;
}

.editor-container :deep(.w-e-text-container) {
  border: none !important;
  background: transparent;
}

.editor-container :deep(.w-e-panel-container) {
  z-index: 100;
}

/* 全屏模式样式 */
.fullscreen .editor-container {
  flex: 1;
}
</style>
