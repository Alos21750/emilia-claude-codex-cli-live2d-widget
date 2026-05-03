function isMac() {
  return process.platform === 'darwin'
}

function isWindows() {
  return process.platform === 'win32'
}

function readSize(envKey, fallback, min, max) {
  const raw = parseInt(process.env[envKey] || '', 10)
  if (Number.isFinite(raw) && raw >= min && raw <= max) return raw
  return fallback
}

export function buildWidgetWindowOptions(preloadPath) {
  const width = readSize('WIDGET_WIDTH', 280, 220, 1200)
  const height = readSize('WIDGET_HEIGHT', 400, 300, 1600)
  const shared = {
    width,
    height,
    minWidth: 220,
    minHeight: 300,
    frame: false,
    resizable: true,
    alwaysOnTop: true,
    title: 'Agents Desktop Widget',
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  }

  if (isWindows()) {
    return {
      ...shared,
      transparent: true,
      hasShadow: false,
      backgroundColor: '#00000000',
      resizable: false,
    }
  }

  return {
    ...shared,
    transparent: true,
    hasShadow: false,
    backgroundColor: '#00000000',
  }
}

export function applyPlatformWidgetWindowBehavior(window) {
  window.setMenuBarVisibility(false)

  if (isMac()) {
    window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    window.setAlwaysOnTop(true, 'floating')
    window.setFullScreenable(false)
    return
  }

  if (isWindows()) {
    window.setAlwaysOnTop(true, 'pop-up-menu')
  }
}
