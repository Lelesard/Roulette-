"""Offline physical model and strict, chronological, independently supplied evaluation."""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .domain import WHEEL, sector, number


@dataclass(frozen=True)
class PhysicalState:
    seconds: float
    last_frame_seconds: float
    ball_angle: float
    ball_omega: float
    ball_alpha: float
    rotor_angle: float
    rotor_omega: float
    release_speed: float
    fall_seconds: float
    rebound_offset: float
    uncertainty_radians: float
    confidence: float
    calibrated: bool = False


def estimate(state, closes_at, size=19):
    """Constant angular deceleration until calibrated release, then flight and rebound.

    All angles are radians, clockwise in the rectified camera frame. rotor_angle
    is the measured angle of pocket zero. The user must calibrate camera handedness,
    release speed, flight delay and bounce dispersion on development data.
    """
    fields = [v for k, v in vars(state).items() if k != "calibrated"] + [closes_at]
    if size not in (9, 15, 19):
        raise ValueError("Taille de secteur invalide.")
    if not all(math.isfinite(v) for v in fields):
        return None
    if (
        not state.calibrated
        or state.confidence < 0.9
        or not 0 <= state.last_frame_seconds <= state.seconds < closes_at
    ):
        return None
    if (
        state.seconds - state.last_frame_seconds > 0.1
        or state.fall_seconds < 0
        or state.uncertainty_radians <= 0
        or state.uncertainty_radians > size * math.pi / 37
    ):
        return None
    if (
        state.release_speed <= 0
        or abs(state.ball_omega) <= state.release_speed
        or state.ball_omega * state.ball_alpha >= 0
    ):
        return None
    target = math.copysign(state.release_speed, state.ball_omega)
    delay = (target - state.ball_omega) / state.ball_alpha
    if not 0 < delay < 15:
        return None
    ball = (
        state.ball_angle
        + state.ball_omega * delay
        + 0.5 * state.ball_alpha * delay**2
        + target * state.fall_seconds
        + state.rebound_offset
    )
    rotor = state.rotor_angle + state.rotor_omega * (delay + state.fall_seconds)
    index = round(((ball - rotor) % (2 * math.pi)) * 37 / (2 * math.pi)) % 37
    center = WHEEL[index]
    return {
        "created_seconds": state.seconds,
        "last_frame_seconds": state.last_frame_seconds,
        "closes_at": closes_at,
        "center": center,
        "size": size,
        "numbers": list(sector(center, size)),
        "confidence": state.confidence,
        "experimental": True,
    }


def evaluate(rows):
    seen = set()
    accepted = []
    rejected = []
    for row in rows:
        try:
            key = (row["video"], row["spin_id"])
            if key in seen:
                raise ValueError("Lancer dupliqué")
            seen.add(key)
            if row["split"] != "validation":
                raise ValueError("Données hors validation")
            p = row["prediction"]
            size = p["size"]
            result = number(row["result"])
            expected = list(sector(p["center"], size))
            times = (
                p["last_frame_seconds"],
                p["created_seconds"],
                row["closes_at"],
                row["result_seconds"],
            )
            if not all(isinstance(t, (float, int)) and math.isfinite(t) for t in times):
                raise ValueError("Horodatages invalides")
            if not 0 <= times[0] <= times[1] < times[2] <= times[3]:
                raise ValueError("Chronologie invalide ou données après fermeture")
            if p["numbers"] != expected:
                raise ValueError("Zone incohérente")
            accepted.append((size, result in expected))
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(str(exc))
    groups = []
    for size in (9, 15, 19):
        hits = [hit for s, hit in accepted if s == size]
        n = len(hits)
        k = sum(hits)
        if n:
            rate = k / n
            z = 1.96
            denominator = 1 + z * z / n
            center = (rate + z * z / (2 * n)) / denominator
            half = (
                z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
            )
            interval = [max(0, center - half), min(1, center + half)]
        else:
            rate = None
            interval = None
        groups.append(
            {
                "size": size,
                "n": n,
                "hits": k,
                "rate": rate,
                "wilson_95": interval,
                "random_baseline": size / 37,
            }
        )
    return {
        "evaluable": len(accepted),
        "rejected": len(rejected),
        "reasons": rejected,
        "groups": groups,
        "warning": "Déclarations horodatées à auditer sur les vidéos. Aucun résultat ne démontre à lui seul un avantage.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Évaluation hors ligne de prédictions antérieures à la fermeture des mises."
    )
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.annotations.read_text(encoding="utf-8")))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
