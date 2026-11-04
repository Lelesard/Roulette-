"""Dynamic scene state for changing roulette camera views."""

from dataclasses import dataclass

import cv2
import numpy as np

from .capture import detect_wheel_roi


def intersection_over_union(a, b):
    if a is None or b is None:
        return 0.0
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1, bx1, by1 = ax0 + aw, ay0 + ah, bx0 + bw, by0 + bh
    width = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    height = max(0.0, min(ay1, by1) - max(ay0, by0))
    intersection = width * height
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def blend_roi(previous, current, weight=0.35):
    return tuple(
        float(old * (1 - weight) + new * weight)
        for old, new in zip(previous, current)
    )


@dataclass(frozen=True)
class SceneObservation:
    seconds: float
    camera_changed: bool
    kind: str
    candidate_roi: tuple | None
    wheel_roi: tuple | None
    score: float
    stable_frames: int
    message: str


class SceneObserver:
    """Find a stable wheel region and invalidate it across hard camera cuts."""

    def __init__(self, confirmations=3, hold_seconds=1.5):
        self.confirmations = confirmations
        self.hold_seconds = hold_seconds
        self.reset()

    def reset(self):
        self.previous_gray = None
        self.previous_histogram = None
        self.candidate = None
        self.stable_frames = 0
        self.accepted = None
        self.last_seen = None

    @staticmethod
    def signature(frame):
        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        histogram = cv2.calcHist([gray], [0], None, [32], [0, 256])
        cv2.normalize(histogram, histogram)
        return gray, histogram

    def detect_cut(self, gray, histogram):
        if self.previous_gray is None:
            return False
        difference = float(np.mean(cv2.absdiff(gray, self.previous_gray)))
        similarity = float(
            cv2.compareHist(
                histogram, self.previous_histogram, cv2.HISTCMP_CORREL
            )
        )
        return difference > 34 and similarity < 0.72

    def analyze(self, frame, seconds):
        gray, histogram = self.signature(frame)
        camera_changed = self.detect_cut(gray, histogram)
        self.previous_gray, self.previous_histogram = gray, histogram
        if camera_changed:
            self.candidate = None
            self.stable_frames = 0
            self.accepted = None
            self.last_seen = None

        try:
            candidate, score = detect_wheel_roi(frame)
        except ValueError:
            candidate, score = None, 0.0

        if candidate is not None:
            if self.candidate is not None and intersection_over_union(
                self.candidate, candidate
            ) >= 0.62:
                self.candidate = blend_roi(self.candidate, candidate)
                self.stable_frames += 1
            else:
                self.candidate = candidate
                self.stable_frames = 1
            if self.stable_frames >= self.confirmations:
                self.accepted = self.candidate
                self.last_seen = seconds
            kind = "wheel"
        else:
            self.candidate = None
            self.stable_frames = 0
            kind = "other"
            if (
                self.accepted is not None
                and self.last_seen is not None
                and seconds - self.last_seen > self.hold_seconds
            ):
                self.accepted = None

        if camera_changed:
            message = "Changement de caméra • recherche de la nouvelle vue"
        elif self.accepted is not None and candidate is not None:
            message = (
                f"Roue stable • {self.stable_frames} observations • "
                f"score {score * 100:.0f} %"
            )
        elif candidate is not None:
            message = (
                f"Roue candidate • confirmation {self.stable_frames}/"
                f"{self.confirmations}"
            )
        elif self.accepted is not None:
            message = "Roue momentanément masquée • dernier cadre conservé"
        else:
            message = "Autre vue ou roue non visible • suivi suspendu"
        return SceneObservation(
            float(seconds),
            camera_changed,
            kind,
            candidate,
            self.accepted,
            float(score),
            self.stable_frames,
            message,
        )
