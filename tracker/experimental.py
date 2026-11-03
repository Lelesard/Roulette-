"""Offline candidate tracker. Bright blobs are hypotheses, not validated ball labels."""

from collections import deque
from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class Track:
    seconds: float
    point: tuple | None = None
    angle: float | None = None
    omega: float | None = None
    alpha: float | None = None
    confidence: float = 0.0
    message: str = "Aucune bille validée"


class CandidateTracker:
    """Ellipse from a tight wheel ROI, normalized to a circle; white outer-ring candidates.

    This heuristic cannot identify a ball against all reflections. A score measures
    temporal consistency, never a probability of correct detection.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.points = deque(maxlen=60)
        self.previous = None
        self.last_time = None
        self.shape = None

    def analyze(self, frame, seconds):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (64, 64))
        changed = (
            self.previous is not None
            and np.mean(cv2.absdiff(small, self.previous)) > 38
        )
        discontinuity = (
            self.last_time is not None and not 0 < seconds - self.last_time < 0.35
        )
        resized = self.shape is not None and self.shape != (h, w)
        if changed or discontinuity or resized:
            self.points.clear()
        self.previous, self.last_time, self.shape = small, seconds, (h, w)
        if changed or resized:
            return Track(
                seconds, message="Changement de caméra / zoom : suivi réinitialisé"
            )
        yy, xx = np.mgrid[:h, :w]
        nx, ny = (xx - w / 2) / (w * 0.48), (yy - h / 2) / (h * 0.48)
        radius = np.hypot(nx, ny)
        contrast = cv2.subtract(gray, cv2.GaussianBlur(gray, (0, 0), 3))
        mask = (
            (gray > 205) & (contrast > 22) & (radius > 0.65) & (radius < 1.04)
        ).astype(np.uint8) * 255
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        candidates = []
        for i in range(1, count):
            area = stats[i, cv2.CC_STAT_AREA]
            bw, bh = stats[i, cv2.CC_STAT_WIDTH : cv2.CC_STAT_HEIGHT + 1]
            if 2 <= area <= max(10, h * w * 0.0015) and 0.25 < bw / max(1, bh) < 4:
                x, y = centers[i]
                candidates.append(
                    (
                        float(x),
                        float(y),
                        math.atan2((y - h / 2) / (h * 0.48), (x - w / 2) / (w * 0.48)),
                    )
                )
        if len(candidates) != 1:
            self.points.clear()
            return Track(
                seconds, message="Bille perdue ou reflets ambigus : aucune mesure"
            )
        x, y, angle = candidates[0]
        self.points.append((seconds, angle, x, y))
        if len(self.points) < 8 or self.points[-1][0] - self.points[0][0] < 0.2:
            return Track(
                seconds,
                (x, y),
                angle,
                message="Candidat lumineux : continuité insuffisante",
            )
        times = np.array([p[0] - seconds for p in self.points])
        angles = np.unwrap([p[1] for p in self.points])
        # Sampling aliasing is not resolvable when inter-frame motion approaches pi.
        if np.max(np.abs(np.diff(angles))) > 1.8:
            self.points.clear()
            return Track(
                seconds, message="Mouvement trop rapide / aliasing : mesure rejetée"
            )
        coeff = np.polyfit(times, angles, 2)
        residual = float(np.sqrt(np.mean((np.polyval(coeff, times) - angles) ** 2)))
        confidence = max(0.0, min(1.0, 1 - residual / 0.2)) * min(1.0, len(times) / 20)
        if residual > 0.12:
            self.points.clear()
            return Track(seconds, message="Trajectoire incohérente : candidat rejeté")
        return Track(
            seconds,
            (x, y),
            angle,
            float(coeff[1]),
            float(2 * coeff[0]),
            confidence,
            "Candidat bille expérimental • identité non validée • rotor non mesuré",
        )
