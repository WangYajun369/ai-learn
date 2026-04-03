import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'editor',
      component: () => import('../views/EditorView.vue'),
    },
  ],
})

export default router
