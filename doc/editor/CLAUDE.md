# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WeChat Article Editor - a web-based HTML editor for creating and editing WeChat public account articles. It provides a three-column layout: file list (left) | source editor (center) | mobile preview (right).

## Development Commands

```bash
# Install dependencies
npm install

# Start development server (runs on port 5173, or 5174 if occupied)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Type checking
vue-tsc -b
```

## Tech Stack

- **Framework**: Vue 3 with Composition API (`<script setup>`)
- **Language**: TypeScript
- **Build Tool**: Vite 8
- **State Management**: Pinia
- **Routing**: Vue Router

## Architecture

### Application Structure

```
src/
├── main.ts                 # App entry point
├── assets/
│   └── global.css         # Global styles (CSS reset)
├── App.vue                 # Root component
├── router/
│   └── index.ts           # Single route to EditorView
├── stores/
│   └── editor.ts          # Pinia store for editor state
├── views/
│   └── EditorView.vue     # Main editor layout
└── components/
    ├── Toolbar.vue        # Top toolbar with save/copy actions
    ├── Sidebar.vue        # File list sidebar
    ├── Resizer.vue        # Draggable panel resizer
    └── AppToast.vue       # Toast notifications
```

### Layout Structure

**Three-column layout (EditorView.vue):**
- **Left**: File list (220px fixed width)
- **Center**: Source HTML editor (initially 50%, draggable)
- **Right**: Mobile preview (375px fixed width content, centered in gray area)

**Resizer Configuration:**
- `min-left="250"`: Minimum editor width
- `min-right="410"`: Minimum preview panel width (ensures 375px mobile content fits)
- `left-fixed-width="220"`: Sidebar width (must be subtracted from calculations)

### Data Flow

1. **File Loading**: `editor.ts` store loads HTML files from `/wechat/index.json` and `/wechat/{filename}.html`
2. **Editing**: Uses textarea for full HTML editing including `<style>` tags
3. **Preview**: Rendered via `v-html` with mobile viewport constraints injected
4. **Persistence**: Currently saves via browser download (no backend)

### Key Patterns

**Mobile Preview Styles**: The preview area uses a computed property `previewHtml` that:
- Replaces `body` selectors with `.preview-content`
- Injects mobile-specific styles (359px max-width, image constraints, etc.)
- Ensures content fits WeChat mobile view

**Preview Layout**:
- `.preview-area`: Gray background, scrollable
- `.preview-container`: Fixed 375px width (iPhone), flex: 1
- `.preview-content`: White background with shadow, min-height 667px

**Important**: The `.preview-content` uses `flex: 1` combined with parent `.preview-container` having `flex: 1` and `.preview-area` having `min-height: 0` - this is a CSS flexbox pattern to ensure the white background extends to the bottom.

## File System

- **Source files**: Located in `public/wechat/`
- **File list**: `public/wechat/index.json` - array of article filenames
- **Global styles**: `src/assets/global.css` contains CSS reset

## Store API (editor.ts)

Key reactive state and methods:
- `fileList`: Array of available articles
- `currentFile`: Currently selected article
- `editContent`: Current HTML content (editable)
- `originalHtml`: Original file content (for reset/compare)
- `isModified`: Computed flag showing unsaved changes
- `loadFileList()`: Fetch and parse index.json
- `loadArticle(file)`: Load specific article HTML
- `setEditContent(content)`: Update editor content
- `resetToOriginal()`: Revert to original file content

## Clipboard/Copy Functionality

Toolbar.vue implements two copy methods:
1. **Modern API**: `navigator.clipboard.write()` with ClipboardItem (HTML format)
2. **Fallback**: `document.execCommand('copy')` with temporary contenteditable div

## File System Access API

EditorView.vue uses the File System Access API for direct file saving (Chrome/Edge 87+):

**Save Options:**
1. **Directory Access**: User selects a directory once, subsequent saves write directly without confirmation
2. **Single File Save**: Each save prompts user for file location

**Backup Feature:**
- Automatically backs up existing files before overwriting
- Backup file name format: `originalname.backup.YYYYMMDD-HHMMSS-SSS`
- Example: `article.html.backup.20250103-123456-789`

**Fallback**: For browsers without File System Access API support, automatically falls back to file download.

## Global CSS Reset

`src/assets/global.css` contains:
- `* { margin: 0; padding: 0; box-sizing: border-box; }`
- `html, body { height: 100%; overflow: hidden; }`

**Note**: Do NOT use `:deep(*)` in scoped styles as it will break child component styles.
