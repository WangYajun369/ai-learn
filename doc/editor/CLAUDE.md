# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WeChat Article Editor - a web-based visual editor for creating and editing WeChat public account articles. It provides a split-pane interface with visual/source editing modes and mobile preview.

## Development Commands

```bash
# Install dependencies
npm install

# Start development server (runs on port 5173)
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
- **Rich Text Editor**: WangEditor (`@wangeditor/editor-for-vue`)
- **State Management**: Pinia
- **Routing**: Vue Router

## Architecture

### Application Structure

```
src/
├── main.ts                 # App entry point
├── App.vue                 # Root component
├── router/
│   └── index.ts           # Single route to EditorView
├── stores/
│   └── editor.ts          # Pinia store for editor state
├── views/
│   └── EditorView.vue     # Main editor layout
└── components/
    ├── VisualEditor.vue   # WangEditor wrapper
    ├── EditorPanel.vue    # Split-pane editor (visual/source modes)
    ├── PreviewPanel.vue   # Mobile preview in PhoneFrame
    ├── PhoneFrame.vue     # iPhone frame component
    ├── Toolbar.vue        # Top toolbar
    ├── StylePanel.vue     # Left style templates panel
    ├── ActionsPanel.vue   # Right actions panel
    ├── Resizer.vue        # Draggable panel resizer
    ├── Sidebar.vue        # File list sidebar (unused in current layout)
    └── AppToast.vue       # Toast notifications
```

### Data Flow

1. **File Loading**: `editor.ts` store loads HTML files from `/wechat/index.json` and `/wechat/{filename}.html`
2. **Editing**:
   - Visual mode uses WangEditor (edits body content only)
   - Source mode uses textarea (edits full HTML including `<style>` tags)
3. **Preview**: Rendered in iframe via `PreviewPanel.vue` with mobile viewport constraints
4. **Persistence**: Currently saves via browser download (no backend)

### Key Patterns

**HTML Content Split**: WeChat articles have a specific format:
- `<style>` tags containing CSS (maintained across edits in source mode)
- Body content edited in visual mode
- Store provides `extractBodyContent()` and `extractStyleContent()` helpers

**Editor Sync**: `EditorPanel.vue` maintains two-way sync between visual and source modes using Vue's `watch` and debouncing.

**IFrame Isolation**: Preview uses an iframe to safely render WeChat's HTML without polluting the main app's styles.

**Layout Resizing**: `Resizer.vue` enables draggable panel resizing with CSS selector-based targeting.

## File System

- **Source files**: Located in `../` (doc/) directory
- **Public assets**: `public/wechat/` contains HTML articles for editing
- **File list**: `public/wechat/index.json` - array of article filenames

## Vite Configuration Notes

- Vite dev server runs on port 5173
- `fs.allow` includes `..` to access parent directory files
- Path alias `@` maps to `src/`

## WangEditor Integration

- CSS imported globally in `main.ts`
- Editor toolbar configured to exclude video features (not supported by WeChat)
- Image upload disabled (base64 images handled internally)
- Editor instance stored in `shallowRef` for Toolbar access

## Mobile Preview

- Simulates iPhone 6/7/8 dimensions (375x667px)
- Content constrained to 359px width to match WeChat mobile view
- Fullscreen mode available for better preview experience
