import voicesJson from '../../scripts/emilia-voices.json'

export interface EmiliaVoice {
  n: number
  slug: string
  start: number
  text: string
  filename: string
  durationMs: number
}

interface EmiliaVoiceJsonEntry {
  n: number
  slug: string
  start: number
  text: string
}

const FINAL_VOICE_END_SECONDS = 252
const rawVoices = voicesJson as readonly EmiliaVoiceJsonEntry[]

export const EMILIA_VOICES: readonly EmiliaVoice[] = rawVoices.map((voice, index) => {
  const nextStart = rawVoices[index + 1]?.start
  const end = typeof nextStart === 'number' ? nextStart - 0.1 : FINAL_VOICE_END_SECONDS
  const durationSeconds = Math.max(0.5, end - voice.start)
  return {
    ...voice,
    filename: `${String(voice.n).padStart(3, '0')}_${voice.slug}.mp3`,
    durationMs: Math.round(durationSeconds * 1000),
  }
})
