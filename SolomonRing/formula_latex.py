"""Render a LaTeX/mathtext string - or a curve - to a crisp, theme-coloured QPixmap
via matplotlib.

Used by the formula popup to typeset formulas and to chart a stat/EXP curve. Degrades gracefully: if matplotlib isn't
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


def plot(points, x_label="", y_label="", marker=None, color="#3a7bd5",
         fg="#000000", pt=8, dpr=2.0, width_in=4.6, height_in=2.3):
    """Return a QPixmap line chart of ``points`` (a list of (x, y)), or None if matplotlib
    is missing. ``marker`` is an optional (x, y) point highlighted on the curve - the level
    the popup is currently sampling. ``fg`` colours the axes/labels so the chart follows the
    app's light/dark theme. Not cached: the curve changes with every coefficient edit."""
    if not AVAILABLE or not points:
        return None
    try:
        fig = Figure(figsize=(width_in, height_in), dpi=96 * dpr)
        fig.patch.set_alpha(0.0)
        ax = fig.add_subplot(111)
        ax.patch.set_alpha(0.0)
        ax.plot([p[0] for p in points], [p[1] for p in points], color=color, linewidth=1.6)
        if marker is not None:
            ax.plot([marker[0]], [marker[1]], "o", color=color, markersize=5)
            # Label the sampled point on whichever side has room - at the default level 100 the
            # marker sits on the right edge, where an outward label would be clipped away.
            xs = [q[0] for q in points]
            right_side = marker[0] > (xs[0] + xs[-1]) / 2
            ax.annotate(f"{marker[1]:,}", marker, textcoords="offset points",
                        xytext=(-6, -12) if right_side else (6, -3),
                        ha="right" if right_side else "left", fontsize=pt - 1, color=fg)
        ax.set_xlabel(x_label, fontsize=pt, color=fg)
        ax.set_ylabel(y_label, fontsize=pt, color=fg)
        ax.tick_params(labelsize=pt - 1, colors=fg)
        for spine in ax.spines.values():
            spine.set_color(fg)
        ax.grid(True, linewidth=0.4, alpha=0.3, color=fg)
        fig.tight_layout(pad=0.4)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=96 * dpr, transparent=True)
        buf.seek(0)
        pix = QPixmap()
        if not pix.loadFromData(buf.getvalue(), "PNG"):
            return None
        pix.setDevicePixelRatio(dpr)
        return pix
    except Exception:
        return None
