import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { applyPlatformWidgetWindowBehavior, buildWidgetWindowOptions } from './platform.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const DEFAULT_WIDGET_URL = 'http://127.0.0.1:5173/'

let widgetWindow = null
let dragState = null

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
  const [winX, winY] = widgetWindow.getPosition()
  dragState = {
    startScreenX: Math.round(screenX),
    startScreenY: Math.round(screenY),
    winX,
    winY,
  }
})

ipcMain.on('desktop-widget:drag-move', (_e, screenX, screenY) => {
  if (!widgetWindow || !dragState) return
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return
  const dx = Math.round(screenX) - dragState.startScreenX
  const dy = Math.round(screenY) - dragState.startScreenY
  widgetWindow.setPosition(dragState.winX + dx, dragState.winY + dy)
})

ipcMain.on('desktop-widget:drag-end', () => {
  dragState = null
})
