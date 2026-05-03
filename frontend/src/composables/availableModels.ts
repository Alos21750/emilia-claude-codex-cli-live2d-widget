import { getCurrentInstance, onMounted, ref } from 'vue'
import type { Ref } from 'vue'
import { getDefaultServerUrl } from '../utils/serverUrl'

export interface Live2DModel {
  key: string
  modelPath: string
  displayName: string
}

export const DEFAULT_FALLBACK_KEY = 'hiyori'

const MODELS_PATH = '/api/widget/models'
const availableModels = ref<Live2DModel[]>([])
const modelsLoading = ref(false)
let hasFetched = false
let fetchPromise: Promise<void> | null = null

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function resolveModelsUrl(): string {
  const base = trimTrailingSlash(getDefaultServerUrl())
  return `${base}${MODELS_PATH}`
}

function isLive2DModel(value: unknown): value is Live2DModel {
  const item = value as Live2DModel
  return typeof item?.key === 'string'
    && typeof item.modelPath === 'string'
    && typeof item.displayName === 'string'
}

export function isValidModelKey(key: string, models: Live2DModel[]): boolean {
  return models.some((model) => model.key === key)
}

async function fetchAvailableModels(): Promise<void> {
  modelsLoading.value = true
  try {
    const response = await fetch(resolveModelsUrl(), { method: 'GET' })
    if (!response.ok) {
      availableModels.value = []
      return
    }
    const data = await response.json()
    availableModels.value = Array.isArray(data) ? data.filter(isLive2DModel) : []
    hasFetched = true
  } catch {
    availableModels.value = []
  } finally {
    modelsLoading.value = false
    fetchPromise = null
  }
}

function ensureLoaded(): Promise<void> {
  if (hasFetched) return Promise.resolve()
  if (!fetchPromise) {
    fetchPromise = fetchAvailableModels()
  }
  return fetchPromise
}

export function useAvailableModels(): {
  availableModels: Ref<Live2DModel[]>
  modelsLoading: Ref<boolean>
  refresh: () => Promise<void>
} {
  if (getCurrentInstance()) {
    onMounted(() => {
      void ensureLoaded()
    })
  }

  return {
    availableModels,
    modelsLoading,
    refresh: fetchAvailableModels,
  }
}
