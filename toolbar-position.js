// Shared wire curve and toolbar positioning logic
// Used by index.html and test-toolbar.html

/** Compute cubic Bezier control points and handle position for a wire.
 *  All positions in screen-space pixels (wrapper-relative).
 *  @param {number} x1 - Start connector X
 *  @param {number} y1 - Start connector Y
 *  @param {number} x2 - End connector X
 *  @param {number} y2 - End connector Y
 *  @param {number} curve - Canvas-space curve value (w.curve or 0)
 *  @param {number} viewportScale - Current viewport scale (vp.scale)
 *  @returns {object} { dx, dy, len, nx, ny, offset, cx1, cy1, cx2, cy2, mpx, mpy, handleX, handleY }
 */
function computeWireCurve(x1, y1, x2, y2, curve, viewportScale) {
  var dx = x2 - x1;
  var dy = y2 - y1;
  var len = Math.hypot(dx, dy) || 1;
  var nx = -dy / len;
  var ny = dx / len;
  var offset = (curve || 0) * viewportScale;

  // Control points: one near each connector, at 1/3 of the way along
  var cx1 = x1 + dx / 3 + nx * offset;
  var cy1 = y1 + dy / 3 + ny * offset;
  var cx2 = x2 - dx / 3 + nx * offset;
  var cy2 = y2 - dy / 3 + ny * offset;

  // Midpoint at t=0.5 of cubic Bezier
  var mpx = (x1 + 3 * cx1 + 3 * cx2 + x2) / 8;
  var mpy = (y1 + 3 * cy1 + 3 * cy2 + y2) / 8;

  // Curve handle position = curve midpoint (t=0.5)
  var handleX = mpx + 0.75 * offset * nx;
  var handleY = mpy + 0.75 * offset * ny;

  return {
    dx: dx, dy: dy, len: len,
    nx: nx, ny: ny,
    offset: offset,
    cx1: cx1, cy1: cy1,
    cx2: cx2, cy2: cy2,
    mpx: mpx, mpy: mpy,
    handleX: handleX, handleY: handleY
  };
}

/** Compute toolbar position relative to a wire's curve.
 *  @param {number} x1 - Start connector X (screen-space)
 *  @param {number} y1 - Start connector Y
 *  @param {number} x2 - End connector X
 *  @param {number} y2 - End connector Y
 *  @param {number} curve - Canvas-space curve value
 *  @param {number} viewportScale - Current zoom scale
 *  @param {number} [offsetPx=12] - Pixels to offset from handle
 *  @returns {object} { left, top, transform, handleX, handleY, offDirX, offDirY, isHorizontal }
 */
function computeToolbarPosition(x1, y1, x2, y2, curve, viewportScale, offsetPx) {
  if (offsetPx === undefined) offsetPx = 12;
  var c = computeWireCurve(x1, y1, x2, y2, curve, viewportScale);
  var curveVal = curve || 0;

  // Offset direction: convex side for curved wires, perpendicular upward for straight
  var offDirX, offDirY;
  if (curveVal === 0) {
    // Straight line — offset perpendicular upward
    if (c.ny < 0) { offDirX = c.nx; offDirY = c.ny; }
    else { offDirX = -c.nx; offDirY = -c.ny; }
  } else {
    var sign = curveVal > 0 ? 1 : -1;
    offDirX = sign * c.nx;
    offDirY = sign * c.ny;
  }

  var isHorizontal = Math.abs(c.dx) >= Math.abs(c.dy);
  var transform = isHorizontal ? 'translateX(-50%)' : 'translateY(-50%)';
  var left = c.handleX + offDirX * offsetPx;
  var top = c.handleY + offDirY * offsetPx;

  return {
    left: left,
    top: top,
    transform: transform,
    handleX: c.handleX,
    handleY: c.handleY,
    offDirX: offDirX,
    offDirY: offDirY,
    isHorizontal: isHorizontal,
    // Also return raw curve data for callers that need it
    _curve: c
  };
}
