"""Lucide (ISC) SVG icons rendered to theme-colored, HiDPI-correct pixmaps."""
from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer


def icon_dir() -> Path:
    bundled = getattr(sys, '_MEIPASS', '')
    if bundled:
        return Path(bundled) / 'assets' / 'icons'
    return Path(__file__).resolve().parents[1] / 'assets' / 'icons'


_source: dict[str, str] = {}
_cache: dict[tuple, QPixmap] = {}
MISSING = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
           ' stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/></svg>')


def ratio() -> float:
    screen = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
    return max(1.0, min(3.0, screen.devicePixelRatio() if screen else 1.0))


def source(name: str) -> str:
    if name not in _source:
        path = icon_dir() / f'{name}.svg'
        try:
            _source[name] = path.read_text(encoding='utf-8')
        except OSError:
            _source[name] = MISSING
    return _source[name]


def _svg(name: str, color: str, fill: bool, weight: float) -> bytes:
    text = source(name).replace('currentColor', color)
    if fill:
        text = text.replace('fill="none"', f'fill="{color}"', 1)
    if weight != 2.0:
        text = text.replace('stroke-width="2"', f'stroke-width="{weight}"')
    return text.encode('utf-8')


def pixmap(name: str, color: str, size: int = 18, fill: bool = False,
           weight: float = 2.0, angle: float = 0.0) -> QPixmap:
    dpr = ratio()
    key = (name, color, size, fill, weight, round(angle, 1), dpr)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    edge = max(1, int(round(size * dpr)))
    out = QPixmap(edge, edge)
    out.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_svg(name, color, fill, weight)))
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if angle:
        painter.translate(edge / 2, edge / 2)
        painter.rotate(angle)
        painter.translate(-edge / 2, -edge / 2)
    renderer.render(painter, QRectF(0, 0, edge, edge))
    painter.end()
    out.setDevicePixelRatio(dpr)
    if len(_cache) > 600:
        _cache.clear()
    _cache[key] = out
    return out


def icon(name: str, color: str, size: int = 18, fill: bool = False, weight: float = 2.0) -> QIcon:
    return QIcon(pixmap(name, color, size, fill, weight))


def clear_cache():
    _cache.clear()


def rounded(source_pixmap: QPixmap, radius: float) -> QPixmap:
    """Clip a pixmap to rounded corners without losing its device pixel ratio."""
    if source_pixmap.isNull():
        return source_pixmap
    dpr = source_pixmap.devicePixelRatio() or 1.0
    out = QPixmap(source_pixmap.size())
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, source_pixmap.width() / dpr, source_pixmap.height() / dpr), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(QPointF(0, 0), source_pixmap)
    painter.end()
    return out


def available() -> list[str]:
    return sorted(p.stem for p in icon_dir().glob('*.svg'))
