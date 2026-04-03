<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'
import Toolbar from '../components/Toolbar.vue'
import Sidebar from '../components/Sidebar.vue'
import AppToast from '../components/AppToast.vue'
import Resizer from '../components/Resizer.vue'

const store = useEditorStore()
const toast = ref<InstanceType<typeof AppToast>>()
const { editContent, originalHtml } = storeToRefs(store)

// 预览 HTML（处理 body 样式适配）
const previewHtml = computed(() => {
  const html = editContent.value
  if (!html) return ''

  // 替换 body 选择器为 .preview-content，并添加移动端样式限制
  let processedHtml = html.replace(/\bbody\b/g, '.preview-content')

  // 插入移动端样式（如果已存在 style 标签则追加，否则创建）
  const mobileStyles = `
    .preview-content {
      max-width: 359px !important;
      margin: 0 auto !important;
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif !important;
      -webkit-text-size-adjust: 100% !important;
    }
    .preview-content img { max-width: 100% !important; height: auto !important; }
    .preview-content table { max-width: 100% !important; }
    .preview-content pre, .preview-content code { white-space: pre-wrap !important; word-break: break-all !important; }
  `

  // 检查是否有 style 标签
  if (processedHtml.includes('<style')) {
    // 在第一个 </style> 后插入移动端样式
    processedHtml = processedHtml.replace(
      /<\/style>/i,
      `</style><style>${mobileStyles}</style>`
    )
  } else {
    // 在开头添加 style 标签
    processedHtml = `<style>${mobileStyles}</style>${processedHtml}`
  }

  return processedHtml
})

onMounted(() => {
  store.loadFileList()
})

// ========== 保存文件 ==========
function handleSave() {
  const content = editContent.value
  if (!content) return

  const fileName = store.currentFile?.name || 'article.html'
  const blob = new Blob([content], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)

  toast.value?.show('📥 文件已下载：' + fileName)
}

// ========== 恢复原始 ==========
function handleReset() {
  if (!originalHtml.value) return
  if (!confirm('确定恢复为文件原始内容？当前编辑会丢失。')) return
  store.setEditContent(originalHtml.value)
  toast.value?.show('↩ 已恢复为原始内容')
}

// ========== 全选预览内容 ==========
function handleSelectAll() {
  const container = document.querySelector('.preview-container')
  if (!container) return
  const range = document.createRange()
  range.selectNodeContents(container)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

// ========== 复制到微信 ==========
function handleCopied() {
  toast.value?.show('✅ 已复制，可直接粘贴到微信公众号后台')
}
</script>

<template>
  <div class="app-layout">
    <AppToast ref="toast" msg="" />
    <Toolbar
      @save="handleSave"
      @reset="handleReset"
      @copied="handleCopied"
      @select-all="handleSelectAll"
    />

    <div class="main-layout">
      <!-- 左侧：文件列表 -->
      <Sidebar class="panel-sidebar" />

      <!-- 中间：编辑器 -->
      <div class="panel-editor" id="editorPanel">
        <div class="editor-header">
          <span class="editor-label">✏️ 编辑器</span>
          <span class="modified-dot" :class="{ show: store.isModified }" title="内容已修改，未保存"></span>
          <span class="spacer"></span>
          <span class="editor-hint">Ctrl+S 保存</span>
        </div>
        <div class="editor-body">
          <textarea
            v-model="editContent"
            class="source-editor"
            spellcheck="false"
            placeholder="选择左侧文件后，HTML 源码会显示在这里..."
          ></textarea>
        </div>
      </div>

      <!-- 拖拽分割线 -->
      <Resizer
        left-selector=".panel-editor"
        right-selector=".panel-preview"
        :min-left="250"
        :min-right="410"
        :left-fixed-width="220"
        container-selector=".main-layout"
      />

      <!-- 右侧：预览 -->
      <div class="panel-preview">
        <div class="preview-header">👁️ 实时预览</div>
        <div class="preview-area">
          <div class="preview-container">
            <div class="preview-content" v-if="!store.isLoading && !store.loadError">
              <div v-html="previewHtml"></div>
            </div>
            <div v-else-if="store.isLoading" class="preview-loading">
              <div class="loading-spinner"></div>
              加载中...
            </div>
            <div v-else-if="store.loadError" class="preview-error">
              <p class="error-icon">⚠️</p>
              <p class="error-title">加载失败</p>
              <p class="error-msg">{{ store.loadError }}</p>
            </div>
            <div v-else-if="!editContent" class="preview-empty">
              <p>📂</p>
              <p>选择左侧文件</p>
              <p class="empty-hint">以加载预览</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: #f0f2f5;
  color: #333;
}

.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

/* 左侧文件列表 */
.panel-sidebar {
  width: 220px;
  min-width: 180px;
  flex-shrink: 0;
}

/* 中间编辑器 */
.panel-editor {
  width: 50%;
  min-width: 300px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e8e8e8;
  background: #fff;
  flex-shrink: 0;
}

.editor-header {
  padding: 10px 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #666;
  font-weight: 600;
  flex-shrink: 0;
}

.editor-label {
  display: flex;
  align-items: center;
  gap: 4px;
}

.modified-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff4d4f;
  margin-left: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.modified-dot.show {
  opacity: 1;
}

.spacer {
  flex: 1;
}

.editor-hint {
  font-size: 11px;
  color: #bbb;
  font-weight: 400;
}

.editor-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.source-editor {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  padding: 16px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  background: #fff;
  tab-size: 2;
  white-space: pre;
  overflow: auto;
  height: 100%;
}

.source-editor::selection {
  background: #b3d7ff;
}

/* 右侧预览 */
.panel-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.preview-header {
  padding: 10px 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #666;
  font-weight: 600;
  flex-shrink: 0;
}

.preview-area {
  flex: 1;
  overflow-y: auto;
  background: #e0e0e0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 0;
  min-height: 0;
}

.preview-container {
  width: 375px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.preview-content {
  width: 100%;
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 12px 8px;
  min-height: 667px;
  flex: 1;
  box-sizing: border-box;
}

/* 加载状态 */
.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  color: #999;
  font-size: 14px;
  background: #fff;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e8e8e8;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 错误状态 */
.preview-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  background: #fff;
}

.error-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.error-title {
  font-size: 16px;
  color: #e53935;
  margin: 0 0 8px 0;
  font-weight: 600;
}

.error-msg {
  color: #888;
  font-size: 13px;
  margin: 0;
  max-width: 200px;
}

/* 空状态 */
.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #bbb;
  font-size: 14px;
  text-align: center;
  background: #fff;
}

.preview-empty p {
  margin: 4px 0;
}

.preview-empty .empty-hint {
  font-size: 12px;
  color: #ccc;
}

/* 响应式 */
@media (max-width: 900px) {
  .panel-sidebar {
    width: 180px;
    min-width: 180px;
  }
  .panel-editor {
    width: 40%;
    min-width: 200px;
  }
}
</style>
