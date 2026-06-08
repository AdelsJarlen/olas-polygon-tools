"""
Run once to generate plugin icons as PNG files.
Can be run standalone or from QGIS Python console.
"""
import os, sys

# Make Qt available whether run inside QGIS or standalone
try:
    from qgis.PyQt.QtCore import Qt, QSize, QPointF, QRectF
    from qgis.PyQt.QtGui import (
        QImage, QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QPainterPath,
    )
except ImportError:
    from PyQt5.QtCore import Qt, QSize, QPointF, QRectF
    from PyQt5.QtGui import (
        QImage, QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QPainterPath,
    )

ICON_SIZE = 64
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _polygon_points(cx, cy, r, n=6, rotation=-90):
    """Return QPolygonF with n vertices centred at (cx, cy)."""
    import math
    pts = []
    for i in range(n):
        angle = math.radians(rotation + 360 * i / n)
        pts.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return QPolygonF(pts)


def make_icon(letter, fill_color, stroke_color, text_color, filename):
    img = QImage(QSize(ICON_SIZE, ICON_SIZE), QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    poly = _polygon_points(32, 33, 27, n=6)

    # Fill
    p.setBrush(QBrush(fill_color))
    p.setPen(QPen(stroke_color, 3))
    p.drawPolygon(poly)

    # Letter
    font = QFont("Arial", 24, QFont.Bold)
    p.setFont(font)
    p.setPen(QPen(text_color))
    p.drawText(QRectF(0, 0, ICON_SIZE, ICON_SIZE), Qt.AlignCenter, letter)

    p.end()
    path = os.path.join(OUT_DIR, filename)
    img.save(path)
    print(f"  Saved {path}")


def generate():
    print("Generating icons …")
    # Main icon — polygon with "O"
    make_icon(
        "O",
        fill_color=QColor(80, 80, 80, 40),
        stroke_color=QColor(60, 60, 60),
        text_color=QColor(50, 50, 50),
        filename="icon.png",
    )
    # W — extend — green
    make_icon(
        "W",
        fill_color=QColor(76, 175, 80, 60),
        stroke_color=QColor(46, 125, 50),
        text_color=QColor(27, 94, 32),
        filename="icon_extend.png",
    )
    # A — move — blue
    make_icon(
        "A",
        fill_color=QColor(66, 165, 245, 60),
        stroke_color=QColor(21, 101, 192),
        text_color=QColor(13, 71, 161),
        filename="icon_move.png",
    )
    # D — delete — red
    make_icon(
        "D",
        fill_color=QColor(239, 83, 80, 60),
        stroke_color=QColor(198, 40, 40),
        text_color=QColor(183, 28, 28),
        filename="icon_delete.png",
    )
    print("Done.")


if __name__ == "__main__":
    # Needs a QApplication for QPainter
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
    except Exception:
        pass
    generate()
