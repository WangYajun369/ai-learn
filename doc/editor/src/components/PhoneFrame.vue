<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  width?: number
  height?: number
}>(), {
  width: 375,  // iPhone 6/7/8 尺寸
  height: 667,
})

const isFullscreen = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}
</script>

<template>
  <div class="phone-frame" :class="{ fullscreen: isFullscreen }">
    <!-- 手机外框顶部（听筒+摄像头） -->
    <div class="phone-notch">
      <div class="notch-speaker"></div>
    </div>

    <!-- 手机屏幕内容插槽 -->
    <div class="phone-screen" :style="{ width: width + 'px' }">
      <slot></slot>
    </div>

    <!-- 手机外框底部（Home 键） -->
    <div class="phone-homebar">
      <div class="home-indicator"></div>
    </div>

    <!-- 全屏按钮 -->
    <button class="phone-fullscreen-btn" @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏预览'">
      {{ isFullscreen ? '⤓' : '⤒' }}
    </button>
  </div>
</template>

<style scoped>
.phone-frame {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(145deg, #e0e0e0 0%, #f5f5f5 50%, #e8e8e8 100%);
  border-radius: 40px;
  padding: 12px;
  box-shadow:
    inset 0 2px 4px rgba(255, 255, 255, 0.8),
    inset 0 -2px 4px rgba(0, 0, 0, 0.1),
    0 20px 40px rgba(0, 0, 0, 0.2),
    0 0 0 1px rgba(0, 0, 0, 0.05);
  position: relative;
  transition: all 0.3s ease;
}

.phone-frame.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  border-radius: 0;
  padding: 20px;
  background: rgba(0, 0, 0, 0.9);
}

/* 听筒区域 */
.phone-notch {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
}

.notch-speaker {
  width: 60px;
  height: 6px;
  background: #1a1a1a;
  border-radius: 3px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.5);
}

.fullscreen .phone-notch {
  top: 20px;
}

/* 手机屏幕 */
.phone-screen {
  height: calc(100% - 60px);
  max-height: v-bind('height + "px"');
  background: #fff;
  border-radius: 25px;
  overflow: hidden;
  box-shadow:
    inset 0 0 20px rgba(0, 0, 0, 0.1),
    0 0 0 3px #1a1a1a;
  position: relative;
}

/* Home 键区域 */
.phone-homebar {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
}

.home-indicator {
  width: 100px;
  height: 4px;
  background: #999;
  border-radius: 2px;
}

.fullscreen .phone-homebar {
  bottom: 20px;
}

/* 全屏按钮 */
.phone-fullscreen-btn {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.1);
  color: #666;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.phone-fullscreen-btn:hover {
  background: rgba(0, 0, 0, 0.2);
  color: #333;
}

.fullscreen .phone-fullscreen-btn {
  bottom: 30px;
  right: 30px;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.fullscreen .phone-fullscreen-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 响应式 - 小屏幕时自动缩小手机尺寸 */
@media (max-height: 700px) {
  .phone-frame {
    padding: 8px;
    border-radius: 30px;
  }

  .phone-screen {
    max-height: calc(100vh - 80px);
    border-radius: 20px;
  }

  .notch-speaker {
    width: 50px;
    height: 5px;
  }
}

@media (max-height: 500px) {
  .phone-frame {
    padding: 6px;
    border-radius: 24px;
  }

  .phone-screen {
    max-height: calc(100vh - 60px);
    border-radius: 16px;
  }

  .phone-homebar {
    display: none;
  }

  .phone-notch {
    display: none;
  }
}
</style>
