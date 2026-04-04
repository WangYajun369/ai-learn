# 微信公众号文章编辑器

一个基于 Vue 3 的 HTML 可视编辑器，用于创建和编辑微信公众号文章。

## 在线体验

[访问在线演示](https://zhenbangxu.github.io/Editor/)

## 主要功能

- **实时预览**: 编写 HTML 后即时在右侧预览移动端效果
- **多文件管理**: 左侧文件列表，快速切换不同的文章
- **样式编辑**: 支持编辑 HTML、CSS 样式
- **复制功能**: 一键复制编辑好的 HTML 源码到剪贴板
- **文件保存**: 支持下载保存为本地 HTML 文件
- **自动备份**: 保存时自动备份原文件
- **移动端仿真**: 预览区域精确模拟微信公众号文章在 iPhone 上的显示效果

## 项目结构

```
src/
├── main.ts                  # 应用入口
├── App.vue                  # 根组件
├── router/index.ts          # 路由配置
├── stores/editor.ts         # Pinia 状态管理
├── views/
│   └── EditorView.vue      # 主编辑视图
├── components/
│   ├── Toolbar.vue         # 顶部工具栏
│   ├── Sidebar.vue         # 文件列表侧边栏
│   └── Resizer.vue         # 拖动分割线组件
└── assets/
    └── global.css          # 全局样式重置
public/
├── wechat/
│   ├── index.json          # 文件列表配置
│   └── *.html              # 文章模板文件
└── index.html              # 入口 HTML
```

## 技术栈

- **构建工具**: Vite 8
- **前端框架**: Vue 3 (Composition API)
- **语言**: TypeScript
- **状态管理**: Pinia
- **路由**: Vue Router
- **UI 框架**: WeUI (微信官方 UI 库)

## 功能特性

### 侧边栏

- 左侧显示所有可编辑的文章文件列表
- 点击文件快速切换编辑内容
- 支持多标签文章管理

### 中央编辑器

- 使用 HTML textarea 作为编辑区域
- 支持完整的 HTML 源码编辑
- 包含 `<style>` 标签编辑功能
- 实时显示 HTML 结构

### 右侧预览

- 固定 375px 宽度，精确模拟 iPhone 显示效果
- 使用 .preview-content 样式重写 body 选择器
- 自动处理图片最大宽度限制
- 支持微信原生图片组件优化
- 白底内容区域适配移动端布局

### 顶部工具栏

- **"复制源码"**: 通过 Clipboard API 复制 HTML 到剪贴板
- **"另存为 HTML"**: 使用 File System Access API 保存文件 (Chrome/Edge 87+)
  - 可选择目录一次性授权，后续保存无需确认
  - 也可逐文件保存，每次选择保存位置
- 状态显示当前文章是否已修改

### 预览区域

- 灰色背景 + 居中白色内容区域
- 359px 内容宽度 + 左右留白 = 375px 总宽度
- 滚动支持：预览区域可独立滚动
- flex 布局确保内容区底部显示完整

## 快速开始

### 环境要求

- Node.js >= 18
- 现代浏览器（Edge 98+/Chrome 98+ 以获得完整的 File System Access API 支持）

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

访问 `http://localhost:5173` (或 5174 如果 5173 端口被占用)

### 构建生产版本

```bash
npm run build
```

### 预览生产构建

```bash
npm run preview
```

## 开发指南

### 添加新文章

1. 在 `public/wechat/` 目录创建新的 `.html` 文件
2. 在 `index.json` 添加新文件名（如 `["article1.html", "article2.html", "newfile.html"]`）
3. 刷新页面即可在左侧看到新文件

### 修改预览样式

编辑 `EditorView.vue` 中的 `previewHtml` computed 属性，可自定义：
- 移动端内容宽度
- 图片尺寸限制
- 自定义样式注入
- `.preview-content` 选择器的样式规则

### 自定义布局

在 `EditorView.vue` 中调整 resizer 参数：
- `min-left="250"`: 编辑区域最小宽度
- `min-right="410"`: 预览区域最小宽度（需容纳 375px 内容）
- `left-fixed-width="220"`: 左侧文件列表宽度

## 常见问题

### 为什么编辑区域使用 textarea 而不使用代码编辑器？

项目选择简单的 textarea 而非 Monaco/CodeMirror 等编辑器：
- 简化复杂度，避免依赖额外库
- 支持编辑包含 `<style>` 标签的完整 HTML 文档
- 对于微信公众号文章，结构相对稳定，无需语法高亮

### 剪贴板 API 实现说明

Editor 使用两步复制策略：
1. **现代 API**: 优先使用 `navigator.clipboard.write()`，支持 HTML format
2. **降级方案**: 对旧浏览器支持 `document.execCommand('copy')`

### 文件保存的浏览器兼容性

- **File System Access API**: Chrome/Edge 87+
- 降级方案：不支持该 API 的浏览器自动使用下载方式保存

## 许可证

MIT License
