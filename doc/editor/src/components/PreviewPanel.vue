<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'
import PhoneFrame from './PhoneFrame.vue'

const store = useEditorStore()
const { editContent, isLoading, loadError } = storeToRefs(store)

const iframeRef = ref<HTMLIFrameElement>()

const previewHtml = computed(() => store.getPreviewHtml())

// 防抖：编辑时不要每帧都刷新 iframe，延迟 500ms
let previewTimer: ReturnType<typeof setTimeout> | undefined = undefined

// 通过 iframe 渲染完整 HTML（保留 <style> 标签）
watch(previewHtml, (html) => {
  if (!html || !iframeRef.value) return

  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    const iframe = iframeRef.value
    if (!iframe) return
    const doc = iframe.contentDocument
    if (!doc) return

    // 直接将原始 HTML 包裹在基本文档结构中
    // 微信排版文件本身包含 <style> + body 内容（无 <html>/<body> 标签）
    // 添加 max-width 限制模拟手机宽度
    const fullDoc = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
  body {
    margin: 0;
    padding: 10px 8px;
    max-width: 359px;
    margin-left: auto;
    margin-right: auto;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    -webkit-text-size-adjust: 100% !important;
  }
  img { max-width: 100% !important; height: auto !important; }
  table { max-width: 100% !important; }
  pre, code { white-space: pre-wrap !important; word-break: break-all !important; }
</style>
</head>
<body>
${html}
</body>
</html>`

    doc.open()
    doc.write(fullDoc)
    doc.close()
  }, 300)
}, { immediate: true })

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
})
</script>

<template>
  <div class="preview-panel">
    <div class="preview-header">📱 手机预览</div>
    <div class="preview-area">
      <PhoneFrame :width="375" :height="667">
        <iframe
          v-show="editContent && !isLoading && !loadError"
          ref="iframeRef"
          class="preview-iframe"
        ></iframe>
        <div v-if="isLoading" class="preview-loading">
          <div class="loading-spinner"></div>
          加载中...
        </div>
        <div v-else-if="loadError" class="preview-error">
          <p class="error-icon">⚠️</p>
          <p class="error-title">加载失败</p>
          <p class="error-msg">{{ loadError }}</p>
        </div>
        <div v-else-if="!editContent" class="preview-empty">
          <p>📂</p>
          <p>选择左侧文件</p>
          <p class="empty-hint">以加载预览</p>
        </div>
      </PhoneFrame>
    </div>
  </div>
</template>

<style scoped>
.preview-panel {
  display: flex;
  flex-direction: column;
  min-width: 280px;
  background: #f0f2f5;
  height: 100%;
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
  overflow: hidden;
  position: relative;
  background: linear-gradient(180deg, #e8e8e8 0%, #d0d0d0 100%);
}
.preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
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
}

.preview-empty p {
  margin: 4px 0;
}

.preview-empty .empty-hint {
  font-size: 12px;
  color: #ccc;
}
</style>
