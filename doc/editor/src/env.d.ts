/// <reference types="vite/client" />

// WangEditor Vue 组件类型声明
declare module '@wangeditor/editor-for-vue' {
  import { DefineComponent } from 'vue'

  export const Editor: DefineComponent<{
    modelValue?: string
    defaultConfig?: Record<string, any>
    mode?: 'default' | 'simple'
    onChange?: (editor: any) => void
    onCreated?: (editor: any) => void
    onDestroyed?: (editor: any) => void
  }>

  export const Toolbar: DefineComponent<{
    defaultConfig?: Record<string, any>
    editor?: { getEditor: () => any } | null
    mode?: 'default' | 'simple'
  }>
}
