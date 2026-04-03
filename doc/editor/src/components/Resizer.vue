<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'

const props = withDefaults(defineProps<{
  /** 左侧面板的 CSS 选择器（通过 closest 匹配） */
  leftSelector: string
  /** 右侧面板的 CSS 选择器 */
  rightSelector: string
  /** 左侧最小宽度 */
  minLeft?: number
  /** 右侧最小宽度 */
  minRight?: number
  /** 容器选择器，默认 .main-layout */
  containerSelector?: string
}>(), {
  minLeft: 180,
  minRight: 200,
  containerSelector: '.main-layout',
})

const resizer = ref<HTMLDivElement>()
let startX = 0
let startLeftWidth = 0
let containerWidth = 0

function onMouseDown(e: MouseEvent) {
  const container = document.querySelector(props.containerSelector)
  if (!container) return

  const leftPanel = container.querySelector(props.leftSelector) as HTMLElement | null
  const rightPanel = container.querySelector(props.rightSelector) as HTMLElement | null
  if (!leftPanel || !rightPanel) return

  startX = e.clientX
  startLeftWidth = leftPanel.offsetWidth
  containerWidth = (container as HTMLElement).offsetWidth

  resizer.value?.classList.add('active')
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  ;(document.body as HTMLElement).style.cursor = 'col-resize'
  ;(document.body as HTMLElement).style.userSelect = 'none'
  e.preventDefault()
}

function onMouseMove(e: MouseEvent) {
  const container = document.querySelector(props.containerSelector)
  if (!container) return

  const leftPanel = container.querySelector(props.leftSelector) as HTMLElement | null
  const rightPanel = container.querySelector(props.rightSelector) as HTMLElement | null
  if (!leftPanel || !rightPanel) return

  const dx = e.clientX - startX
  const newLeft = Math.max(props.minLeft, Math.min(startLeftWidth + dx, containerWidth - props.minRight - 8))
  const newRight = containerWidth - 8 - newLeft // 8 = 两个 resizer 的宽度

  leftPanel.style.width = newLeft + 'px'
  leftPanel.style.flex = 'none'
  rightPanel.style.width = newRight + 'px'
  rightPanel.style.flex = 'none'
}

function onMouseUp() {
  resizer.value?.classList.remove('active')
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  ;(document.body as HTMLElement).style.cursor = ''
  ;(document.body as HTMLElement).style.userSelect = ''
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
})
</script>

<template>
  <div class="resizer" ref="resizer" @mousedown="onMouseDown"></div>
</template>

<style scoped>
.resizer {
  width: 4px;
  cursor: col-resize;
  background: #e8e8e8;
  transition: background 0.15s;
  flex-shrink: 0;
}
.resizer:hover,
.resizer.active {
  background: #667eea;
}
</style>
