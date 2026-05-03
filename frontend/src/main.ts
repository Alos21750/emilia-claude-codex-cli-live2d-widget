// Polyfill TouchEvent for desktop browsers (Firefox etc.) where it is not defined.
// PixiJS InteractionManager uses `instanceof TouchEvent` internally and throws if missing.
if (typeof globalThis.TouchEvent === 'undefined') {
  (globalThis as any).TouchEvent = class TouchEvent extends UIEvent {}
}

import { createApp } from 'vue'
import DesktopWidget from './pages/DesktopWidget.vue'
import './style.css'

createApp(DesktopWidget).mount('#app')
