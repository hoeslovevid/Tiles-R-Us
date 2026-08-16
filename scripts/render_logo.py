"""Render the Tiles R Us wordmark (Toys R Us–style lockup, original artwork)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
RED = QColor("#E31837")
BLUE = QColor("#0057A8")
WHITE = QColor("#FFFFFF")


def _font(px: int) -> QFont:
    font = QFont("Arial Black")
    if font.family() != "Arial Black":
        font = QFont("Segoe UI")
        font.setWeight(QFont.Weight.Black)
    font.setPixelSize(px)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def _text_size(font: QFont, text: str) -> tuple[int, int]:
    metrics = QFontMetrics(font)
    return metrics.horizontalAdvance(text), metrics.ascent()


def _draw_flipped_r(painter: QPainter, font: QFont, x: float, baseline: float, color: QColor) -> float:
    metrics = QFontMetrics(font)
    width = metrics.horizontalAdvance("R")
    painter.save()
    painter.setFont(font)
    painter.setPen(color)
    painter.translate(x + width, 0)
    painter.scale(-1, 1)
    painter.drawText(0, int(baseline), "R")
    painter.restore()
    return width


def paint_wordmark(painter: QPainter, cx: float, baseline: float, px: int) -> tuple[float, float, float, float]:
    font = _font(px)
    r_font = _font(int(px * 1.22))
    tiles_w, _ = _text_size(font, "tiles")
    us_w, _ = _text_size(font, "us")
    r_w = QFontMetrics(r_font).horizontalAdvance("R")
    gap = px * 0.08
    total = tiles_w + gap + r_w + gap + us_w
    x = cx - total / 2
    painter.setFont(font)
    painter.setPen(RED)
    painter.drawText(int(x), int(baseline), "tiles")
    x += tiles_w + gap
    _draw_flipped_r(painter, r_font, x, baseline, RED)
    x += r_w + gap
    painter.setFont(font)
    painter.setPen(BLUE)
    painter.drawText(int(x), int(baseline), "us")
    top = baseline - QFontMetrics(r_font).ascent()
    bottom = baseline + QFontMetrics(font).descent()
    return cx - total / 2, top, total, bottom - top


def paint_stacked(painter: QPainter, cx: float, cy: float, px: int) -> None:
    tiles_font = _font(px)
    r_font = _font(int(px * 1.55))
    us_font = _font(px)
    tiles_w, tiles_a = _text_size(tiles_font, "tiles")
    r_w = QFontMetrics(r_font).horizontalAdvance("R")
    us_w, us_a = _text_size(us_font, "us")
    gap = px * 0.12
    r_a = QFontMetrics(r_font).ascent()
    total_h = tiles_a + gap + r_a + gap + us_a
    y = cy - total_h / 2 + tiles_a
    painter.setFont(tiles_font)
    painter.setPen(RED)
    painter.drawText(int(cx - tiles_w / 2), int(y), "tiles")
    y += gap + r_a
    _draw_flipped_r(painter, r_font, cx - r_w / 2, y, RED)
    y += gap + us_a
    painter.setFont(us_font)
    painter.setPen(BLUE)
    painter.drawText(int(cx - us_w / 2), int(y), "us")


def render_icon(path: Path, size: int = 1024) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    margin = size * 0.07
    radius = size * 0.18
    rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)
    path_bg = QPainterPath()
    path_bg.addRoundedRect(rect, radius, radius)
    painter.fillPath(path_bg, WHITE)
    paint_stacked(painter, size / 2, size / 2, int(size * 0.145))
    painter.end()
    image.save(str(path))


def render_wordmark(path: Path, width: int = 1600, height: int = 420) -> None:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    paint_wordmark(painter, width / 2, height * 0.68, int(height * 0.42))
    painter.end()
    image.save(str(path))


def render_ico(png_path: Path, ico_path: Path) -> None:
    from PIL import Image

    src = Image.open(png_path).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    src.save(ico_path, format="ICO", sizes=sizes)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    icon_png = OUT / "logo-icon.png"
    wordmark = OUT / "logo-wordmark.png"
    ico = OUT / "app.ico"
    render_icon(icon_png)
    render_wordmark(wordmark)
    try:
        render_ico(icon_png, ico)
    except ImportError:
        print("Pillow missing; wrote PNGs only. pip install pillow")
        return 1
    print(f"wrote {icon_png}")
    print(f"wrote {wordmark}")
    print(f"wrote {ico}")
    _ = app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
