<script setup lang="ts">
import { ref } from 'vue'
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'

const store = useEditorStore()
const { currentFile, editContent } = storeToRefs(store)

const emit = defineEmits<{
  save: []
  reset: []
  copied: []
  'select-all': []
}>()

// 复制按钮引用（保留用于可能的未来扩展）
const _copyBtn = ref<HTMLButtonElement | null>(null)
void _copyBtn // 避免未使用警告

function saveFile() {
  emit('save')
}

function resetEditor() {
  emit('reset')
}

async function copyToWechat() {
  const htmlContent = editContent.value
  if (!htmlContent.trim()) return

  try {
    if (navigator.clipboard && navigator.clipboard.write) {
      const blob = new Blob([htmlContent], { type: 'text/html' })
      const item = new ClipboardItem({ 'text/html': blob })
      await navigator.clipboard.write([item])
      emit('copied')
      return
    }
  } catch {
    // fallback
  }

  // fallback: execCommand
  const tempDiv = document.createElement('div')
  tempDiv.setAttribute('contenteditable', 'true')
  tempDiv.style.cssText = 'position:fixed;left:-9999px;top:0;background:transparent;color:inherit;'
  tempDiv.innerHTML = htmlContent
  document.body.appendChild(tempDiv)

  const range = document.createRange()
  range.selectNodeContents(tempDiv)
  const selection = window.getSelection()
  selection!.removeAllRanges()
  selection!.addRange(range)

  let success = false
  try {
    success = document.execCommand('copy')
  } catch {
    // ignore
  }
  selection!.removeAllRanges()
  document.body.removeChild(tempDiv)

  if (success) {
    emit('copied')
  } else {
    alert('复制失败，请手动全选后 Ctrl+C / Cmd+C')
  }
}

function selectAll() {
  emit('select-all')
}
</script>

<template>
  <div class="toolbar">
    <span class="logo">📝 微信排版工具</span>
    <span class="file-info">{{ currentFile?.name || '-' }}</span>
    <span class="spacer"></span>
    <button class="btn btn-secondary btn-sm" @click="resetEditor" title="放弃编辑，恢复为文件原始内容">
      ↩ 恢复原始
    </button>
    <button class="btn btn-success btn-sm" @click="saveFile" title="保存编辑内容到文件">
      💾 保存文件
    </button>
    <span class="toolbar-sep"></span>
    <button class="btn btn-secondary btn-sm" @click="selectAll" title="全选文章内容">
      📋 全选
    </button>
    <button ref="copyBtn" class="btn btn-primary" @click="copyToWechat" title="复制后可直接粘贴到微信公众号后台">
      📌 一键复制到微信
    </button>
  </div>
</template>

<style scoped>
.toolbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
}
.logo {
  font-weight: 700;
  font-size: 16px;
  color: #667eea;
  margin-right: 4px;
  white-space: nowrap;
}
.file-info {
  font-size: 13px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}
.spacer {
  flex: 1;
}
.toolbar-sep {
  width: 1px;
  height: 20px;
  background: #e0e0e0;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.btn-primary {
  background: #667eea;
  color: #fff;
}
.btn-primary:hover {
  background: #5a6fd6;
  transform: translateY(-1px);
}
.btn-primary:active {
  transform: translateY(0);
}
.btn-primary.copied {
  background: #52c41a;
}
.btn-secondary {
  background: #f5f5f5;
  color: #555;
  border: 1px solid #d9d9d9;
}
.btn-secondary:hover {
  background: #e8e8e8;
}
.btn-success {
  background: #52c41a;
  color: #fff;
}
.btn-success:hover {
  background: #45a818;
  transform: translateY(-1px);
}
.btn-success:active {
  transform: translateY(0);
}
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
</style>
