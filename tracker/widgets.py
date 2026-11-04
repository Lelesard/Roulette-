import math
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget, QPushButton
from .domain import WHEEL


class FrameView(QWidget):
    selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 240)
        self.image = None
        self.regions = {}
        self.mode = None
        self.start = None
        self.end = None
        self.point = None

    def set_image(self, image):
        self.image = image
        self.update()

    def image_rect(self):
        if self.image is None:
            return QRectF()
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            (self.width() - size.width()) / 2,
            (self.height() - size.height()) / 2,
            size.width(),
            size.height(),
        )

    def normalize(self, pos):
        r = self.image_rect()
        if r.isEmpty():
            return None
        return QPointF(
            max(0, min(1, (pos.x() - r.x()) / r.width())),
            max(0, min(1, (pos.y() - r.y()) / r.height())),
        )

    def mousePressEvent(self, event):
        if (
            self.mode
            and event.button() == Qt.MouseButton.LeftButton
            and self.image_rect().contains(event.position())
        ):
            self.start = self.normalize(event.position())
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = self.normalize(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None or self.end is None:
            return
        self.end = self.normalize(event.position())
        roi = (
            min(self.start.x(), self.end.x()),
            min(self.start.y(), self.end.y()),
            abs(self.start.x() - self.end.x()),
            abs(self.start.y() - self.end.y()),
        )
        self.start = None
        self.end = None
        if roi[2] > 0.015 and roi[3] > 0.015:
            self.selected.emit((self.mode, roi))
            self.mode = None
            self.unsetCursor()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b1019"))
        r = self.image_rect()
        if self.image is None:
            p.setPen(QColor("#bac8db"))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Aucune image • ouvrez une vidéo ou démarrez la capture Brave",
            )
            return
        p.drawImage(r, self.image)
        regions = dict(self.regions)
        if self.start is not None and self.end is not None:
            regions["sélection"] = (
                min(self.start.x(), self.end.x()),
                min(self.start.y(), self.end.y()),
                abs(self.start.x() - self.end.x()),
                abs(self.start.y() - self.end.y()),
            )
        for name, (x, y, w, h) in regions.items():
            color = (
                "#78f06b"
                if name == "wheel_dynamic"
                else "#f9bf66"
                if name == "wheel_candidate"
                else "#52d9ec"
                if name == "wheel_roi"
                else "#f9bf66"
            )
            p.setPen(
                QPen(
                    QColor(color),
                    3 if name in ("wheel_candidate", "wheel_dynamic") else 2,
                )
            )
            box = QRectF(
                r.x() + x * r.width(),
                r.y() + y * r.height(),
                w * r.width(),
                h * r.height(),
            )
            p.drawRect(box)
            p.drawText(
                box.topLeft() + QPointF(4, 17),
                {
                    "wheel_roi": "Cylindre",
                    "wheel_candidate": "Cylindre proposé",
                    "wheel_dynamic": "Roue suivie",
                    "results_roi": "Résultats",
                }.get(name, name),
            )
        if self.point:
            p.setPen(QPen(QColor("#f7df57"), 3))
            x, y = self.point
            p.drawEllipse(QPointF(r.x() + x * r.width(), r.y() + y * r.height()), 6, 6)
        if self.mode:
            p.setPen(QColor("#ffffff"))
            p.drawText(12, 22, "Glissez pour définir la région : " + self.mode)


class Racetrack(QWidget):
    def __init__(self, on_select):
        super().__init__()
        self.setMinimumSize(850, 320)
        self.buttons = {}
        for n in WHEEL:
            button = QPushButton(str(n), self)
            button.clicked.connect(lambda checked=False, n=n: on_select(n))
            self.buttons[n] = button

    def resizeEvent(self, event):
        width, height = self.width(), self.height()
        # Equal arc lengths keep adjacent touch targets apart at the narrow ends.
        samples = []
        distances = [0.0]
        for j in range(1481):
            angle = 2 * math.pi * j / 1480 - math.pi / 2
            samples.append(
                (
                    width / 2 + (width / 2 - 37) * math.cos(angle),
                    height / 2 + (height / 2 - 28) * math.sin(angle),
                )
            )
            if j:
                distances.append(distances[-1] + math.dist(samples[-2], samples[-1]))
        cursor = 0
        for i, n in enumerate(WHEEL):
            target = distances[-1] * i / 37
            while cursor < len(distances) - 1 and distances[cursor] < target:
                cursor += 1
            x, y = samples[cursor]
            self.buttons[n].setGeometry(round(x - 25), round(y - 21), 50, 42)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(QColor("#b4c1d8"))
        p.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "CYLINDRE EUROPÉEN\nSélection manuelle des voisins",
        )


class BalanceChart(QWidget):
    def __init__(self):
        super().__init__()
        self.values = [0]
        self.setMinimumHeight(150)

    def set_values(self, values):
        self.values = values or [0]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#1e2838"))
        low, high = min(self.values), max(self.values)
        if low == high:
            high = low + 100
        p.setPen(QColor("#c9d2e6"))
        p.drawText(
            10,
            20,
            f"Évolution de la bankroll • min {low / 100:.2f} € • max {max(self.values) / 100:.2f} €",
        )
        points = [
            QPointF(
                12 + i * (self.width() - 24) / max(1, len(self.values) - 1),
                self.height() - 12 - (v - low) * (self.height() - 48) / (high - low),
            )
            for i, v in enumerate(self.values)
        ]
        p.setPen(QPen(QColor("#60dfba"), 2))
        for a, b in zip(points, points[1:]):
            p.drawLine(a, b)
