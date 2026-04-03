<script setup lang="ts">
const emit = defineEmits<{
  save: []
  copy: []
  reset: []
  preview: []
}>()

const actions = [
  { id: 'copy', icon: '📋', label: '一键复制', desc: '复制到公众号', color: '#667eea' },
  { id: 'save', icon: '💾', label: '保存文件', desc: '下载 HTML', color: '#52c41a' },
  { id: 'preview', icon: '👁️', label: '全屏预览', desc: '页面预览', color: '#1890ff' },
  { id: 'reset', icon: '↩', label: '恢复原始', desc: '撤销所有修改', color: '#faad14' },
]
</script>

<template>
  <div class="actions-panel">
    <div class="panel-title">操作面板</div>

    <div class="action-list">
      <button
        v-for="action in actions"
        :key="action.id"
        class="action-btn"
        :style="{ '--btn-color': action.color }"
        @click="emit(action.id as any)"
      >
        <span class="action-icon">{{ action.icon }}</span>
        <div class="action-text">
          <span class="action-label">{{ action.label }}</span>
          <span class="action-desc">{{ action.desc }}</span>
        </div>
      </button>
    </div>

    <div class="panel-footer">
      <div class="tips">
        <div class="tips-title">💡 提示</div>
        <ul class="tips-list">
          <li>Ctrl+S 保存文件</li>
          <li>点击"一键复制"可直接粘贴到公众号</li>
          <li>可视化模式下可直接编辑文字</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.actions-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.panel-title {
  padding: 14px 16px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-bottom: 1px solid #f0f0f0;
}

.action-list {
  flex: 1;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.action-btn:hover {
  border-color: var(--btn-color);
  background: color-mix(in srgb, var(--btn-color) 5%, #fff);
  transform: translateX(4px);
}

.action-btn:active {
  transform: translateX(2px);
}

.action-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--btn-color) 10%, #fff);
  border-radius: 8px;
}

.action-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.action-desc {
  font-size: 12px;
  color: #999;
}

/* 底部提示 */
.panel-footer {
  padding: 16px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.tips-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.tips-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #888;
  line-height: 1.8;
}

.tips-list li {
  margin: 0;
}

/* 滚动条 */
.action-list::-webkit-scrollbar,
.panel-footer::-webkit-scrollbar {
  width: 4px;
}

.action-list::-webkit-scrollbar-track,
.panel-footer::-webkit-scrollbar-track {
  background: transparent;
}

.action-list::-webkit-scrollbar-thumb,
.panel-footer::-webkit-scrollbar-thumb {
  background: #ddd;
  border-radius: 2px;
}
</style>
