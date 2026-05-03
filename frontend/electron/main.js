import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { applyPlatformWidgetWindowBehavior, buildWidgetWindowOptions } from './platform.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const DEFAULT_WIDGET_URL = 'http://127.0.0.1:5173/'

let widgetWindow = null
let dragState = null
let resizeState = null

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n))
}

function resolveWidgetUrl() {
  return process.env.DESKTOP_WIDGET_URL || process.env.VITE_DEV_SERVER_URL || DEFAULT_WIDGET_URL
}

function createWidgetWindow() {
  const preloadPath = path.join(__dirname, 'preload.cjs')
  widgetWindow = new BrowserWindow(buildWidgetWindowOptions(preloadPath))

  applyPlatformWidgetWindowBehavior(widgetWindow)

  if (process.env.WIDGET_DEVTOOLS === '1' || process.env.WIDGET_DEBUG === '1') {
    widgetWindow.webContents.openDevTools({ mode: 'detach' })
  }
  widgetWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error(`[widget] did-fail-load code=${code} desc=${desc} url=${url}`)
  })
  widgetWindow.webContents.on('console-message', (_e, level, message, line, source) => {
    console.log(`[renderer ${level}] ${message} (${source}:${line})`)
  })

  const url = resolveWidgetUrl()
  console.log(`[widget] loadURL: ${url}`)
  widgetWindow.loadURL(url)
  widgetWindow.on('closed', () => {
    widgetWindow = null
    dragState = null
    resizeState = null
  })
}

app.whenReady().then(() => {
  createWidgetWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWidgetWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

ipcMain.on('desktop-widget:close', () => {
  widgetWindow?.close()
})

ipcMain.on('desktop-widget:reload', () => {
  widgetWindow?.reload()
})

ipcMain.on('desktop-widget:drag-start', (_e, screenX, screenY) => {
  if (!widgetWindow) return
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return
  resizeState = null
  const [winX, winY] = widgetWindow.getPosition()
  dragState = {
    startScreenX: Math.round(screenX),
    startScreenY: Math.round(screenY),
    winX,
    winY,
  }
})

ipcMain.on('desktop-widget:drag-move', (_e, screenX, screenY) => {
  if (!widgetWindow || !dragState || resizeState) return
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return
  const dx = Math.round(screenX) - dragState.startScreenX
  const dy = Math.round(screenY) - dragState.startScreenY
  widgetWindow.setPosition(dragState.winX + dx, dragState.winY + dy)
})

ipcMain.on('desktop-widget:drag-end', () => {
  dragState = null
})

ipcMain.on('desktop-widget:resize-start', (_e, screenX, screenY) => {
  if (!widgetWindow) return
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return
  dragState = null
  const [w, h] = widgetWindow.getSize()
  resizeState = {
    startScreenX: Math.round(screenX),
    startScreenY: Math.round(screenY),
    startW: w,
    startH: h,
  }
})

ipcMain.on('desktop-widget:resize-move', (_e, screenX, screenY) => {
  if (!widgetWindow || !resizeState || dragState) return
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return
  const dx = Math.round(screenX) - resizeState.startScreenX
  const dy = Math.round(screenY) - resizeState.startScreenY
  const w = clamp(resizeState.startW + dx, 220, 1600)
  const h = clamp(resizeState.startH + dy, 300, 2000)
  widgetWindow.setSize(w, h)
})

ipcMain.on('desktop-widget:resize-end', () => {
  resizeState = null
})

ipcMain.on('desktop-widget:set-size', (_e, width, height) => {
  if (!widgetWindow) return
  if (!Number.isFinite(width) || !Number.isFinite(height)) return
  const w = clamp(Math.round(width), 220, 1600)
  const h = clamp(Math.round(height), 300, 2000)
  widgetWindow.setSize(w, h)
})

ipcMain.on('desktop-widget:set-always-on-top', (_e, value) => {
  if (!widgetWindow) return
  widgetWindow.setAlwaysOnTop(!!value)
})
