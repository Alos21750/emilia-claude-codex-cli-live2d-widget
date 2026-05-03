const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopWidget', {
  close: () => ipcRenderer.send('desktop-widget:close'),
  reload: () => ipcRenderer.send('desktop-widget:reload'),
  startDrag: (screenX, screenY) => ipcRenderer.send('desktop-widget:drag-start', screenX, screenY),
  dragMove: (screenX, screenY) => ipcRenderer.send('desktop-widget:drag-move', screenX, screenY),
  endDrag: () => ipcRenderer.send('desktop-widget:drag-end'),
  startResize: (screenX, screenY) => ipcRenderer.send('desktop-widget:resize-start', screenX, screenY),
  resizeMove: (screenX, screenY) => ipcRenderer.send('desktop-widget:resize-move', screenX, screenY),
  endResize: () => ipcRenderer.send('desktop-widget:resize-end'),
  applySize: (width, height) => ipcRenderer.send('desktop-widget:set-size', width, height),
})
