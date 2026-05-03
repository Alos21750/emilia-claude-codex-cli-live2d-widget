const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopWidget', {
  close: () => ipcRenderer.send('desktop-widget:close'),
  reload: () => ipcRenderer.send('desktop-widget:reload'),
  startDrag: (screenX, screenY) => ipcRenderer.send('desktop-widget:drag-start', screenX, screenY),
  dragMove: (screenX, screenY) => ipcRenderer.send('desktop-widget:drag-move', screenX, screenY),
  endDrag: () => ipcRenderer.send('desktop-widget:drag-end'),
})
