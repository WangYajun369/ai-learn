<script setup lang="ts">
import {onMounted, ref, computed, onBeforeUnmount} from 'vue'
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'
import Toolbar from '../components/Toolbar.vue'
import Sidebar from '../components/Sidebar.vue'
import AppToast from '../components/AppToast.vue'
import Resizer from '../components/Resizer.vue'

const store = useEditorStore()
const toast = ref<InstanceType<typeof AppToast>>()
const { editContent, originalHtml } = storeToRefs(store)

// File System Access API: 保存目录的 handle
const saveDirHandle = ref<FileSystemDirectoryHandle | null>(null)

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
  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

// 处理窗口大小变化
let resizeTimer: ReturnType<typeof setTimeout> | undefined = undefined
function handleResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    window.location.reload()
  }, 300) // 防抖：窗口大小稳定 300ms 后再刷新
}

// ========== 检查 File System Access API 支持 ==========
function isFileSystemAPISupported() {
  return 'showDirectoryPicker' in window && 'showSaveFilePicker' in window
}

// ========== 获取文件名（不含路径）==========
function getFileName() {
  return store.currentFile?.name || 'article.html'
}

// ========== 获取时间戳（到毫秒）==========
function getTimestamp() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const hour = String(now.getHours()).padStart(2, '0')
  const minute = String(now.getMinutes()).padStart(2, '0')
  const second = String(now.getSeconds()).padStart(2, '0')
  const millisecond = String(now.getMilliseconds()).padStart(3, '0')
  return `${year}${month}${day}-${hour}${minute}${second}-${millisecond}`
}

// ========== 保存文件 ==========
async function handleSave() {
  const content = editContent.value
  if (!content) return

  const fileName = getFileName()

  // 检查 File System Access API 支持
  if (!isFileSystemAPISupported()) {
    toast.value?.show('❌ 浏览器不支持 File System Access API，请使用 Chrome/Edge 最新版')
    // 降级为下载方式
    downloadFile(fileName, content)
    return
  }

  try {
    // 如果已授权目录，直接保存
    if (saveDirHandle.value) {
      await saveToDirectory(saveDirHandle.value, fileName, content)
      return
    }

    // 首次保存，让用户选择保存方式
    const choice = confirm(
      '首次保存，请选择保存方式：\n\n' +
      '确定 = 选择保存目录（后续保存直接写入，无需确认）\n' +
      '取消 = 每次保存时选择文件位置'
    )

    if (choice) {
      // 选择保存目录
      await requestDirectoryAccess(fileName, content)
    } else {
      // 单次保存文件
      await saveFileOnce(fileName, content)
    }
  } catch (error: any) {
    console.error('保存失败:', error)
    if (error.name === 'AbortError') {
      toast.value?.show('❌ 已取消保存')
    } else {
      toast.value?.show('❌ 保存失败：' + error.message)
    }
  }
}

// ========== 请求目录访问权限 ==========
async function requestDirectoryAccess(fileName: string, content: string) {
  try {
    // 让用户选择保存目录
    const dirHandle = await (window as any).showDirectoryPicker({
      mode: 'readwrite',
      startIn: 'documents'
    })

    // 检查权限
    const permission = await dirHandle.requestPermission({ mode: 'readwrite' })
    if (permission !== 'granted') {
      toast.value?.show('❌ 未授权目录访问权限')
      return
    }

    saveDirHandle.value = dirHandle
    await saveToDirectory(dirHandle, fileName, content)
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      throw error
    }
  }
}

// ========== 保存到目录 ==========
async function saveToDirectory(
  dirHandle: FileSystemDirectoryHandle,
  fileName: string,
  content: string
) {
  try {
    // 检查文件是否存在
    let fileHandle: FileSystemFileHandle
    try {
      fileHandle = await dirHandle.getFileHandle(fileName)
      // 文件存在，先备份
      await backupFile(fileHandle, dirHandle)
    } catch {
      // 文件不存在，创建新文件
      fileHandle = await dirHandle.getFileHandle(fileName, { create: true })
    }

    // 写入内容
    const writable = await fileHandle.createWritable()
    await writable.write(content)
    await writable.close()

    toast.value?.show(`✅ 已保存：${fileName}`)
  } catch (error: any) {
    console.error('保存到目录失败:', error)
    // 可能是权限过期，清除 handle
    saveDirHandle.value = null
    throw new Error('目录访问权限已过期，请重新选择保存目录')
  }
}

// ========== 备份文件 ==========
async function backupFile(
  fileHandle: FileSystemFileHandle,
  dirHandle: FileSystemDirectoryHandle
) {
  const fileName = fileHandle.name
  const timestamp = getTimestamp()
  const backupFileName = `${fileName}.backup.${timestamp}`

  // 读取原文件内容
  const file = await fileHandle.getFile()
  const originalContent = await file.text()

  // 创建备份文件
  const backupHandle = await dirHandle.getFileHandle(backupFileName, { create: true })
  const writable = await backupHandle.createWritable()
  await writable.write(originalContent)
  await writable.close()

  console.log(`已备份：${backupFileName}`)
  toast.value?.show(`💾 已备份：${backupFileName}`)
}

// ========== 单次保存文件（不记住目录）==========
async function saveFileOnce(fileName: string, content: string) {
  try {
    const fileHandle = await (window as any).showSaveFilePicker({
      suggestedName: fileName,
      types: [{
        description: 'HTML 文件',
        accept: { 'text/html': ['.html'] }
      }]
    })

    const writable = await fileHandle.createWritable()
    await writable.write(content)
    await writable.close()

    toast.value?.show(`✅ 已保存：${fileName}`)
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      throw error
    }
  }
}

// ========== 降级：下载文件 ==========
function downloadFile(fileName: string, content: string) {
  const blob = new Blob([content], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
  toast.value?.show(`📥 已下载：${fileName}`)
}

// ========== 恢复原始 ==========
function handleReset() {
  if (!originalHtml.value) return
  if (!confirm('确定恢复为文件原始内容？当前编辑会丢失。')) return
  store.setEditContent(originalHtml.value)
  toast.value?.show('↩ 已恢复为原始内容')
}

// ========== 清空编辑内容 ==========
function handleClear() {
  store.setEditContent('')
  toast.value?.show('🗑️ 已清空编辑器')
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
      @clear="handleClear"
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
