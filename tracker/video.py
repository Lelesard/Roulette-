import cv2
import time
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage
from .vision import NoDetector


class VideoWorker(QObject):
    raw_frame = Signal(object, float)
    frame = Signal(QImage, float, str)
    opened = Signal(float, float)
    error = Signal(str)
    ended = Signal()

    def __init__(self):
        super().__init__()
        self.cap = None
        self.analyzer = NoDetector()
        self.fps = 30.0

    @Slot(str)
    def open(self, path):
        self.close()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self.error.emit("Vidéo illisible.")
            cap.release()
            return
        self.cap = cap
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.analyzer.reset()
        self.opened.emit(cap.get(cv2.CAP_PROP_FRAME_COUNT) / self.fps, self.fps)
        self.read()

    @Slot()
    def read(self):
        if self.cap is None:
            return
        started = time.perf_counter()
        ok, frame = self.cap.read()
        if not ok:
            self.ended.emit()
            return
        seconds = max(0, self.cap.get(cv2.CAP_PROP_POS_FRAMES) - 1) / self.fps
        observation = self.analyzer.analyze(frame, seconds)
        self.raw_frame.emit(frame.copy(), seconds)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        self.frame.emit(
            QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy(),
            seconds,
            observation.diagnostic
            + f" • décodage/analyse {(time.perf_counter() - started) * 1000:.1f} ms",
        )

    @Slot(float)
    def seek(self, seconds):
        if self.cap is not None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, round(seconds * self.fps)))
            self.analyzer.reset()
            self.read()

    @Slot()
    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
