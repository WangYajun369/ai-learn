import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
// 全局样式
import './assets/global.css'
// WangEditor 样式（全局引入，确保编辑器正常显示）
import '@wangeditor/editor/dist/css/style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
