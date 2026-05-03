<template>
  <main class="desktop-widget-shell">
    <div class="desktop-widget-controls">
      <button type="button" title="重新載入" @click="reloadWindow">↻</button>
      <button type="button" title="關閉" @click="closeWindow">×</button>
    </div>

    <section class="desktop-widget-stage" :class="statusClass">
      <div class="drag-handle" aria-hidden="true"></div>
      <div
        class="resize-handle no-drag"
        aria-hidden="true"
        @pointerdown="onResizeDown"
        @pointermove="onResizeMove"
        @pointerup="onResizeUp"
        @pointercancel="onResizeCancel"
      ></div>
      <select v-model="selectedModelKey" class="desktop-widget-model-picker no-drag" aria-label="Live2D character">
        <option v-for="item in EMILIA_MODELS" :key="item.key" :value="item.key">
          {{ item.displayName }}
        </option>
      </select>

      <DesktopWidgetLive2D :state="monitor.activeState.value" :modelKey="selectedModelKey" />
      <div class="status-bubble">
        <span class="status-dot"></span>
        <span>{{ monitor.activeStateText.value }}</span>
      </div>
    </section>

    <footer class="desktop-widget-status">
      <div class="session-row">
        <span class="brand">{{ monitor.brandName.value }}</span>
        <span class="session-name">{{ sessionName }}</span>
      </div>
      <div class="quota-row">
        <span class="brand-label brand-label--claude">Claude</span>
        <span class="quota-value">{{ claudeQuota }}</span>
      </div>
      <div class="quota-row">
        <span class="brand-label brand-label--codex">Codex</span>
        <span class="quota-value">{{ codexQuota }}</span>
      </div>
    </footer>

  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import DesktopWidgetLive2D from '../components/DesktopWidgetLive2D.vue'
import { getSessionActivityEpoch } from '../utils/sessionStageState'
import { isDesktopWidgetWarmupSession, useDesktopWidgetMonitor } from '../composables/desktopWidgetMonitor'
import type { DesktopWidgetSession } from '../composables/desktopWidgetMonitor'
import { DEFAULT_EMILIA_KEY, EMILIA_MODELS, isValidEmiliaKey } from '../composables/emiliaModels'

const monitor = useDesktopWidgetMonitor()
const selectedModelKey = ref<string>(loadInitialModelKey())
const resizeStart = ref<{ screenX: number; screenY: number; pointerId: number } | null>(null)
const WIDGET_SIZE_STORAGE_KEY = 'desktopWidget.size'

const sessionName = computed(() => monitor.activeSession.value?.display_name || 'Bridge monitor')
const statusClass = computed(() => ({
  'is-disconnected': monitor.connectionStatus.value === 'disconnected',
  'is-connected': monitor.connectionStatus.value === 'connected',
}))
const claudeQuota = computed(() => {
  const usage = monitor.claudeUsage.value
  if (usage) {
    const fiveHour = usage.five_hour?.remaining
    const sevenDay = usage.seven_day?.remaining
    const parts: string[] = []
    if (typeof fiveHour === 'number') parts.push(`5h ${Math.round(fiveHour)}%`)
    if (typeof sevenDay === 'number') parts.push(`7d ${Math.round(sevenDay)}%`)
    if (parts.length > 0) return parts.join(' / ')
  }
  return formatBrandQuota(pickLatestSessionForBrand('claude'))
})
const codexQuota = computed(() => formatBrandQuota(pickLatestSessionForBrand('codex')))

function pickLatestSessionForBrand(brand: 'codex' | 'claude'): DesktopWidgetSession | null {
  return monitor.sessions.value
    .filter((s) => !isDesktopWidgetWarmupSession(s))
    .filter((s) => (s.agent_brand || 'codex').toLowerCase() === brand)
    .sort((a, b) => getSessionActivityEpoch(b) - getSessionActivityEpoch(a))[0] || null
}

function formatBrandQuota(session: DesktopWidgetSession | null): string {
  if (!session?.context) return '—'
  const ctx = session.context
  const p = ctx.primary_rate_remaining_percent
  const s = ctx.secondary_rate_remaining_percent
  if (typeof p === 'number' || typeof s === 'number') {
    const parts: string[] = []
    if (typeof p === 'number') parts.push(`P ${Math.round(p)}%`)
    if (typeof s === 'number') parts.push(`S ${Math.round(s)}%`)
    return parts.join(' / ')
  }
  const used = ctx.total_tokens
  const limit = ctx.model_context_window
  if (typeof used === 'number' && typeof limit === 'number' && limit > 0) {
    const pct = Math.round((used / limit) * 100)
    return `${pct}% ctx`
  }
  return '—'
}

function loadInitialModelKey(): string {
  try {
    const stored = localStorage.getItem('desktopWidget.modelKey') || ''
    return isValidEmiliaKey(stored) ? stored : DEFAULT_EMILIA_KEY
  } catch {
    return DEFAULT_EMILIA_KEY
  }
}

watch(selectedModelKey, (key) => {
  try {
    localStorage.setItem('desktopWidget.modelKey', key)
  } catch {
    // ignore unavailable storage
  }
})

onMounted(() => {
  restoreWidgetSize()
})

function closeWindow(): void {
  window.desktopWidget?.close()
}

function reloadWindow(): void {
  window.desktopWidget?.reload()
}

function restoreWidgetSize(): void {
  try {
    const stored = localStorage.getItem(WIDGET_SIZE_STORAGE_KEY)
    if (!stored) return
    const parsed = JSON.parse(stored) as { w?: unknown; h?: unknown }
    const w = Number(parsed.w)
    const h = Number(parsed.h)
    if (!Number.isFinite(w) || !Number.isFinite(h)) return
    if (w < 1 || h < 1) return
    window.desktopWidget?.applySize?.(w, h)
  } catch {
    // ignore unavailable or invalid storage
  }
}

function persistWidgetSize(): void {
  try {
    localStorage.setItem(WIDGET_SIZE_STORAGE_KEY, JSON.stringify({
      w: Math.round(window.innerWidth),
      h: Math.round(window.innerHeight),
    }))
  } catch {
    // ignore unavailable storage
  }
}

function onResizeDown(e: PointerEvent): void {
  e.preventDefault()
  e.stopPropagation()
  const screenX = Math.round(e.screenX)
  const screenY = Math.round(e.screenY)
  resizeStart.value = {
    screenX,
    screenY,
    pointerId: e.pointerId,
  }
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  window.desktopWidget?.startResize?.(screenX, screenY)
}

function onResizeMove(e: PointerEvent): void {
  if (!resizeStart.value || resizeStart.value.pointerId !== e.pointerId) return
  if (e.buttons === 0) return
  e.preventDefault()
  e.stopPropagation()
  window.desktopWidget?.resizeMove?.(Math.round(e.screenX), Math.round(e.screenY))
}

function finishResize(target: HTMLElement | null, pointerId: number | undefined): void {
  if (target && pointerId != null) {
    try {
      target.releasePointerCapture?.(pointerId)
    } catch {
      // ignore stale pointer capture
    }
  }
  resizeStart.value = null
}

function onResizeUp(e: PointerEvent): void {
  if (!resizeStart.value || resizeStart.value.pointerId !== e.pointerId) return
  e.preventDefault()
  e.stopPropagation()
  window.desktopWidget?.endResize?.()
  finishResize(e.currentTarget as HTMLElement, e.pointerId)
  window.requestAnimationFrame(() => {
    persistWidgetSize()
  })
}

function onResizeCancel(e: PointerEvent): void {
  if (!resizeStart.value || resizeStart.value.pointerId !== e.pointerId) return
  e.preventDefault()
  e.stopPropagation()
  window.desktopWidget?.endResize?.()
  finishResize(e.currentTarget as HTMLElement, e.pointerId)
}
</script>

<style scoped>
.desktop-widget-shell {
  position: relative;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  border-radius: 16px;
  color: #f8fbff;
  background: transparent;
  user-select: none;
  -webkit-app-region: drag;
}

.desktop-widget-controls {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 20;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 160ms ease;
  -webkit-app-region: no-drag;
}

.desktop-widget-shell:hover .desktop-widget-controls {
  opacity: 1;
}

.desktop-widget-controls button {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 28%);
  border-radius: 999px;
  color: #f8fbff;
  font-size: 17px;
  line-height: 1;
  background: rgb(12 18 28 / 72%);
  box-shadow: 0 8px 24px rgb(0 0 0 / 18%);
  cursor: pointer;
}

.no-drag {
  -webkit-app-region: no-drag;
}

.desktop-widget-stage {
  position: relative;
  min-height: 0;
  padding: 36px 18px 0;
}

.drag-handle {
  position: absolute;
  top: 14px;
  left: 50%;
  z-index: 5;
  width: 44px;
  height: 4px;
  border-radius: 999px;
  background: rgb(255 255 255 / 36%);
  pointer-events: none;
  transform: translateX(-50%);
}

.resize-handle {
  position: absolute;
  right: 4px;
  bottom: 4px;
  z-index: 11;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background:
    linear-gradient(135deg,
      transparent 0,
      transparent 6px,
      rgb(255 255 255 / 36%) 6px,
      rgb(255 255 255 / 36%) 8px,
      transparent 8px,
      transparent 11px,
      rgb(255 255 255 / 28%) 11px,
      rgb(255 255 255 / 28%) 13px,
      transparent 13px);
  -webkit-app-region: no-drag;
}

.desktop-widget-model-picker {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
  max-width: calc(100% - 70px);
  padding: 4px 8px;
  border: none;
  border-radius: 8px;
  color: #f8fbff;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.2;
  background: rgb(12 18 28 / 48%);
  box-shadow: none;
  backdrop-filter: blur(8px);
  cursor: pointer;
  user-select: text;
}

.desktop-widget-model-picker option {
  color: #0f1722;
  background: #f8fbff;
}

.desktop-widget-stage::after {
  position: absolute;
  right: 52px;
  bottom: 18px;
  left: 52px;
  height: 18px;
  content: "";
  background: radial-gradient(ellipse at center, rgb(12 18 28 / 36%), rgb(12 18 28 / 0) 68%);
  pointer-events: none;
}

.desktop-widget-live2d {
  width: 100%;
  height: 100%;
}

.status-bubble {
  position: absolute;
  top: 54px;
  left: 22px;
  display: inline-flex;
  max-width: calc(100% - 44px);
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgb(255 255 255 / 14%);
  border-radius: 8px;
  color: #f8fbff;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  background: rgb(20 28 40 / 74%);
  box-shadow: none;
  backdrop-filter: blur(10px);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #74d680;
  box-shadow: 0 0 14px rgb(116 214 128 / 70%);
}

.is-disconnected .status-dot {
  background: #ff6b72;
  box-shadow: 0 0 14px rgb(255 107 114 / 72%);
}

.desktop-widget-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 6px 12px 12px;
  border-top: none;
  background: transparent;
  backdrop-filter: none;
}

.session-row,
.quota-row {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  padding: 3px 8px;
  border-radius: 8px;
  background: rgb(12 18 28 / 56%);
  text-shadow: 0 1px 2px rgb(0 0 0 / 60%);
  backdrop-filter: blur(6px);
}

.brand {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 6px;
  color: #0f1722;
  font-size: 11px;
  font-weight: 800;
  background: #d8f3ff;
}

.session-name {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quota-row .brand-label {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: 6px;
  color: #0f1722;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.quota-row .brand-label--claude {
  background: #ffd5b1;
}

.quota-row .brand-label--codex {
  background: #d8f3ff;
}

.quota-row .quota-value {
  min-width: 0;
  overflow: hidden;
  color: #d7e2f0;
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
