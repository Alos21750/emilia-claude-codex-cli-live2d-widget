export interface EmiliaModel {
  key: string
  displayName: string
}

export const EMILIA_MODELS: readonly EmiliaModel[] = [
  { key: 'ac_base_emilia01', displayName: 'Emilia (default)' },
  { key: 'ac_base_emilia02', displayName: 'Emilia 02' },
  { key: 'ac_base_emilia_dress01', displayName: 'Emilia (Dress)' },
  { key: 'ac_base_emilia_hood01', displayName: 'Emilia (Hood)' },
  { key: 'ac_base_emilia_mizugi01', displayName: 'Emilia (Swimsuit)' },
  { key: 'ac_base_emilia_nemaki01', displayName: 'Emilia (Sleepwear 1)' },
  { key: 'ac_base_emilia_nemaki02', displayName: 'Emilia (Sleepwear 2)' },
  { key: 'ac_base_emilia_nemaki03', displayName: 'Emilia (Sleepwear 3)' },
  { key: 'ac_base_emilia_wedding01', displayName: 'Emilia (Wedding)' },
  { key: 'ac_base_emilia_xmas01', displayName: 'Emilia (Christmas)' },
] as const

export const DEFAULT_EMILIA_KEY = 'ac_base_emilia01'

export function isValidEmiliaKey(key: string): boolean {
  return EMILIA_MODELS.some((m) => m.key === key)
}
