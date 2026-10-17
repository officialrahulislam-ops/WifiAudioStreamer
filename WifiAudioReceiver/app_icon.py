from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def make_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2f6df6"))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    p.setBrush(QColor("white"))
    path = QPainterPath()
    path.moveTo(s * .22, s * .40); path.lineTo(s * .34, s * .40); path.lineTo(s * .48, s * .28)
    path.lineTo(s * .48, s * .72); path.lineTo(s * .34, s * .60); path.lineTo(s * .22, s * .60)
    path.closeSubpath()
    p.drawPath(path)
    pen = QPen(QColor("white"), s * 0.055)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for r in (0.16, 0.27):
        rad = s * r
        p.drawArc(QRectF(s * .50 - rad, s * .50 - rad, 2 * rad, 2 * rad), -40 * 16, 80 * 16)
    p.end()
    return pm


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_pixmap(size))
    return icon
