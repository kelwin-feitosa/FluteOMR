"use strict";

// Coordenadas da imagem permanecem invariantes; o zoom afeta só a vista.
const FluteGeometry = {
  boxStyle(box, zoom) {
    if (!(zoom > 0)) throw new RangeError("zoom inválido");
    return {
      left: box.left * zoom,
      top: box.top * zoom,
      width: (box.right - box.left + 1) * zoom,
      height: (box.bottom - box.top + 1) * zoom,
    };
  },
  screenToImage(clientX, clientY, stageLeft, stageTop, zoom, width, height) {
    if (!(zoom > 0)) throw new RangeError("zoom inválido");
    return {
      x: Math.max(0, Math.min(width - 1, Math.round((clientX - stageLeft) / zoom))),
      y: Math.max(0, Math.min(height - 1, Math.round((clientY - stageTop) / zoom))),
    };
  },
};

if (typeof module !== "undefined" && module.exports) module.exports = FluteGeometry;
