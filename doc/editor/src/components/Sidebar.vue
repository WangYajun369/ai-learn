<script setup lang="ts">
import { useEditorStore } from '../stores/editor'
import { storeToRefs } from 'pinia'

const store = useEditorStore()
const { fileList, fileListLoaded, currentFile } = storeToRefs(store)

function displayName(file: { name: string }) {
  return file.name.split('/').pop() || file.name
}

async function selectFile(file: typeof fileList.value[0]) {
  await store.loadArticle(file)
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      📂 文件列表
      <span class="count" v-if="fileListLoaded">{{ fileList.length }}</span>
    </div>
    <div class="file-list">
      <div v-if="!fileListLoaded" class="sidebar-empty">加载中...</div>
      <div v-else-if="fileList.length === 0" class="sidebar-empty">
        暂无文章<br />请将 *_wechat.html 放入<br />wechat/ 目录
      </div>
      <div
        v-for="file in fileList"
        v-else
        :key="file.fullPath"
        class="file-item"
        :class="{ active: currentFile?.fullPath === file.fullPath }"
        @click="selectFile(file)"
      >
        <span class="file-icon">📄</span>
        <span class="file-name">{{ displayName(file) }}</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  min-width: 140px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.sidebar-header {
  padding: 14px 16px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.sidebar-header .count {
  font-size: 11px;
  font-weight: 400;
  color: #aaa;
  background: #f5f5f5;
  padding: 1px 8px;
  border-radius: 10px;
}
.file-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.file-item {
  padding: 9px 16px;
  font-size: 13px;
  color: #444;
  cursor: pointer;
  transition: all 0.15s;
  border-left: 3px solid transparent;
  display: flex;
  align-items: center;
  gap: 8px;
}
.file-item:hover {
  background: #f7f8fc;
  color: #667eea;
}
.file-item.active {
  background: #eef0ff;
  color: #667eea;
  border-left-color: #667eea;
  font-weight: 500;
}
.file-item .file-icon {
  flex-shrink: 0;
  font-size: 14px;
  opacity: 0.6;
}
.file-item .file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-empty {
  padding: 30px 20px;
  text-align: center;
  color: #ccc;
  font-size: 13px;
  line-height: 1.8;
}
</style>
