/// <reference types="vite/client" />

interface Window {
  desktopWidget?: {
    close: () => void
    reload: () => void
    startDrag?: (screenX: number, screenY: number) => void
    dragMove?: (screenX: number, screenY: number) => void
    endDrag?: () => void
    startResize?: (screenX: number, screenY: number) => void
    resizeMove?: (screenX: number, screenY: number) => void
    endResize?: () => void
    applySize?: (width: number, height: number) => void
    setAlwaysOnTop?: (value: boolean) => void
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
} 
