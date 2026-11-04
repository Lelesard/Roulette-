"""Experimental multi-hypothesis ball candidate tracker.

The selected point is never treated as a validated ball label. Real roulette
reflections and rotor details can still create coherent false tracks.
"""

from collections import deque
from dataclasses import dataclass, replace
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
    rotor_omega: float | None = None
    rotor_confidence: float = 0.0
    rotor_message: str = "Rotor non mesuré"


@dataclass(frozen=True)
class RotorTrack:
    seconds: float
    omega: float | None = None
    confidence: float = 0.0
    message: str = "Rotor non mesuré"


def direction_label(omega):
    if omega is None or abs(omega) < 0.01:
        return "non mesuré"
    return "horaire à l’écran" if omega > 0 else "antihoraire à l’écran"


def validate_ball_direction(ball, rotor):
    """Publish a ball direction only when its speed is independent of the rotor."""
    if ball.omega is None:
        return ball
    candidate_direction = direction_label(ball.omega)
    if rotor.omega is None:
        return replace(
            ball,
            omega=None,
            alpha=None,
            message=(
                f"Candidat {candidate_direction} en attente d’une direction rotor "
                "indépendante"
            ),
        )
    minimum_independent_speed = max(0.7, 5 * abs(rotor.omega))
    if abs(ball.omega) < minimum_independent_speed:
        return replace(
            ball,
            point=None,
            omega=None,
            alpha=None,
            message=(
                f"Candidat rejeté : vitesse {abs(ball.omega):.2f} rad/s trop proche "
                f"du rotor ({abs(rotor.omega):.2f} rad/s) • reflet rotor probable"
            ),
        )
    ratio = abs(ball.omega) / max(abs(rotor.omega), 0.01)
    relation = (
        "même sens"
        if math.copysign(1, ball.omega) == math.copysign(1, rotor.omega)
        else "sens opposé"
    )
    return replace(
        ball,
        message=(
            f"{ball.message} • mouvement indépendant du rotor confirmé "
            f"(vitesse ×{ratio:.1f}, {relation})"
        ),
    )


class RotorTracker:
    """Estimate rotor angular shift from a polar-unwrapped inner wheel band."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.previous = None
        self.last_time = None
        self.speeds = deque(maxlen=18)

    @staticmethod
    def polar_band(frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        h, w = gray.shape
        radius = min(h, w) * 0.48
        polar = cv2.warpPolar(
            gray,
            (96, 720),
            (w / 2, h / 2),
            radius,
            cv2.WARP_POLAR_LINEAR,
        )
        # Ignore the hub and the outer ball track. Pocket/number features live in
        # the middle radial band and move with the rotor.
        band = polar[:, 30:78].astype(np.float32)
        band -= cv2.GaussianBlur(band, (0, 0), 3)
        band *= np.hanning(band.shape[0]).astype(np.float32)[:, None]
        return band

    def analyze(self, frame, seconds):
        band = self.polar_band(frame)
        if self.previous is None or self.last_time is None:
            self.previous, self.last_time = band, seconds
            return RotorTrack(seconds, message="Rotor : initialisation")
        dt = seconds - self.last_time
        if not 0 < dt < 0.35 or self.previous.shape != band.shape:
            self.reset()
            self.previous, self.last_time = band, seconds
            return RotorTrack(seconds, message="Rotor : suivi réinitialisé")
        (radial_shift, angular_shift), response = cv2.phaseCorrelate(
            self.previous, band
        )
        self.previous, self.last_time = band, seconds
        omega = angular_shift / band.shape[0] * 2 * math.pi / dt
        while self.speeds and seconds - self.speeds[0][0] > 0.9:
            self.speeds.popleft()
        if response < 0.025:
            return RotorTrack(
                seconds,
                message=(
                    "Rotor : détails insuffisants ou image ambiguë • "
                    f"corrélation {max(0.0, response):.2f}"
                ),
            )
        if abs(radial_shift) > 18:
            return RotorTrack(
                seconds,
                message=(
                    f"Rotor : déplacement radial {radial_shift:.1f} px, mesure rejetée • "
                    f"corrélation {response:.2f}"
                ),
            )
        if abs(omega) < 0.08:
            return RotorTrack(
                seconds,
                message=(
                    "Rotor immobile ou mouvement trop faible • "
                    f"corrélation {response:.2f}"
                ),
            )
        if abs(omega) > 28:
            return RotorTrack(
                seconds,
                message=(
                    f"Rotor : saut angulaire trop rapide ({omega:.1f} rad/s) • "
                    f"corrélation {response:.2f}"
                ),
            )
        self.speeds.append((seconds, float(omega), float(response)))
        if len(self.speeds) < 5:
            return RotorTrack(
                seconds,
                message=f"Rotor : continuité {len(self.speeds)}/5",
            )
        speeds = np.array([sample[1] for sample in self.speeds])
        responses = np.array([sample[2] for sample in self.speeds])
        median = float(np.median(speeds))
        direction_agreement = float(np.mean(np.sign(speeds) == np.sign(median)))
        spread = float(np.median(np.abs(speeds - median)))
        confidence = (
            min(1.0, max(0.0, float(np.median(responses))) / 0.20)
            * direction_agreement
            * max(0.0, min(1.0, 1 - spread / max(abs(median), 0.2)))
        )
        if direction_agreement < 0.8 or confidence < 0.25:
            return RotorTrack(
                seconds,
                message="Rotor : direction instable, mesure rejetée",
            )
        return RotorTrack(
            seconds,
            median,
            confidence,
            (
                f"Rotor {direction_label(median)} • {len(self.speeds)} mesures récentes • "
                f"corrélation médiane {float(np.median(responses)):.2f}"
            ),
        )


class Hypothesis:
    def __init__(self, point):
        self.points = deque([point], maxlen=45)
        self.misses = 0

    def predict(self, seconds):
        last = self.points[-1]
        if len(self.points) < 2:
            return last[1]
        previous = self.points[-2]
        dt = last[0] - previous[0]
        omega = (last[1] - previous[1]) / dt if dt > 0 else 0.0
        return last[1] + omega * max(0.0, seconds - last[0])

    def add(self, seconds, candidate):
        x, y, raw_angle, radius, quality = candidate
        predicted = self.predict(seconds)
        angle = raw_angle + round((predicted - raw_angle) / (2 * math.pi)) * 2 * math.pi
        self.points.append((seconds, angle, x, y, radius, quality))
        self.misses = 0


class CandidateTracker:
    """Track moving bright hypotheses in the normalized outer wheel ring."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.points = deque(maxlen=45)
        self.hypotheses = []
        self.previous_small = None
        self.previous_gray = None
        self.last_time = None
        self.shape = None

    @staticmethod
    def angular_distance(a, b):
        return abs((a - b + math.pi) % (2 * math.pi) - math.pi)

    def candidates(self, gray):
        h, w = gray.shape
        yy, xx = np.mgrid[:h, :w]
        nx, ny = (xx - w / 2) / (w * 0.48), (yy - h / 2) / (h * 0.48)
        radius = np.hypot(nx, ny)
        contrast = cv2.subtract(gray, cv2.GaussianBlur(gray, (0, 0), 3))
        motion = (
            cv2.absdiff(gray, self.previous_gray)
            if self.previous_gray is not None and self.previous_gray.shape == gray.shape
            else np.zeros_like(gray)
        )
        mask = (
            (gray > 190)
            & (contrast > 12)
            & (radius > 0.56)
            & (radius < 1.08)
        ).astype(np.uint8) * 255
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        result = []
        for index in range(1, count):
            area = stats[index, cv2.CC_STAT_AREA]
            bw, bh = stats[index, cv2.CC_STAT_WIDTH : cv2.CC_STAT_HEIGHT + 1]
            if not (
                3 <= area <= max(18, h * w * 0.002)
                and 0.28 < bw / max(1, bh) < 3.6
            ):
                continue
            x, y = map(float, centers[index])
            component = labels == index
            brightness = float(np.mean(gray[component])) / 255
            movement = float(np.mean(motion[component])) / 255
            local_contrast = float(np.mean(contrast[component])) / 255
            radial = float(radius[round(y), round(x)])
            quality = (
                0.42 * brightness
                + 0.34 * min(1.0, movement * 3)
                + 0.18 * min(1.0, local_contrast * 4)
                + 0.06 * max(0.0, 1 - abs(radial - 0.84) / 0.28)
            )
            result.append(
                (
                    x,
                    y,
                    math.atan2(
                        (y - h / 2) / (h * 0.48),
                        (x - w / 2) / (w * 0.48),
                    ),
                    radial,
                    quality,
                )
            )
        return result

    def update_hypotheses(self, candidates, seconds):
        unused = set(range(len(candidates)))
        for hypothesis in sorted(
            self.hypotheses, key=lambda item: len(item.points), reverse=True
        ):
            if seconds - hypothesis.points[-1][0] > 0.22:
                hypothesis.misses = 4
                continue
            predicted = hypothesis.predict(seconds)
            previous_radius = hypothesis.points[-1][4]
            choices = []
            for index in unused:
                candidate = candidates[index]
                angle_cost = self.angular_distance(candidate[2], predicted)
                radius_cost = abs(candidate[3] - previous_radius)
                if angle_cost <= 1.25 and radius_cost <= 0.24:
                    choices.append(
                        (angle_cost + radius_cost * 1.8 - candidate[4] * 0.12, index)
                    )
            if choices:
                _, index = min(choices)
                hypothesis.add(seconds, candidates[index])
                unused.remove(index)
            else:
                hypothesis.misses += 1
        self.hypotheses = [item for item in self.hypotheses if item.misses <= 3]
        for index in unused:
            x, y, angle, radius, quality = candidates[index]
            self.hypotheses.append(
                Hypothesis((seconds, angle, x, y, radius, quality))
            )
        self.hypotheses = sorted(
            self.hypotheses,
            key=lambda item: (len(item.points), -item.misses, item.points[-1][5]),
            reverse=True,
        )[:24]

    @staticmethod
    def fit(hypothesis, seconds):
        points = list(hypothesis.points)[-30:]
        if len(points) < 7 or points[-1][0] - points[0][0] < 0.18:
            return None
        times = np.array([point[0] - seconds for point in points])
        angles = np.array([point[1] for point in points])
        if np.max(np.abs(np.diff(angles))) > 1.8:
            return None
        coeff = np.polyfit(times, angles, 2)
        residual = float(
            np.sqrt(np.mean((np.polyval(coeff, times) - angles) ** 2))
        )
        omega = float(coeff[1])
        alpha = float(2 * coeff[0])
        if residual > 0.22 or not 0.35 <= abs(omega) <= 40:
            return None
        quality = float(np.mean([point[5] for point in points]))
        confidence = (
            max(0.0, min(1.0, 1 - residual / 0.22))
            * min(1.0, len(points) / 20)
            * min(1.0, abs(omega) / 3)
            * min(1.0, quality / 0.72)
        )
        return confidence, omega, alpha, residual

    def analyze(self, frame, seconds):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (64, 64))
        changed = (
            self.previous_small is not None
            and np.mean(cv2.absdiff(small, self.previous_small)) > 38
        )
        discontinuity = (
            self.last_time is not None and not 0 < seconds - self.last_time < 0.35
        )
        resized = self.shape is not None and self.shape != (h, w)
        if changed or discontinuity or resized:
            self.points.clear()
            self.hypotheses.clear()
        if changed or resized:
            self.previous_small = small
            self.previous_gray = gray
            self.last_time = seconds
            self.shape = (h, w)
            return Track(
                seconds, message="Changement de caméra / zoom : suivi réinitialisé"
            )

        candidates = self.candidates(gray)
        self.update_hypotheses(candidates, seconds)
        self.previous_small = small
        self.previous_gray = gray
        self.last_time = seconds
        self.shape = (h, w)

        fitted = []
        for hypothesis in self.hypotheses:
            if hypothesis.misses:
                continue
            result = self.fit(hypothesis, seconds)
            if result is not None:
                fitted.append((result[0], hypothesis, result))
        if not fitted:
            self.points.clear()
            growing = max(
                (item for item in self.hypotheses if item.misses == 0),
                key=lambda item: len(item.points),
                default=None,
            )
            if growing is None or not candidates:
                return Track(
                    seconds, message="Bille perdue ou reflets ambigus : aucune mesure"
                )
            point = growing.points[-1]
            return Track(
                seconds,
                (point[2], point[3]),
                point[1],
                message=(
                    f"Candidats lumineux : continuité {len(growing.points)}/7 • "
                    "identité non validée"
                ),
            )

        confidence, selected, result = max(fitted, key=lambda item: item[0])
        self.points = deque(selected.points, maxlen=45)
        point = selected.points[-1]
        _, omega, alpha, residual = result
        return Track(
            seconds,
            (point[2], point[3]),
            point[1],
            omega,
            alpha,
            confidence,
            (
                "Trajectoire lumineuse cohérente • candidat bille non validé • "
                f"résidu {residual:.3f} rad"
            ),
        )
