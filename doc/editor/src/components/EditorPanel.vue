<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'
import VisualEditor from './VisualEditor.vue'

const store = useEditorStore()
const { editContent, isModified, isLoading } = storeToRefs(store)

const emit = defineEmits<{
  'save': []
}>()

// 模式切换：visual（可视化）/ source（源码）
const mode = ref<'visual' | 'source'>('visual')
const sourceEditor = ref<HTMLTextAreaElement>()
// visualEditorRef 保留用于可能的未来扩展
const _visualEditorRef = ref<InstanceType<typeof VisualEditor> | null>(null)
void _visualEditorRef // 避免未使用警告

// 防抖定时器（用于预览更新延迟）
let previewDebounce: ReturnType<typeof setTimeout> | undefined = undefined

// 同步 visual 编辑器的值
const visualContent = ref('')

// 从 store 加载内容 - 更新到两个编辑器
watch(editContent, (val) => {
  if (mode.value === 'source') {
    nextTick(() => {
      if (sourceEditor.value && sourceEditor.value !== document.activeElement) {
        sourceEditor.value.value = val
      }
    })
  } else {
    // 可视化模式：从完整 HTML 中提取 body 内容
    const bodyContent = store.extractBodyContent(val)
    visualContent.value = bodyContent
  }
}, { immediate: true })

// 可视化编辑器内容变化
function handleVisualChange(html: string) {
  // 将 body 内容重新组合为完整 HTML
  const stylePart = store.extractStyleContent(store.editContent)
  const fullHtml = stylePart + '\n' + html
  store.setEditContent(fullHtml)
}

// 源码编辑变化（带防抖，避免频繁更新 store 触发预览刷新）
function handleSourceInput() {
  if (previewDebounce) clearTimeout(previewDebounce)
  previewDebounce = setTimeout(() => {
    const val = sourceEditor.value?.value || ''
    store.setEditContent(val)
  }, 300)
}

// 切换模式
function toggleMode() {
  if (mode.value === 'visual') {
    // 可视化 → 源码：先获取当前内容
    mode.value = 'source'
    nextTick(() => {
      if (sourceEditor.value) {
        sourceEditor.value.value = store.editContent
      }
    })
  } else {
    // 源码 → 可视化
    mode.value = 'visual'
    nextTick(() => {
      const bodyContent = store.extractBodyContent(store.editContent)
      visualContent.value = bodyContent
    })
  }
}

// Ctrl+S 快捷键
function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    emit('save')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (previewDebounce) clearTimeout(previewDebounce)
})
</script>

<template>
  <div class="editor-panel">
    <div class="editor-header">
      <span class="editor-label">✏️ 编辑器</span>
      <span class="modified-dot" :class="{ show: isModified }" title="内容已修改，未保存"></span>
      <span class="spacer"></span>
      <div class="mode-switch">
        <button
          class="mode-btn"
          :class="{ active: mode === 'visual' }"
          @click="mode !== 'visual' && toggleMode()"
          title="可视化编辑模式（使用富文本编辑器）"
        >
          🎨 可视化
        </button>
        <button
          class="mode-btn"
          :class="{ active: mode === 'source' }"
          @click="mode !== 'source' && toggleMode()"
          title="源码编辑模式（编辑完整 HTML 含样式）"
        >
          &lt;/&gt; 源码
        </button>
      </div>
      <span class="editor-hint">Ctrl+S 保存</span>
    </div>
    <div class="editor-body">
      <div v-if="isLoading" class="editor-loading">加载中...</div>
      <!-- 可视化模式：使用 WangEditor 富文本编辑器 -->
      <VisualEditor
        v-else-if="mode === 'visual'"
        ref="visualEditorRef"
        v-model="visualContent"
        placeholder="开始编辑文章内容..."
        @update:model-value="handleVisualChange"
      />
      <!-- 源码模式 -->
      <textarea
        v-else
        ref="sourceEditor"
        class="source-editor"
        spellcheck="false"
        placeholder="选择左侧文件后，HTML 源码会显示在这里..."
        @input="handleSourceInput"
      ></textarea>
    </div>
  </div>
</template>

<style scoped>
.editor-panel {
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
  border-right: 1px solid #e8e8e8;
  height: 100%;
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
.mode-switch {
  display: flex;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  overflow: hidden;
}
.mode-btn {
  padding: 3px 12px;
  font-size: 12px;
  border: none;
  background: #f5f5f5;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
  white-space: nowrap;
}
.mode-btn.active {
  background: #667eea;
  color: #fff;
}
.mode-btn:not(.active):hover {
  background: #e8e8e8;
}
.editor-hint {
  font-size: 11px;
  color: #bbb;
  font-weight: 400;
  margin-left: 8px;
}
.editor-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
  min-height: 0;
}
.editor-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #bbb;
  font-size: 14px;
}

/* ====== 源码编辑器 ====== */
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
</style>
