<script setup lang="ts">
import { ref } from 'vue'

interface StyleItem {
  id: string
  name: string
  thumbnail?: string
  category: string
}

const props = defineProps<{
  styles: StyleItem[]
}>()

const emit = defineEmits<{
  select: [style: StyleItem]
}>()

const activeCategory = ref('全部')
const categories = ['全部', '标题', '正文', '图文', '引导', '布局']

function selectStyle(style: StyleItem) {
  emit('select', style)
}
</script>

<template>
  <div class="style-panel">
    <!-- 分类标签 -->
    <div class="category-tabs">
      <button
        v-for="cat in categories"
        :key="cat"
        class="tab-btn"
        :class="{ active: activeCategory === cat }"
        @click="activeCategory = cat"
      >
        {{ cat }}
      </button>
    </div>

    <!-- 样式列表 -->
    <div class="style-list">
      <div
        v-for="style in styles.filter(s => activeCategory === '全部' || s.category === activeCategory)"
        :key="style.id"
        class="style-item"
        @click="selectStyle(style)"
      >
        <div class="style-preview">
          <div v-if="style.thumbnail" class="thumbnail">
            <img :src="style.thumbnail" :alt="style.name">
          </div>
          <div v-else class="placeholder">
            <span class="placeholder-icon">🎨</span>
            <span class="placeholder-text">{{ style.name }}</span>
          </div>
        </div>
        <div class="style-name">{{ style.name }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.style-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

/* 分类标签 */
.category-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 12px 8px;
  border-bottom: 1px solid #f0f0f0;
  overflow-x: auto;
  flex-shrink: 0;
}

.tab-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  background: #f5f5f5;
  color: #666;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab-btn:hover {
  background: #e8e8e8;
}

.tab-btn.active {
  background: #667eea;
  color: #fff;
}

/* 样式列表 */
.style-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.style-item {
  cursor: pointer;
  transition: all 0.2s;
}

.style-item:hover {
  transform: translateY(-2px);
}

.style-preview {
  aspect-ratio: 4/3;
  background: #f8f8f8;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e8e8e8;
  transition: all 0.2s;
}

.style-item:hover .style-preview {
  border-color: #667eea;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.thumbnail {
  width: 100%;
  height: 100%;
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
}

.placeholder-icon {
  font-size: 24px;
}

.placeholder-text {
  font-size: 12px;
  color: #999;
  text-align: center;
  padding: 0 8px;
}

.style-name {
  margin-top: 6px;
  font-size: 12px;
  color: #666;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 滚动条美化 */
.style-list::-webkit-scrollbar {
  width: 6px;
}

.style-list::-webkit-scrollbar-track {
  background: transparent;
}

.style-list::-webkit-scrollbar-thumb {
  background: #ddd;
  border-radius: 3px;
}

.style-list::-webkit-scrollbar-thumb:hover {
  background: #ccc;
}
</style>
