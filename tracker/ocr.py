"""Conservative OCR proposals, never derived from browser traffic."""

import shutil
import subprocess
import tempfile
import csv
import io
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, Signal, Slot


def reconcile(previous, current, min_overlap=3):
    """Newest-first lists. Return new prefix, or None if overlap is ambiguous.

    Identical snapshots do not create results. Repeated identical outcomes cannot
    be resolved from a static panel alone and are deliberately not inferred.
    """
    if len(current) < min_overlap:
        return None
    if not previous:
        return list(current)
    overlap = min(len(current), len(previous))
    if current[:overlap] == previous[:overlap] and overlap >= min_overlap:
        return []
    matches = []
    for added in range(1, len(current) - min_overlap + 1):
        length = min(len(previous), len(current) - added)
        if (
            length >= min_overlap
            and current[added : added + length] == previous[:length]
        ):
            matches.append(current[:added])
    return matches[0] if len(matches) == 1 else None


def read_numbers(frame, executable="", newest_left=True):
    command = executable.strip() or shutil.which("tesseract")
    if not command or not Path(command).is_file():
        raise ValueError(
            "Tesseract absent. Installez-le et indiquez tesseract.exe dans Paramètres."
        )
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    with tempfile.TemporaryDirectory(prefix="roulette-ocr-") as temp:
        path = Path(temp) / "panel.png"
        if not cv2.imwrite(str(path), gray):
            raise ValueError("Écriture temporaire OCR impossible.")
        result = subprocess.run(
            [
                command,
                str(path),
                "stdout",
                "--psm",
                "6",
                "-c",
                "tessedit_char_whitelist=0123456789 ",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if result.returncode:
        raise ValueError("Tesseract : " + result.stderr.strip()[-250:])
    tokens = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = row.get("text", "").strip()
        if not text:
            continue
        if (
            not text.isdigit()
            or len(text) > 2
            or not 0 <= int(text) <= 36
            or (len(text) > 1 and text.startswith("0"))
        ):
            raise ValueError(
                "OCR ambigu : nombre illisible ou chiffres fusionnés. Recalibrez le panneau."
            )
        confidence = float(row["conf"]) / 100
        tokens.append((int(row["top"]), int(row["left"]), int(text), confidence))
    if len(tokens) < 3 or min(t[3] for t in tokens) < 0.85:
        raise ValueError(
            "OCR insuffisant : au moins 3 numéros séparés avec score ≥ 85 % requis."
        )
    # Tesseract reading order is top-to-bottom then left-to-right.
    values = [t[2] for t in tokens]
    return values if newest_left else values[::-1]


class OCRWorker(QObject):
    ready = Signal(object, object)  # context token, newest-first snapshot
    error = Signal(object, str)

    @Slot(object, object, str, bool)
    def read(self, context, frame, executable, newest_left):
        try:
            self.ready.emit(context, read_numbers(frame, executable, newest_left))
        except Exception as exc:
            self.error.emit(context, str(exc))
