<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
const props = withDefaults(defineProps<{
  msg: string
  duration?: number
}>(), {
  duration: 2500,
})
const visible = ref(false)
const currentMsg = ref(props.msg)
let timer: ReturnType<typeof setTimeout> | undefined = undefined

function show(_msg?: string) {
  currentMsg.value = _msg || ''
  visible.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    visible.value = false
  }, props.duration)
}

defineExpose({ show })
onUnmounted(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="toast" :class="{ show: visible }">{{ currentMsg }}</div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 60px;
  left: 50%;
  transform: translateX(-50%) translateY(-20px);
  background: #52c41a;
  color: #fff;
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(82, 196, 26, 0.3);
  opacity: 0;
  pointer-events: none;
  transition: all 0.3s ease;
  z-index: 200;
  white-space: nowrap;
}
.toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
</style>
