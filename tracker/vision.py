"""Contrat d’extension hors ligne : aucune recommandation de mise."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Observation:
    seconds: float
    ball_xy: tuple[float, float] | None = None
    rotor_angle: float | None = None
    confidence: float = 0.0
    diagnostic: str = "Aucun détecteur installé"


class OfflineAnalyzer(Protocol):
    def reset(self) -> None: ...
    def analyze(self, frame, seconds: float) -> Observation: ...


class NoDetector:
    def reset(self):
        pass

    def analyze(self, frame, seconds):
        return Observation(seconds)
