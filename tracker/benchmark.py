"""Evaluate candidate localization on independently annotated recorded frames."""

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from .capture import crop_roi
from .experimental import CandidateTracker


def run(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("split") != "validation":
        raise ValueError(
            "Ce rapport exige un jeu de validation distinct du développement."
        )
    video = Path(manifest["video"])
    if not video.is_absolute():
        video = manifest_path.parent / video
    labels = {}
    for label in manifest["frames"]:
        index = label["frame"]
        point = label["ball_xy"]
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index in labels
        ):
            raise ValueError("Indices de frames invalides ou dupliqués.")
        if point is not None and (
            len(point) != 2
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)
        ):
            raise ValueError("Coordonnées de vérité terrain invalides.")
        labels[index] = point
    if not labels:
        raise ValueError("Aucune frame annotée : aucun taux de détection calculable.")
    tolerance = float(manifest.get("tolerance_pixels", 8))
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Tolérance positive requise.")
    roi = manifest["wheel_roi"]
    threshold = 0.8
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError("Vidéo illisible.")
    tracker = CandidateTracker()
    latencies = []
    checked = []
    index = 0
    visible = tp = fp = predicted = 0
    longest = run_length = 0
    previous_index = None
    started = time.perf_counter()
    last_index = max(labels)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Cadence source invalide.")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        while index <= last_index:
            ok, frame = cap.read()
            if not ok:
                break
            begin = time.perf_counter()
            crop = crop_roi(frame, roi)
            observation = tracker.analyze(crop, index / fps)
            latency = (time.perf_counter() - begin) * 1000
            if index in labels:
                latencies.append(latency)
                actual = labels[index]
                found = None
                if (
                    observation.point is not None
                    and observation.confidence >= threshold
                    and observation.omega is not None
                ):
                    found = (
                        roi[0] * width + observation.point[0],
                        roi[1] * height + observation.point[1],
                    )
                good = (
                    found is not None
                    and actual is not None
                    and math.dist(found, actual) <= tolerance
                )
                visible += actual is not None
                predicted += found is not None
                tp += good
                fp += found is not None and not good
                if good:
                    run_length = (
                        run_length + 1
                        if previous_index is not None and index == previous_index + 1
                        else 1
                    )
                else:
                    run_length = 0
                longest = max(longest, run_length)
                previous_index = index
                checked.append(index)
            index += 1
    finally:
        cap.release()
    if set(checked) != set(labels):
        raise ValueError(
            "Certaines annotations dépassent la vidéo décodable ; rapport refusé."
        )
    elapsed = time.perf_counter() - started
    return {
        "video": video.name,
        "split": "validation",
        "source": {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_seconds": count / fps,
        },
        "annotated_frames": len(checked),
        "visible_frames": visible,
        "candidate_predictions": predicted,
        "true_positives": tp,
        "false_positives": fp,
        "missed_visible_frames": visible - tp,
        "detection_rate": tp / visible if visible else None,
        "precision": tp / predicted if predicted else None,
        "longest_correct_continuous_seconds": longest / fps,
        "analysis_latency_ms": {
            "p50": float(np.median(latencies)),
            "p95": float(np.percentile(latencies, 95)),
        },
        "processed_frames": index,
        "processing_fps": index / elapsed,
        "candidate_score_threshold": threshold,
        "tolerance_pixels": tolerance,
        "warning": "Mesure de localisation sur annotations fournies, pas de validation de prédiction ni de gain. Les images non annotées ne contribuent pas au taux.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Mesurer le suivi sur une vidéo annotée, sans apprentissage."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.manifest)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
