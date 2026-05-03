<template>
  <canvas
    ref="canvasRef"
    class="desktop-widget-live2d"
    @pointerdown="handleCanvasPointerDown"
    @pointermove="handleCanvasPointerMove"
    @pointerup="handleCanvasPointerUp"
    @pointercancel="handleCanvasPointerCancel"
  ></canvas>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as PIXI from 'pixi.js'
import { Live2DModel as Live2DModelCubism4 } from 'pixi-live2d-display/cubism4'
import { Live2DModel as Live2DModelCubism2 } from 'pixi-live2d-display/cubism2'
import { EMILIA_VOICES, type EmiliaVoice } from '../composables/emiliaVoices'
import type { SessionState } from '../types/sessionState'

const props = withDefaults(defineProps<{
  state: SessionState
  modelPath?: string
  characterScale?: number
  resolutionMultiplier?: number
  maxFps?: number
  hairPhysicsEnabled?: boolean
  voiceOnTap?: boolean
  voiceVolume?: number
}>(), {
  modelPath: '',
  characterScale: 1.0,
  resolutionMultiplier: 1.0,
  maxFps: 60,
  hairPhysicsEnabled: true,
  voiceOnTap: true,
  voiceVolume: 0.8,
})
const emit = defineEmits<{
  (event: 'voice-played', voice: EmiliaVoice): void
  (event: 'voice-ended', voice: EmiliaVoice): void
}>()

interface MotionEntry {
  group: string
  index: number
  key: string
}

const STATE_MOTION_CANDIDATES: Record<SessionState, string[]> = {
  IDLE: ['idle', 'main_1', 'home'],
  THINKING: ['main_2', 'main_1', 'touch_head', 'taphead', 'tap', 'idle'],
  TOOLING: ['mission', 'touch_body', 'touch_special', 'effect', 'tap', 'idle'],
  RESPONDING: ['main_3', 'main_2', 'main_1', 'home', 'taphead', 'idle'],
  WAITING: ['mail', 'home', 'login', 'idle'],
}
const MIN_MODEL_SCALE = 0.06
const HORIZONTAL_BIAS = 0.65
const IDLE_MOTION_INTERVAL_MS = 10_000
const IDLE_MOTION_JITTER_MS = 2_500
const DRAG_THRESHOLD_PX = 5
const CLICK_MAX_DURATION_MS = 350

const canvasRef = ref<HTMLCanvasElement | null>(null)
let app: PIXI.Application | null = null
let model: any | null = null
let disposed = false
let lastMotionKey = ''
let layoutWarmupTicks = 0
let idleMotionTimer: number | null = null
let nextIdleMotionAt = 0
let loadToken = 0
let pointerStart: { screenX: number; screenY: number; ts: number; pointerId: number } | null = null
let dragging = false
let cachedPhysicsForCurrentModel: any = null
let voiceAudio: HTMLAudioElement | null = null
let currentVoice: EmiliaVoice | null = null

Live2DModelCubism4.registerTicker(PIXI.Ticker)
Live2DModelCubism2.registerTicker(PIXI.Ticker)

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

function collectMotions(currentModel: any): MotionEntry[] {
  const settings = currentModel?.internalModel?.settings
  const rawMotions = settings?.motions || settings?.json?.FileReferences?.Motions || {}
  const entries: MotionEntry[] = []
  for (const [group, motions] of Object.entries(rawMotions)) {
    if (!Array.isArray(motions)) continue
    motions.forEach((motion: any, index) => {
      const file = String(motion?.File || motion?.file || '')
      const name = file.split('/').pop()?.replace(/\.motion3?\.json$/i, '') || group
      entries.push({
        group,
        index,
        key: `${normalize(group)}:${normalize(name)}:${index}`,
      })
    })
  }
  return entries
}

function pickMotion(currentModel: any, state: SessionState): MotionEntry | null {
  const motions = collectMotions(currentModel)
  if (motions.length === 0) return null
  const candidates = STATE_MOTION_CANDIDATES[state]
  for (const candidate of candidates) {
    const target = normalize(candidate)
    const exact = motions.find((motion) => {
      const [group, name] = motion.key.split(':')
      return group === target || name === target
    })
    if (exact) return exact
    const fuzzy = motions.find((motion) => motion.key.includes(target))
    if (fuzzy) return fuzzy
  }
  return motions[0]
}

function pickRandomMotion(currentModel: any): MotionEntry | null {
  const motions = collectMotions(currentModel)
  if (motions.length === 0) return null
  const candidates = motions.filter((motion) => motion.key !== lastMotionKey)
  const pool = candidates.length > 0 ? candidates : motions
  const index = Math.floor(Math.random() * pool.length)
  return pool[index] || null
}

function clampNumber(value: number | undefined, fallback: number, min: number, max: number): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.max(min, Math.min(max, numeric))
}

function normalizedCharacterScale(): number {
  return clampNumber(props.characterScale, 1.0, 0.5, 2.0)
}

function normalizedResolution(): number {
  const value = clampNumber(props.resolutionMultiplier, 1.0, 1.0, 4.0)
  if (value < 1.5) return 1
  if (value <= 2.5) return 2
  if (value < 3.5) return 3
  return 4
}

function normalizedMaxFps(): number {
  const fps = Number(props.maxFps)
  return fps === 15 || fps === 30 || fps === 60 || fps === 120 ? fps : 60
}

function normalizedVoiceVolume(): number {
  return clampNumber(props.voiceVolume, 0.8, 0, 1)
}

function snapToRenderPixel(value: number): number {
  const resolution = normalizedResolution()
  return Math.round(value * resolution) / resolution
}

function layoutModel(): void {
  if (!app || !model) return
  const width = app.renderer.screen.width
  const height = app.renderer.screen.height
  const bounds = model.getLocalBounds()
  const naturalWidth = Math.max(1, bounds.width)
  const naturalHeight = Math.max(1, bounds.height)
  const horizontalPadding = 26
  const topPadding = 26
  const bottomPadding = 8
  const availableWidth = Math.max(1, width - horizontalPadding * 2)
  const availableHeight = Math.max(1, height - topPadding - bottomPadding)
  const scale = Math.max(MIN_MODEL_SCALE, Math.min(
    availableWidth / naturalWidth,
    availableHeight / naturalHeight,
  ) * normalizedCharacterScale())
  const scaledWidth = naturalWidth * scale
  const scaledHeight = naturalHeight * scale
  const targetLeft = (width - scaledWidth) * HORIZONTAL_BIAS
  const targetTop = topPadding + Math.max(0, availableHeight - scaledHeight) * 0.42

  model.scale.set(scale)
  model.x = snapToRenderPixel(targetLeft - bounds.x * scale)
  model.y = snapToRenderPixel(targetTop - bounds.y * scale)
}

function resizeRenderer(): void {
  if (!app || !canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  app.renderer.resize(Math.max(1, Math.floor(rect.width)), Math.max(1, Math.floor(rect.height)))
  layoutModel()
}

function applyHairPhysics(enabled: boolean): void {
  if (!model?.internalModel) return
  if (cachedPhysicsForCurrentModel === null && model.internalModel.physics) {
    cachedPhysicsForCurrentModel = model.internalModel.physics
  }
  model.internalModel.physics = enabled && cachedPhysicsForCurrentModel
    ? cachedPhysicsForCurrentModel
    : null
}

function handleVoiceEnded(): void {
  if (!currentVoice) return
  const endedVoice = currentVoice
  currentVoice = null
  emit('voice-ended', endedVoice)
}

function getVoiceAudio(): HTMLAudioElement {
  if (!voiceAudio) {
    voiceAudio = new Audio()
    voiceAudio.preload = 'auto'
    voiceAudio.addEventListener('ended', handleVoiceEnded)
  }
  return voiceAudio
}

function pickRandomVoice(): EmiliaVoice | null {
  if (EMILIA_VOICES.length === 0) return null
  return EMILIA_VOICES[Math.floor(Math.random() * EMILIA_VOICES.length)] || null
}

async function playRandomVoice(): Promise<void> {
  const voice = pickRandomVoice()
  if (!voice) return
  emit('voice-played', voice)
  currentVoice = voice
  const audio = getVoiceAudio()
  audio.pause()
  audio.currentTime = 0
  audio.volume = normalizedVoiceVolume()
  audio.src = `/assets/voices/${voice.filename}`
  try {
    await audio.play()
  } catch {
    // Missing local voice clips still allow subtitles to show.
  }
}

async function playStateMotion(state: SessionState): Promise<void> {
  if (!model) return
  const motion = pickMotion(model, state)
  if (!motion || motion.key === lastMotionKey) return
  lastMotionKey = motion.key
  try {
    if (typeof model.motion === 'function') {
      const played = await model.motion(motion.group, motion.index)
      if (played) return
    }
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      return
    }
  } catch (error) {
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      return
    }
    console.warn('Failed to play desktop widget Live2D motion', error)
  } finally {
    scheduleNextIdleMotion()
  }
}

async function handleCanvasClick(): Promise<void> {
  if (!model) return
  if (props.voiceOnTap) {
    void playRandomVoice()
  }
  const motion = pickRandomMotion(model)
  if (!motion) return
  lastMotionKey = motion.key
  try {
    if (typeof model.motion === 'function') {
      const played = await model.motion(motion.group, motion.index)
      if (played) return
    }
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      return
    }
  } catch (error) {
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      return
    }
    console.warn('Failed to play click motion', error)
  } finally {
    scheduleNextIdleMotion()
  }
}

function handleCanvasPointerDown(e: PointerEvent): void {
  pointerStart = {
    screenX: Math.round(e.screenX),
    screenY: Math.round(e.screenY),
    ts: Date.now(),
    pointerId: e.pointerId,
  }
  dragging = false
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
}

function handleCanvasPointerMove(e: PointerEvent): void {
  if (!pointerStart || e.buttons === 0) return
  const ex = Math.round(e.screenX)
  const ey = Math.round(e.screenY)
  const dx = ex - pointerStart.screenX
  const dy = ey - pointerStart.screenY
  if (!dragging && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
    dragging = true
    window.desktopWidget?.startDrag?.(pointerStart.screenX, pointerStart.screenY)
  }
  if (dragging) {
    window.desktopWidget?.dragMove?.(ex, ey)
  }
}

function finishPointer(target: HTMLElement | null, pointerId: number | undefined): void {
  if (target && pointerId != null) {
    try {
      target.releasePointerCapture?.(pointerId)
    } catch {
      // ignore stale pointer capture
    }
  }
  pointerStart = null
  dragging = false
}

function handleCanvasPointerUp(e: PointerEvent): void {
  if (!pointerStart) return
  const ex = Math.round(e.screenX)
  const ey = Math.round(e.screenY)
  const moved = Math.hypot(ex - pointerStart.screenX, ey - pointerStart.screenY)
  const duration = Date.now() - pointerStart.ts
  if (dragging) {
    window.desktopWidget?.endDrag?.()
  } else if (moved <= DRAG_THRESHOLD_PX && duration <= CLICK_MAX_DURATION_MS) {
    void handleCanvasClick()
  }
  finishPointer(e.currentTarget as HTMLElement, e.pointerId)
}

function handleCanvasPointerCancel(e: PointerEvent): void {
  if (dragging) {
    window.desktopWidget?.endDrag?.()
  }
  finishPointer(e.currentTarget as HTMLElement, e.pointerId)
}

function scheduleNextIdleMotion(nowMs = Date.now()): void {
  const randomJitter = Math.floor(Math.random() * IDLE_MOTION_JITTER_MS)
  nextIdleMotionAt = nowMs + IDLE_MOTION_INTERVAL_MS + randomJitter
}

async function maybePlayIdleMotion(): Promise<void> {
  if (!model || disposed) return
  const now = Date.now()
  if (now < nextIdleMotionAt) return
  const motion = pickRandomMotion(model) || pickMotion(model, props.state)
  if (!motion) {
    scheduleNextIdleMotion(now)
    return
  }
  try {
    if (typeof model.motion === 'function') {
      const played = await model.motion(motion.group, motion.index)
      if (played) {
        lastMotionKey = motion.key
        return
      }
    }
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      lastMotionKey = motion.key
      return
    }
  } catch (error) {
    const manager = model.internalModel?.motionManager
    if (manager && typeof manager.startMotion === 'function') {
      manager.startMotion(motion.group, motion.index)
      lastMotionKey = motion.key
      return
    }
    console.warn('Failed to play desktop widget idle motion', error)
  } finally {
    scheduleNextIdleMotion()
  }
}

async function loadModel(path: string): Promise<void> {
  if (!app || !path) return
  const token = ++loadToken
  const ModelClass = path.endsWith('.model3.json') ? Live2DModelCubism4 : Live2DModelCubism2
  let loaded: any
  try {
    loaded = await ModelClass.from(path)
  } catch (error) {
    if (!disposed && token === loadToken) {
      console.warn('Failed to load Live2D model', path, error)
    }
    return
  }
  if (disposed || !app || token !== loadToken) {
    try {
      loaded.destroy()
    } catch {
      // ignore stale model cleanup errors
    }
    return
  }
  if (model) {
    try {
      app.stage.removeChild(model)
    } catch {
      // ignore stale stage cleanup errors
    }
    try {
      model.destroy()
    } catch {
      // ignore stale model cleanup errors
    }
    model = null
  }
  model = loaded
  cachedPhysicsForCurrentModel = null
  model.zIndex = 1
  app.stage.addChild(model)
  applyHairPhysics(props.hairPhysicsEnabled)
  layoutWarmupTicks = 12
  layoutModel()
  lastMotionKey = ''
  scheduleNextIdleMotion()
  void playStateMotion(props.state)
}

onMounted(() => {
  if (!canvasRef.value) return
  PIXI.settings.ROUND_PIXELS = true
  PIXI.settings.RESOLUTION = normalizedResolution()
  app = new PIXI.Application({
    view: canvasRef.value,
    transparent: true,
    autoStart: true,
    sharedTicker: true,
    width: 360,
    height: 440,
    backgroundAlpha: 0,
    resolution: normalizedResolution(),
    autoDensity: true,
    antialias: false,
  })
  app.stage.sortableChildren = true
  app.ticker.maxFPS = normalizedMaxFps()
  app.ticker.add(() => {
    if (layoutWarmupTicks <= 0) return
    layoutWarmupTicks -= 1
    layoutModel()
  })
  window.addEventListener('resize', resizeRenderer)
  resizeRenderer()
  idleMotionTimer = window.setInterval(() => {
    void maybePlayIdleMotion()
  }, 1000)
  void loadModel(props.modelPath)
})

onUnmounted(() => {
  disposed = true
  window.removeEventListener('resize', resizeRenderer)
  if (idleMotionTimer !== null) {
    window.clearInterval(idleMotionTimer)
    idleMotionTimer = null
  }
  if (model) {
    model.destroy()
    model = null
  }
  if (app) {
    app.destroy(true)
    app = null
  }
  if (voiceAudio) {
    voiceAudio.pause()
    voiceAudio.removeEventListener('ended', handleVoiceEnded)
    voiceAudio = null
  }
  currentVoice = null
})

watch(
  () => props.state,
  (state) => {
    void playStateMotion(state)
  },
)

watch(
  () => props.modelPath,
  () => {
    void loadModel(props.modelPath)
  },
)

watch(
  () => props.characterScale,
  () => {
    layoutModel()
  },
)

watch(
  () => props.resolutionMultiplier,
  () => {
    if (!app) return
    const resolution = normalizedResolution()
    PIXI.settings.RESOLUTION = resolution
    app.renderer.resolution = resolution
    resizeRenderer()
  },
)

watch(
  () => props.maxFps,
  () => {
    if (!app) return
    app.ticker.maxFPS = normalizedMaxFps()
  },
)

watch(
  () => props.hairPhysicsEnabled,
  (enabled) => {
    applyHairPhysics(enabled)
  },
)

watch(
  () => props.voiceVolume,
  () => {
    if (voiceAudio) {
      voiceAudio.volume = normalizedVoiceVolume()
    }
  },
)
</script>

<style scoped>
.desktop-widget-live2d {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  height: 100%;
  backface-visibility: hidden;
  transform: translateZ(0);
  will-change: transform;
  -webkit-app-region: no-drag;
  cursor: pointer;
}
</style>
