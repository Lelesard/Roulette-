"""Local recording of experimental ball and rotor measurements."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path

from .experimental import direction_label


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class MeasurementRecorder:
    """Group analysis samples into local runs without storing images or URLs."""

    VERSION = 1

    def __init__(self, path, pre_roll_seconds=2.0, quiet_seconds=5.0):
        self.path = Path(path)
        self.pre_roll_seconds = pre_roll_seconds
        self.quiet_seconds = quiet_seconds
        self.pre_roll = deque(maxlen=120)
        self.runs = []
        self.current = None
        self.last_ball_at = None
        self.last_saved_at = None
        self.sequence = 0
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("format_version") != self.VERSION:
                return
            self.runs = payload.get("runs", [])[-200:]
            active = payload.get("active_run")
            if active:
                active["ended_utc"] = utc_now()
                active["ended_reason"] = "interruption de l’application"
                active["sample_count"] = len(active.get("samples", []))
                self.runs.append(active)
            self.sequence = max(
                (int(run.get("sequence", 0)) for run in self.runs), default=0
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.runs = []

    @staticmethod
    def _sample(context, track, received):
        return {
            "_received": float(received),
            "source_seconds": float(track.seconds),
            "session_id": int(context[1]),
            "source_kind": str(context[2]),
            "camera_epoch": int(context[4]) if len(context) > 4 else 0,
            "ball_direction": direction_label(track.omega),
            "ball_omega_rad_s": track.omega,
            "ball_alpha_rad_s2": track.alpha,
            "ball_confidence": float(track.confidence),
            "ball_point_px": list(track.point) if track.point is not None else None,
            "ball_message": track.message,
            "rotor_direction": direction_label(track.rotor_omega),
            "rotor_omega_rad_s": track.rotor_omega,
            "rotor_confidence": float(track.rotor_confidence),
            "rotor_message": track.rotor_message,
        }

    def add(self, context, track, received):
        row = self._sample(context, track, received)
        ball_valid = track.omega is not None
        if self.current is not None and any(
            self.current.get(key) != row[key]
            for key in ("session_id", "source_kind", "camera_epoch")
        ):
            self.finish("changement de contexte", received)
        if self.current is None:
            self.pre_roll.append(row)
            while (
                self.pre_roll
                and received - self.pre_roll[0]["_received"] > self.pre_roll_seconds
            ):
                self.pre_roll.popleft()
            if ball_valid:
                self.sequence += 1
                self.current = {
                    "sequence": self.sequence,
                    "started_utc": utc_now(),
                    "session_id": row["session_id"],
                    "source_kind": row["source_kind"],
                    "camera_epoch": row["camera_epoch"],
                    "result": None,
                    "spin_id": None,
                    "samples": list(self.pre_roll),
                }
                self.pre_roll.clear()
                self.last_ball_at = received
                self.last_saved_at = received
                self._save()
            return

        self.current["samples"].append(row)
        if len(self.current["samples"]) > 2400:
            self.current["samples"] = self.current["samples"][-2400:]
        if ball_valid:
            self.last_ball_at = received
        if self.last_ball_at is not None and received - self.last_ball_at >= self.quiet_seconds:
            self.finish(
                f"aucune bille validée depuis {self.quiet_seconds:g} secondes",
                received,
            )
        elif self.last_saved_at is None or received - self.last_saved_at >= 1.0:
            self.last_saved_at = received
            self._save()

    def finish(self, reason, received=None):
        if self.current is None:
            return None
        samples = self.current.get("samples", [])
        first = samples[0]["_received"] if samples else received or 0.0
        last = samples[-1]["_received"] if samples else received or first
        self.current["ended_utc"] = utc_now()
        self.current["ended_reason"] = reason
        self.current["duration_seconds"] = max(0.0, last - first)
        self.current["sample_count"] = len(samples)
        run = self.current
        self.runs.append(run)
        self.runs = self.runs[-200:]
        self.current = None
        self.last_ball_at = None
        self.last_saved_at = None
        self._save()
        return run

    def attach_result(self, number, spin_id=None, session_id=None):
        if self.current is not None:
            self.finish("résultat saisi")
        target = next(
            (
                run
                for run in reversed(self.runs)
                if run.get("result") is None
                and (
                    session_id is None
                    or int(run.get("session_id", -1)) == int(session_id)
                )
            ),
            None,
        )
        if target is None:
            return False
        target["result"] = int(number)
        target["spin_id"] = spin_id
        self._save()
        return True

    @staticmethod
    def _public_run(run):
        public = {key: value for key, value in run.items() if key != "samples"}
        samples = []
        raw = run.get("samples", [])
        origin = raw[0].get("_received", 0.0) if raw else 0.0
        for sample in raw:
            if "_received" not in sample:
                samples.append(dict(sample))
                continue
            item = {key: value for key, value in sample.items() if key != "_received"}
            item["elapsed_seconds"] = max(
                0.0, float(sample.get("_received", origin)) - origin
            )
            samples.append(item)
        public["samples"] = samples
        public["sample_count"] = len(samples)
        return public

    def payload(self):
        return {
            "format_version": self.VERSION,
            "tracker_version": "measurements-v11",
            "generated_utc": utc_now(),
            "privacy": "Aucune image, URL, titre de fenêtre ou identifiant casino.",
            "runs": [self._public_run(run) for run in self.runs],
            "active_run": (
                self._public_run(self.current) if self.current is not None else None
            ),
        }

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def export(self, path):
        target = Path(path)
        target.write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def status(self):
        if self.current is not None:
            count = len(self.current.get("samples", []))
            return f"Mesures v11 : lancer {self.current['sequence']} actif • {count} échantillons"
        return f"Mesures v11 : {len(self.runs)} lancer(s) enregistré(s) • en attente d’une bille validée"
