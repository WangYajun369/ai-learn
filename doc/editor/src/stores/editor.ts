import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface ArticleFile {
  name: string
  fullPath: string
}

export const useEditorStore = defineStore('editor', () => {
  // ========== 文件列表 ==========
  const fileList = ref<ArticleFile[]>([])
  const fileListLoaded = ref(false)

  // ========== 当前文件 ==========
  const currentFile = ref<ArticleFile | null>(null)
  const originalHtml = ref('')
  const editContent = ref('')
  const isModified = computed(() => editContent.value !== originalHtml.value)
  const isLoading = ref(false)
  const loadError = ref('')

  // ========== 加载文件列表 ==========
  async function loadFileList() {
    try {
      const res = await fetch('/wechat/index.json')
      if (!res.ok) throw new Error('HTTP ' + res.status)
      const files: string[] = await res.json()

      fileList.value = files.map(name => ({
        name,
        fullPath: name.includes('/') ? name : `wechat/${name}`,
      }))
      fileListLoaded.value = true

      // 默认加载第一个文件
      if (fileList.value.length > 0) {
        await loadArticle(fileList.value[0])
      }
    } catch {
      fileList.value = []
      fileListLoaded.value = true
    }
  }

  // ========== 加载文章 ==========
  async function loadArticle(file: ArticleFile) {
    if (isModified.value) {
      if (!confirm('当前文件有未保存的修改，切换文件会丢失更改。是否继续？')) {
        return false
      }
    }

    currentFile.value = file
    isLoading.value = true
    loadError.value = ''

    try {
      const res = await fetch('/' + file.fullPath)
      if (!res.ok) throw new Error('HTTP ' + res.status)
      const html = await res.text()

      originalHtml.value = html
      editContent.value = html
      return true
    } catch (e: any) {
      loadError.value = e.message || '加载失败'
      originalHtml.value = ''
      editContent.value = ''
      return false
    } finally {
      isLoading.value = false
    }
  }

  // ========== 编辑 ==========
  function setEditContent(content: string) {
    editContent.value = content
  }

  // ========== 恢复原始 ==========
  function resetToOriginal() {
    if (!originalHtml.value) return
    if (!confirm('确定恢复为文件原始内容？当前编辑会丢失。')) return
    editContent.value = originalHtml.value
  }

  // ========== 从完整 HTML 中提取 body 内容（用于可视化编辑）==========
  function extractBodyContent(html: string): string {
    // 匹配 <body> 或直接内容
    const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i)
    if (bodyMatch) {
      return bodyMatch[1].trim()
    }
    // 如果没有 <body> 标签，提取 </style> 之后的内容（微信排版文件格式）
    const styleEndMatch = html.match(/<\/style>([\s\S]*)$/i)
    if (styleEndMatch) {
      return styleEndMatch[1].trim()
    }
    // 没有匹配，返回原始内容
    return html
  }

  // ========== 从完整 HTML 中提取 style 标签内容 ==========
  function extractStyleContent(html: string): string {
    const styleMatch = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi)
    return styleMatch ? styleMatch.join('\n') : ''
  }

  // ========== 获取预览 HTML（完整 HTML）==========
  function getPreviewHtml() {
    return editContent.value
  }

  return {
    fileList,
    fileListLoaded,
    currentFile,
    originalHtml,
    editContent,
    isModified,
    isLoading,
    loadError,
    loadFileList,
    loadArticle,
    setEditContent,
    resetToOriginal,
    extractBodyContent,
    extractStyleContent,
    getPreviewHtml,
  }
})
