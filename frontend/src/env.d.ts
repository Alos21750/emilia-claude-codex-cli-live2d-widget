/// <reference types="vite/client" />

interface Window {
  desktopWidget?: {
    close: () => void
    reload: () => void
    startDrag?: (screenX: number, screenY: number) => void
    dragMove?: (screenX: number, screenY: number) => void
    endDrag?: () => void
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
} 
