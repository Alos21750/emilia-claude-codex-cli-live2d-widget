<template>
  <main class="desktop-widget-shell" :class="{ 'is-settings-open': settingsOpen }">
    <div class="desktop-widget-controls">
      <button type="button" title="設定" :class="{ 'is-active': settingsOpen }" @click.stop="toggleSettings">⚙</button>
      <button type="button" title="重新載入" @click="reloadWindow">↻</button>
      <button type="button" title="關閉" @click="closeWindow">×</button>
    </div>

    <div v-if="settingsOpen" class="settings-panel no-drag" @click.stop>
      <label class="settings-row">
        <span>Zoom <em>{{ characterScale.toFixed(1) }}×</em></span>
        <input v-model.number="characterScale" type="range" min="0.5" max="2.0" step="0.1" />
      </label>
      <label class="settings-row">
        <span>Resolution <em>{{ resolutionMultiplier.toFixed(1) }}×</em></span>
        <input v-model.number="resolutionMultiplier" type="range" min="1.0" max="4.0" step="0.5" />
      </label>
      <label class="settings-row">
        <span>FPS <em>{{ maxFps }}</em></span>
        <select v-model.number="maxFps">
          <option :value="15">15</option>
          <option :value="30">30</option>
          <option :value="60">60</option>
          <option :value="120">120</option>
        </select>
      </label>
      <label class="settings-row">
        <span>Always on top</span>
        <input v-model="alwaysOnTop" type="checkbox" />
      </label>
      <label class="settings-row">
        <span>Hair physics</span>
        <input v-model="hairPhysicsEnabled" type="checkbox" />
      </label>
      <label class="settings-row">
        <span>Voice on tap</span>
        <input v-model="voiceOnTap" type="checkbox" />
      </label>
      <label class="settings-row">
        <span>Subtitle</span>
        <input v-model="subtitleEnabled" type="checkbox" />
      </label>
      <label class="settings-row">
        <span>Volume <em>{{ voiceVolume }}%</em></span>
        <input v-model.number="voiceVolume" type="range" min="0" max="100" step="5" />
      </label>
    </div>

    <section class="desktop-widget-stage" :class="statusClass">
      <div class="drag-handle" aria-hidden="true"></div>
      <div
        class="resize-handle no-drag"
        aria-hidden="true"
        @pointerdown.stop.prevent="onResizeDown"
        @pointermove.stop.prevent="onResizeMove"
        @pointerup.stop.prevent="onResizeUp"
        @pointercancel.stop.prevent="onResizeCancel"
      ></div>
      <select v-model="selectedModelKey" class="desktop-widget-model-picker no-drag" aria-label="Live2D character">
        <option v-for="item in EMILIA_MODELS" :key="item.key" :value="item.key">
          {{ item.displayName }}
        </option>
      </select>

      <DesktopWidgetLive2D
        :state="monitor.activeState.value"
        :modelKey="selectedModelKey"
        :characterScale="characterScale"
        :resolutionMultiplier="resolutionMultiplier"
        :maxFps="maxFps"
        :hairPhysicsEnabled="hairPhysicsEnabled"
        :voiceOnTap="voiceOnTap"
        :voiceVolume="voiceVolume / 100"
        @voice-played="onVoicePlayed"
        @voice-ended="onVoiceEnded"
      />
      <div v-if="voiceSubtitleVisible && activeVoice" class="voice-subtitle no-drag">
        {{ activeVoice.text }}
      </div>
      <div class="bubbles-layer no-drag" aria-hidden="false">
        <div class="quota-bubble">
          <div class="bubble-line">
            <span class="bubble-label bubble-label--claude">Claude</span>
            <span class="bubble-value">{{ claudeQuota }}</span>
          </div>
          <div class="bubble-line">
            <span class="bubble-label bubble-label--codex">Codex</span>
            <span class="bubble-value">{{ codexQuota }}</span>
          </div>
        </div>
      </div>
    </section>

  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import DesktopWidgetLive2D from '../components/DesktopWidgetLive2D.vue'
import { getSessionActivityEpoch } from '../utils/sessionStageState'
import { isDesktopWidgetWarmupSession, useDesktopWidgetMonitor } from '../composables/desktopWidgetMonitor'
import type { DesktopWidgetSession } from '../composables/desktopWidgetMonitor'
import { DEFAULT_EMILIA_KEY, EMILIA_MODELS, isValidEmiliaKey } from '../composables/emiliaModels'
import type { EmiliaVoice } from '../composables/emiliaVoices'

const monitor = useDesktopWidgetMonitor()
const selectedModelKey = ref<string>(loadInitialModelKey())
const resizeStart = ref<{ screenX: number; screenY: number; pointerId: number } | null>(null)
const WIDGET_SIZE_STORAGE_KEY = 'desktopWidget.size'
const CHARACTER_SCALE_STORAGE_KEY = 'desktopWidget.characterScale'
const RESOLUTION_STORAGE_KEY = 'desktopWidget.resolution'
const MAX_FPS_STORAGE_KEY = 'desktopWidget.maxFps'
const ALWAYS_ON_TOP_STORAGE_KEY = 'desktopWidget.alwaysOnTop'
const HAIR_PHYSICS_STORAGE_KEY = 'desktopWidget.hairPhysics'
const VOICE_ON_TAP_STORAGE_KEY = 'desktopWidget.voiceOnTap'
const SUBTITLE_STORAGE_KEY = 'desktopWidget.subtitle'
const VOICE_VOLUME_STORAGE_KEY = 'desktopWidget.voiceVolume'
const settingsOpen = ref(false)
const characterScale = ref(loadInitialNumberSetting(CHARACTER_SCALE_STORAGE_KEY, 1.0, 0.5, 2.0))
const resolutionMultiplier = ref(loadInitialNumberSetting(
  RESOLUTION_STORAGE_KEY,
  window.devicePixelRatio || 1,
  1.0,
  4.0,
))
const maxFps = ref(loadInitialMaxFps())
const alwaysOnTop = ref(loadInitialBooleanSetting(ALWAYS_ON_TOP_STORAGE_KEY, true))
const hairPhysicsEnabled = ref(loadInitialBooleanSetting(HAIR_PHYSICS_STORAGE_KEY, true))
const voiceOnTap = ref(loadInitialBooleanSetting(VOICE_ON_TAP_STORAGE_KEY, true))
const subtitleEnabled = ref(loadInitialBooleanSetting(SUBTITLE_STORAGE_KEY, true))
const voiceVolume = ref(loadInitialNumberSetting(VOICE_VOLUME_STORAGE_KEY, 80, 0, 100))
const activeVoice = ref<EmiliaVoice | null>(null)
const voiceSubtitleVisible = ref(false)
let voiceSubtitleTimer: number | null = null

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

function loadInitialNumberSetting(key: string, fallback: number, min: number, max: number): number {
  const boundedFallback = Math.max(min, Math.min(max, fallback))
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return boundedFallback
    const value = Number(raw)
    if (!Number.isFinite(value) || value < min || value > max) return boundedFallback
    return value
  } catch {
    return boundedFallback
  }
}

function loadInitialMaxFps(): number {
  const value = loadInitialNumberSetting(MAX_FPS_STORAGE_KEY, 60, 15, 120)
  return value === 15 || value === 30 || value === 60 || value === 120 ? value : 60
}

function loadInitialBooleanSetting(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key)
    if (raw === 'true') return true
    if (raw === 'false') return false
    return fallback
  } catch {
    return fallback
  }
}

function persistNumberSetting(key: string, value: number): void {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // ignore unavailable storage
  }
}

function persistBooleanSetting(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? 'true' : 'false')
  } catch {
    // ignore unavailable storage
  }
}

watch(selectedModelKey, (key) => {
  try {
    localStorage.setItem('desktopWidget.modelKey', key)
  } catch {
    // ignore unavailable storage
  }
})

watch(characterScale, (value) => {
  persistNumberSetting(CHARACTER_SCALE_STORAGE_KEY, value)
})

watch(resolutionMultiplier, (value) => {
  persistNumberSetting(RESOLUTION_STORAGE_KEY, value)
})

watch(maxFps, (value) => {
  persistNumberSetting(MAX_FPS_STORAGE_KEY, value)
})

watch(alwaysOnTop, (value) => {
  persistBooleanSetting(ALWAYS_ON_TOP_STORAGE_KEY, value)
  window.desktopWidget?.setAlwaysOnTop?.(value)
})

watch(hairPhysicsEnabled, (value) => {
  persistBooleanSetting(HAIR_PHYSICS_STORAGE_KEY, value)
})

watch(voiceOnTap, (value) => {
  persistBooleanSetting(VOICE_ON_TAP_STORAGE_KEY, value)
})

watch(subtitleEnabled, (value) => {
  persistBooleanSetting(SUBTITLE_STORAGE_KEY, value)
  if (!value) {
    hideVoiceSubtitle()
  }
})

watch(voiceVolume, (value) => {
  persistNumberSetting(VOICE_VOLUME_STORAGE_KEY, value)
})

onMounted(() => {
  restoreWidgetSize()
  window.desktopWidget?.setAlwaysOnTop?.(alwaysOnTop.value)
  document.addEventListener('click', closeSettingsFromOutside)
})

onUnmounted(() => {
  clearVoiceSubtitleTimer()
  document.removeEventListener('click', closeSettingsFromOutside)
})

function closeWindow(): void {
  window.desktopWidget?.close()
}

function reloadWindow(): void {
  window.desktopWidget?.reload()
}

function toggleSettings(): void {
  settingsOpen.value = !settingsOpen.value
}

function closeSettingsFromOutside(): void {
  settingsOpen.value = false
}

function clearVoiceSubtitleTimer(): void {
  if (voiceSubtitleTimer !== null) {
    window.clearTimeout(voiceSubtitleTimer)
    voiceSubtitleTimer = null
  }
}

function hideVoiceSubtitle(): void {
  clearVoiceSubtitleTimer()
  voiceSubtitleVisible.value = false
  activeVoice.value = null
}

function onVoicePlayed(voice: EmiliaVoice): void {
  clearVoiceSubtitleTimer()
  activeVoice.value = voice
  voiceSubtitleVisible.value = subtitleEnabled.value
  if (!subtitleEnabled.value) return
  voiceSubtitleTimer = window.setTimeout(() => {
    if (activeVoice.value?.n === voice.n) {
      hideVoiceSubtitle()
    }
  }, voice.durationMs + 500)
}

function onVoiceEnded(voice: EmiliaVoice): void {
  if (activeVoice.value?.n !== voice.n) return
  hideVoiceSubtitle()
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
  grid-template-rows: minmax(0, 1fr);
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

.desktop-widget-shell:hover .desktop-widget-controls,
.desktop-widget-shell.is-settings-open .desktop-widget-controls {
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

.desktop-widget-controls button.is-active {
  border-color: rgb(216 243 255 / 48%);
  background: rgb(18 34 52 / 86%);
}

.settings-panel {
  position: absolute;
  top: 50px;
  right: 12px;
  z-index: 30;
  display: grid;
  gap: 8px;
  width: 200px;
  padding: 10px 12px;
  border: 1px solid rgb(255 255 255 / 14%);
  border-radius: 8px;
  color: #f8fbff;
  font-size: 11px;
  background: rgb(12 18 28 / 88%);
  backdrop-filter: blur(10px);
  user-select: text;
}

.settings-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-row span {
  display: flex;
  justify-content: space-between;
  font-weight: 700;
}

.settings-row em {
  color: #d8f3ff;
  font-style: normal;
  font-weight: 600;
}

.settings-row input[type="range"] {
  width: 100%;
}

.settings-row input[type="checkbox"] {
  align-self: flex-start;
}

.settings-row select {
  padding: 3px 6px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 6px;
  color: #f8fbff;
  background: rgb(12 18 28 / 60%);
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

.voice-subtitle {
  position: absolute;
  top: 30%;
  left: 34%;
  z-index: 12;
  max-width: 58%;
  padding: 10px 14px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 14px;
  color: #fff;
  font-size: 15px;
  font-weight: 800;
  line-height: 1.4;
  background: rgb(12 18 28 / 84%);
  backdrop-filter: blur(10px);
  pointer-events: none;
  text-shadow: 0 1px 2px rgb(0 0 0 / 70%);
  transform: translate(-10%, -50%);
}

.bubbles-layer {
  position: absolute;
  inset: 0;
  z-index: 8;
  pointer-events: none;
}

.quota-bubble {
  position: absolute;
  top: 70px;
  left: 14px;
  display: grid;
  gap: 4px;
  max-width: min(36%, 160px);
  padding: 8px 12px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 12px;
  border-bottom-left-radius: 4px;
  color: #f8fbff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
  background: rgb(12 18 28 / 78%);
  backdrop-filter: blur(10px);
  pointer-events: auto;
  user-select: text;
  text-shadow: 0 1px 2px rgb(0 0 0 / 60%);
}

.quota-bubble::after {
  position: absolute;
  bottom: -8px;
  width: 0;
  height: 0;
  content: "";
  border: 8px solid transparent;
  border-top: 8px solid rgb(12 18 28 / 78%);
  border-bottom: 0;
  right: 18px;
  border-right: 0;
}

.bubble-line {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
}

.bubble-label {
  flex: 0 0 auto;
  padding: 2px 6px;
  border-radius: 5px;
  color: #0f1722;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.bubble-label--claude {
  background: #ffd5b1;
}

.bubble-label--codex {
  background: #d8f3ff;
}

.bubble-value {
  min-width: 0;
  overflow: hidden;
  color: #d7e2f0;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
