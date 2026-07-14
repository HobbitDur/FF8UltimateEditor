"""Render a LaTeX/mathtext string to a crisp, theme-coloured QPixmap via matplotlib.

Used by the formula popup to typeset formulas. Degrades gracefully: if matplotlib isn't
installed, ``AVAILABLE`` is False and callers fall back to the plain-text formula.
Rendered pixmaps are cached by (latex, colour, pt, dpr) so repeated recomputes are cheap.
"""
from io import BytesIO

from PyQt6.QtGui import QPixmap

try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401 (ensures Agg present)
    AVAILABLE = True
except Exception:                       # pragma: no cover - matplotlib optional
    AVAILABLE = False

_CACHE = {}


def render(latex: str, color: str = "#000000", pt: int = 13, dpr: float = 2.0):
    """Return a QPixmap of ``$latex$`` in ``color`` at ``pt`` points, or None if it can't
    be rendered (matplotlib missing or a mathtext parse error). ``dpr`` is the device-pixel
    ratio the pixmap is tagged with, for crisp HiDPI display."""
    if not AVAILABLE or not latex:
        return None
    key = (latex, color, pt, round(dpr, 2))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        dpi = 96 * dpr
        fig = Figure()
        fig.patch.set_alpha(0.0)
        fig.text(0.0, 0.0, f"${latex}$", fontsize=pt, color=color)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.04)
        buf.seek(0)
        pix = QPixmap()
        if not pix.loadFromData(buf.getvalue(), "PNG"):
            return None
        pix.setDevicePixelRatio(dpr)
        _CACHE[key] = pix
        return pix
    except Exception:
        return None
