import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import copy
import json
import math
import shutil
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from tracker.capture import crop_roi, brave_windows, detect_wheel_roi
from tracker.evaluation import PhysicalState, estimate, evaluate
from tracker.experimental import (
    CandidateTracker,
    RotorTracker,
    RotorTrack,
    Track,
    direction_label,
    validate_ball_direction,
)
from tracker.ocr import reconcile, read_numbers
from tracker.scene import SceneObserver, SceneObservation, intersection_over_union
from tracker.storage import Store
from tracker.benchmark import run as benchmark


class PersistenceTests(unittest.TestCase):
    def test_pending_settlement_and_rollback_are_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite"
            s = Store(path)
            sid = s.create_session("A", "VIP Roulette")
            bets = [{"kind": "plein", "target": "0", "stake": 10}]
            s.save_setting(f"pending_{sid}", bets)
            with self.assertRaises(ValueError):
                s.add_spin(
                    sid,
                    0,
                    [{"kind": "inconnu", "target": "0", "stake": 10}],
                    settle_pending=True,
                )
            self.assertEqual(s.setting(f"pending_{sid}"), bets)
            self.assertEqual(s.counts(sid), {})
            s.add_spin(sid, 0, bets, settle_pending=True)
            s.close()
            s = Store(path)
            self.assertEqual(s.setting(f"pending_{sid}"), [])
            self.assertEqual(s.summary(sid)["balance"], 350)
            s.close()

    def test_ocr_duplicates_repeated_outcome_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite"
            s = Store(path)
            sid = s.create_session("A", "B")
            first = [7, 7, 2, 19, 0]
            s.commit_ocr(sid, first, reconcile([], first))
            self.assertEqual(reconcile(first, first), [])
            # Repeated 7 is a distinct spin because the rest of the panel shifts.
            second = [7, 7, 7, 2, 19]
            self.assertEqual(reconcile(first, second), [7])
            s.commit_ocr(sid, second, [7])
            s.close()
            s = Store(path)
            self.assertEqual(s.ocr_snapshot(sid), second)
            self.assertEqual(s.counts(sid)[7], 3)
            self.assertEqual(s.summary(sid)["balance"], 0)
            with self.assertRaises(ValueError):
                s.commit_ocr(sid, [0, 1, 37], [1])
            self.assertEqual(s.ocr_snapshot(sid), second)
            s.close()

    def test_export_preserves_dates_and_attributes(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "store.sqlite")
            sid = s.create_session("A", "B")
            s.add_spin(sid, 0)
            for suffix in ("json", "csv"):
                path = Path(tmp) / ("export." + suffix)
                s.export(sid, path)
                other = s.create_session(suffix, "B")
                s.import_file(other, path)
                self.assertEqual(
                    s.spins(sid)[0]["created"], s.spins(other)[0]["created"]
                )
            obj = json.loads((Path(tmp) / "export.json").read_text())
            self.assertEqual(obj[0]["couleur"], "vert")
            self.assertEqual(obj[0]["position_cylindre"], 0)
            s.close()

    def test_mixed_bets_and_cash_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "store.sqlite")
            sid = s.create_session("A", "B")
            s.cash(sid, "initial", 10000)
            s.cash(sid, "dépôt", 1000)
            s.cash(sid, "retrait", 200)
            bets = [
                {"kind": "plein", "target": "1", "stake": 50},
                {"kind": "couleur", "target": "rouge", "stake": 100},
                {"kind": "douzaine", "target": "2", "stake": 100},
            ]
            spin = s.add_spin(sid, 1, bets)
            self.assertEqual(s.summary(sid)["gross"], 2000)
            self.assertEqual(s.summary(sid)["net"], 1750)
            self.assertEqual(s.summary(sid)["balance"], 12550)
            s.edit_spin(spin, 0)
            self.assertEqual(s.summary(sid)["losses"], 250)
            s.close()


class VisionTests(unittest.TestCase):
    def test_dynamic_scene_requires_stability_and_resets_on_camera_cut(self):
        observer = SceneObserver(confirmations=3)
        roi = (0.2, 0.15, 0.45, 0.55)
        dark = np.full((360, 640, 3), 20, np.uint8)
        bright = np.full((360, 640, 3), 235, np.uint8)
        with patch("tracker.scene.detect_wheel_roi", return_value=(roi, 0.8)):
            first = observer.analyze(dark, 0.0)
            second = observer.analyze(dark, 0.6)
            stable = observer.analyze(dark, 1.2)
            changed = observer.analyze(bright, 1.8)
        self.assertIsNone(first.wheel_roi)
        self.assertIsNone(second.wheel_roi)
        for actual, expected in zip(stable.wheel_roi, roi):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(changed.camera_changed)
        self.assertIsNone(changed.wheel_roi)
        self.assertEqual(changed.stable_frames, 1)

    def test_dynamic_scene_holds_brief_occlusion_then_drops_wheel(self):
        observer = SceneObserver(confirmations=2, hold_seconds=1.0)
        roi = (0.1, 0.2, 0.4, 0.5)
        frame = np.full((360, 640, 3), 70, np.uint8)
        with patch("tracker.scene.detect_wheel_roi", return_value=(roi, 0.75)):
            observer.analyze(frame, 0.0)
            observer.analyze(frame, 0.5)
        with patch(
            "tracker.scene.detect_wheel_roi",
            side_effect=ValueError("not visible"),
        ):
            held = observer.analyze(frame, 1.0)
            lost = observer.analyze(frame, 2.0)
        self.assertEqual(held.wheel_roi, roi)
        self.assertIsNone(lost.wheel_roi)
        self.assertGreater(intersection_over_union(roi, roi), 0.99)

    def test_automatic_wheel_calibration_finds_concentric_ellipse(self):
        frame = np.full((540, 960, 3), 24, np.uint8)
        center = (620, 245)
        axes = (205, 145)
        for inset, color in ((0, 235), (18, 80), (38, 220), (62, 70)):
            cv2.ellipse(
                frame,
                center,
                (axes[0] - inset, axes[1] - round(inset * 0.7)),
                -8,
                0,
                360,
                (color, color, color),
                4,
            )
        cv2.rectangle(frame, (10, 410), (950, 530), (70, 110, 40), -1)
        roi, score = detect_wheel_roi(frame)
        x, y, w, h = roi
        self.assertGreater(score, 0.54)
        self.assertLess(x, center[0] / 960)
        self.assertLess(y, center[1] / 540)
        self.assertGreater(x + w, center[0] / 960)
        self.assertGreater(y + h, center[1] / 540)
        self.assertGreater(w, 0.30)
        self.assertGreater(h, 0.35)

    def test_automatic_wheel_calibration_refuses_blank_or_small_images(self):
        with self.assertRaises(ValueError):
            detect_wheel_roi(np.zeros((80, 100, 3), np.uint8))
        with self.assertRaises(ValueError):
            detect_wheel_roi(np.zeros((360, 640, 3), np.uint8))

    def test_regions_and_ambiguous_overlap(self):
        frame = np.zeros((100, 200, 3), np.uint8)
        self.assertEqual(crop_roi(frame, (0.1, 0.2, 0.5, 0.4)).shape, (40, 100, 3))
        for roi in ((-1, 0, 0.5, 0.5), (0.9, 0, 0.5, 0.5), (0, 0, 0, 0.5)):
            with self.assertRaises(ValueError):
                crop_roi(frame, roi)
        self.assertIsNone(reconcile([1, 2, 3, 4], [20, 21, 22, 23]))
        self.assertIsNone(reconcile([1, 1, 1, 1], [2, 1, 1, 1, 1]))
        self.assertEqual(reconcile([1, 2, 3, 4], [1, 2, 3]), [])

    def test_tracker_synthetic_continuity_loss_and_camera_change(self):
        tracker = CandidateTracker()
        observation = None
        for i in range(30):
            frame = np.zeros((200, 200, 3), np.uint8)
            angle = i * 0.04
            cv2.circle(
                frame,
                (round(100 + 85 * math.cos(angle)), round(100 + 85 * math.sin(angle))),
                3,
                (255, 255, 255),
                -1,
            )
            observation = tracker.analyze(frame, i / 30)
        self.assertIsNotNone(observation.omega)
        self.assertAlmostEqual(observation.omega, 1.2, delta=0.2)
        lost = tracker.analyze(np.zeros_like(frame), 1.0)
        self.assertIsNone(lost.point)
        self.assertEqual(lost.confidence, 0)
        changed = tracker.analyze(np.full_like(frame, 255), 1.1)
        self.assertIn("caméra", changed.message)
        self.assertFalse(tracker.points)

    def test_tracker_selects_moving_ball_among_static_reflections(self):
        tracker = CandidateTracker()
        observation = None
        for index in range(36):
            frame = np.zeros((240, 240, 3), np.uint8)
            for reflection in (0.2, 1.7, 3.4, 5.1):
                cv2.circle(
                    frame,
                    (
                        round(120 + 96 * math.cos(reflection)),
                        round(120 + 96 * math.sin(reflection)),
                    ),
                    3,
                    (225, 225, 225),
                    -1,
                )
            angle = index * 0.065
            ball = (
                round(120 + 98 * math.cos(angle)),
                round(120 + 98 * math.sin(angle)),
            )
            cv2.circle(frame, ball, 4, (255, 255, 255), -1)
            observation = tracker.analyze(frame, index / 30)
        self.assertIsNotNone(observation.omega)
        self.assertAlmostEqual(observation.omega, 1.95, delta=0.35)
        self.assertLess(math.dist(observation.point, ball), 5)
        self.assertIn("non validé", observation.message)

    def test_tracker_survives_two_missing_frames_without_inventing_points(self):
        tracker = CandidateTracker()
        observation = None
        for index in range(28):
            frame = np.zeros((200, 200, 3), np.uint8)
            angle = index * 0.05
            if index not in (14, 15):
                cv2.circle(
                    frame,
                    (
                        round(100 + 84 * math.cos(angle)),
                        round(100 + 84 * math.sin(angle)),
                    ),
                    3,
                    (255, 255, 255),
                    -1,
                )
            observation = tracker.analyze(frame, index / 30)
            if index in (14, 15):
                self.assertIsNone(observation.point)
        self.assertIsNotNone(observation.omega)
        self.assertAlmostEqual(observation.omega, 1.5, delta=0.3)

    def test_direction_labels_follow_the_displayed_image(self):
        self.assertEqual(direction_label(1.0), "horaire à l’écran")
        self.assertEqual(direction_label(-1.0), "antihoraire à l’écran")
        self.assertEqual(direction_label(None), "non mesuré")

    def test_ball_direction_requires_speed_independent_from_rotor(self):
        candidate = Track(
            1.0,
            point=(20, 30),
            omega=2.0,
            alpha=-0.2,
            confidence=0.8,
            message="candidat cohérent",
        )
        waiting = validate_ball_direction(candidate, RotorTrack(1.0))
        self.assertIsNone(waiting.omega)
        self.assertIsNotNone(waiting.point)
        self.assertIn("attente", waiting.message)

        rejected = validate_ball_direction(
            candidate, RotorTrack(1.0, omega=0.5, confidence=0.7)
        )
        self.assertIsNone(rejected.omega)
        self.assertIsNone(rejected.point)
        self.assertIn("vitesse", rejected.message)

        same_direction_fast = replace(candidate, omega=4.0)
        validated_same = validate_ball_direction(
            same_direction_fast, RotorTrack(1.0, omega=0.5, confidence=0.7)
        )
        self.assertEqual(validated_same.omega, 4.0)
        self.assertIn("même sens", validated_same.message)

        validated_opposite = validate_ball_direction(
            same_direction_fast, RotorTrack(1.0, omega=-0.5, confidence=0.7)
        )
        self.assertEqual(validated_opposite.point, candidate.point)
        self.assertIn("sens opposé", validated_opposite.message)

    def test_rotor_tracker_detects_both_rotation_directions(self):
        size = 240
        center = (size // 2, size // 2)
        base = np.zeros((size, size, 3), np.uint8)
        rng = np.random.default_rng(4)
        for _ in range(80):
            angle = rng.uniform(0, 2 * math.pi)
            radius = rng.uniform(45, 90)
            value = int(rng.integers(80, 256))
            dot_radius = int(rng.integers(1, 4))
            cv2.circle(
                base,
                (
                    round(center[0] + radius * math.cos(angle)),
                    round(center[1] + radius * math.sin(angle)),
                ),
                dot_radius,
                (value, value, value),
                -1,
            )

        for degrees_per_frame, expected_sign in ((-2, 1), (2, -1)):
            tracker = RotorTracker()
            observation = None
            for index in range(30):
                transform = cv2.getRotationMatrix2D(
                    center, degrees_per_frame * index, 1
                )
                frame = cv2.warpAffine(base, transform, (size, size))
                observation = tracker.analyze(frame, index / 30)
            self.assertIsNotNone(observation.omega)
            self.assertEqual(int(np.sign(observation.omega)), expected_sign)
            self.assertGreater(observation.confidence, 0.8)

    def test_rotor_tracker_rejects_an_unchanged_blank_wheel(self):
        tracker = RotorTracker()
        observation = None
        frame = np.zeros((200, 200, 3), np.uint8)
        for index in range(12):
            observation = tracker.analyze(frame, index / 30)
        self.assertIsNone(observation.omega)
        self.assertIn("détails insuffisants", observation.message)

    def test_rotor_tracker_tolerates_brief_ambiguous_images(self):
        size = 240
        center = (size // 2, size // 2)
        base = np.zeros((size, size, 3), np.uint8)
        rng = np.random.default_rng(8)
        for _ in range(90):
            angle = rng.uniform(0, 2 * math.pi)
            radius = rng.uniform(45, 90)
            point = (
                round(center[0] + radius * math.cos(angle)),
                round(center[1] + radius * math.sin(angle)),
            )
            cv2.circle(base, point, 2, (220, 220, 220), -1)
        tracker = RotorTracker()
        observation = None
        for index in range(8):
            transform = cv2.getRotationMatrix2D(center, -2 * index, 1)
            frame = cv2.warpAffine(base, transform, (size, size))
            observation = tracker.analyze(frame, index / 30)
        self.assertIsNotNone(observation.omega)
        blank = np.zeros_like(base)
        tracker.analyze(blank, 8 / 30)
        tracker.analyze(blank, 9 / 30)
        for index in range(10, 13):
            transform = cv2.getRotationMatrix2D(center, -2 * index, 1)
            frame = cv2.warpAffine(base, transform, (size, size))
            observation = tracker.analyze(frame, index / 30)
        self.assertIsNotNone(observation.omega)
        self.assertGreater(observation.omega, 0)

    @unittest.skipUnless(
        shutil.which("tesseract"), "Moteur Tesseract facultatif absent"
    )
    def test_real_tesseract_on_generated_panel(self):
        image = np.full((80, 750, 3), 255, np.uint8)
        for index, n in enumerate([7, 12, 18, 4, 21]):
            cv2.putText(
                image,
                str(n),
                (15 + index * 145, 57),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
        self.assertEqual(read_numbers(image), [7, 12, 18, 4, 21])
        self.assertEqual(read_numbers(image, newest_left=False), [21, 4, 18, 12, 7])

    @unittest.skipIf(os.name == "nt", "Le refus hors Windows ne concerne pas Windows")
    def test_capture_explains_unsupported_platform(self):
        with self.assertRaisesRegex(RuntimeError, "Windows"):
            brave_windows()


class EvaluationTests(unittest.TestCase):
    def test_benchmark_requires_annotations_and_does_not_invent_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.avi"
            writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (100, 100)
            )
            for _ in range(10):
                writer.write(np.zeros((100, 100, 3), np.uint8))
            writer.release()
            manifest = {
                "video": "blank.avi",
                "split": "validation",
                "wheel_roi": [0, 0, 1, 1],
                "frames": [
                    {"frame": 0, "ball_xy": None},
                    {"frame": 9, "ball_xy": None},
                ],
            }
            annotations = Path(tmp) / "manifest.json"
            annotations.write_text(json.dumps(manifest))
            report = benchmark(annotations)
            self.assertEqual(report["annotated_frames"], 2)
            self.assertIsNone(report["detection_rate"])
            self.assertIsNone(report["precision"])
            manifest["frames"] = []
            annotations.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Aucune frame"):
                benchmark(annotations)

    def state(self):
        return PhysicalState(
            seconds=2,
            last_frame_seconds=2,
            ball_angle=0.5,
            ball_omega=8,
            ball_alpha=-2,
            rotor_angle=0.2,
            rotor_omega=-1,
            release_speed=3,
            fall_seconds=0.3,
            rebound_offset=0.1,
            uncertainty_radians=0.4,
            confidence=0.95,
            calibrated=True,
        )

    def test_model_refuses_future_frames_missing_calibration_and_large_uncertainty(
        self,
    ):
        state = self.state()
        prediction = estimate(state, 3, 9)
        self.assertEqual(len(prediction["numbers"]), 9)
        for changed in (
            replace(state, calibrated=False),
            replace(state, last_frame_seconds=2.1),
            replace(state, uncertainty_radians=3),
            replace(state, ball_alpha=2),
            replace(state, confidence=0.8),
            replace(state, ball_angle=float("nan")),
        ):
            self.assertIsNone(estimate(changed, 3, 9))
        self.assertIsNone(estimate(state, 2))

    def test_evaluation_rejects_leakage_duplicates_and_development_set(self):
        p = estimate(self.state(), 3, 9)
        row = {
            "video": "fixture.mp4",
            "spin_id": 1,
            "split": "validation",
            "prediction": p,
            "closes_at": 3,
            "result_seconds": 8,
            "result": p["center"],
        }
        late = copy.deepcopy(row)
        late["spin_id"] = 2
        late["prediction"]["last_frame_seconds"] = 3.1
        development = copy.deepcopy(row)
        development["spin_id"] = 3
        development["split"] = "development"
        report = evaluate([row, row, late, development])
        self.assertEqual(report["evaluable"], 1)
        self.assertEqual(report["rejected"], 3)
        self.assertEqual(report["groups"][0]["hits"], 1)
        self.assertIsNone(evaluate([])["groups"][0]["rate"])


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.qt_errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.qt_errors.append(
            f"{kind.__name__}: {value}"
        )

    def tearDown(self):
        self.app.processEvents()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.qt_errors, [], "Exception dans un callback Qt")

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_manual_roi_touch_and_profile_persistence(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gui.sqlite"
            w = Window(path)
            w.show()
            self.app.processEvents()
            try:
                image = QImage(640, 360, QImage.Format.Format_RGB888)
                image.fill(Qt.GlobalColor.black)
                w.live_image.set_image(image)
                w.begin_roi(w.live_image, "wheel_roi")
                rect = w.live_image.image_rect()
                a = QPoint(
                    round(rect.x() + rect.width() * 0.1),
                    round(rect.y() + rect.height() * 0.1),
                )
                b = QPoint(
                    round(rect.x() + rect.width() * 0.7),
                    round(rect.y() + rect.height() * 0.8),
                )
                QTest.mousePress(w.live_image, Qt.MouseButton.LeftButton, pos=a)
                QTest.mouseMove(w.live_image, b)
                QTest.mouseRelease(w.live_image, Qt.MouseButton.LeftButton, pos=b)
                self.assertAlmostEqual(
                    w.store.profile(w.active_table())["wheel_roi"][0], 0.1, delta=0.01
                )
                w.add_bet("plein", "0")
                saved = list(w.bets)
                sid = w.sid
            finally:
                w.close()
                self.app.processEvents()
            w = Window(path)
            try:
                self.assertEqual(w.sid, sid)
                self.assertEqual(w.bets, saved)
                self.assertIn("wheel_roi", w.store.profile(w.active_table()))
            finally:
                w.close()
                self.app.processEvents()

    def test_automatic_calibration_requires_confirmation(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                frame = np.zeros((360, 640, 3), np.uint8)
                image = QImage(640, 360, QImage.Format.Format_RGB888)
                image.fill(Qt.GlobalColor.black)
                w.latest_frame = frame
                w.live_image.set_image(image)
                proposed = (0.2, 0.1, 0.5, 0.7)
                with (
                    patch("tracker.live.detect_wheel_roi", return_value=(proposed, 0.82)),
                    patch(
                        "tracker.live.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.No,
                    ),
                ):
                    w.auto_calibrate_wheel(w.live_image)
                self.assertNotIn("wheel_roi", w.store.profile(w.active_table()))
                with (
                    patch("tracker.live.detect_wheel_roi", return_value=(proposed, 0.82)),
                    patch(
                        "tracker.live.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                ):
                    w.auto_calibrate_wheel(w.live_image)
                self.assertEqual(
                    tuple(w.store.profile(w.active_table())["wheel_roi"]), proposed
                )
                self.assertNotIn("wheel_candidate", w.live_image.regions)
            finally:
                w.close()
                self.app.processEvents()

    def test_dynamic_scene_overlay_is_ephemeral_and_clears_on_cut(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                self.assertFalse(w.experimental_enabled.isChecked())
                epoch_before_toggle = w.camera_epoch
                w.experimental_enabled.setChecked(True)
                self.assertTrue(w.store.setting("experimental_ball"))
                self.assertEqual(w.camera_epoch, epoch_before_toggle + 1)
                w.latest_kind = "live"
                context = (w.source_epoch, w.sid, "live", "", w.camera_epoch)
                roi = (0.2, 0.1, 0.4, 0.5)
                stable = SceneObservation(
                    1.0, False, "wheel", roi, roi, 0.8, 3, "Roue stable"
                )
                w.scene_busy = True
                w.scene_ready(context, stable)
                self.assertEqual(w.dynamic_wheel_roi, roi)
                self.assertEqual(w.live_image.regions["wheel_dynamic"], roi)
                self.assertNotIn(
                    "wheel_dynamic", w.store.profile(w.active_table())
                )
                epoch = w.camera_epoch
                changed = SceneObservation(
                    1.6,
                    True,
                    "wheel",
                    roi,
                    None,
                    0.8,
                    1,
                    "Changement de caméra",
                )
                w.scene_ready(context, changed)
                self.assertEqual(w.camera_epoch, epoch + 1)
                self.assertIsNone(w.dynamic_wheel_roi)
                self.assertNotIn("wheel_dynamic", w.live_image.regions)
            finally:
                w.close()
                self.app.processEvents()

    def test_ocr_worker_is_queued_and_stale_context_is_ignored(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                w.ocr_enabled.setChecked(True)
                w.ocr_auto.setChecked(True)
                context = (w.source_epoch, w.sid, "video", "fixture")
                with patch("tracker.ocr.read_numbers", return_value=[7, 2, 19, 0]):
                    for attempt in range(2):
                        w.ocr_busy = True
                        w.ocr_request.emit(
                            context, np.zeros((20, 100, 3), np.uint8), "", True
                        )
                        self.wait(lambda: not w.ocr_busy)
                self.assertEqual(sum(w.store.counts(w.sid).values()), 4)
                w.reset_ocr_proposal()
                w.ocr_ready(context, [9, 7, 2, 19])
                w.ocr_ready(context, [9, 7, 2, 19])
                self.assertEqual(sum(w.store.counts(w.sid).values()), 4)
            finally:
                w.close()
                self.app.processEvents()

    def test_analysis_worker_runs_without_blocking_sqlite_or_ui(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                context = (w.source_epoch, w.sid, "video", "fixture")
                w.analysis_busy = True
                w.analysis_request.emit(context, np.zeros((100, 100, 3), np.uint8), 0.0)
                self.wait(lambda: not w.analysis_busy)
                self.assertIn("Aucune estimation fiable", w.track_status.text())
            finally:
                w.close()
                self.app.processEvents()

    def test_last_directions_remain_visible_after_current_measurement_is_lost(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                context = (w.source_epoch, w.sid, "video", "fixture")
                w.analysis_ready(
                    context,
                    Track(
                        1.0,
                        omega=2.0,
                        confidence=0.8,
                        message="candidat",
                        rotor_omega=-1.0,
                        rotor_confidence=0.7,
                        rotor_message="rotor",
                    ),
                )
                w.analysis_ready(
                    context,
                    Track(
                        1.1,
                        message="bille perdue",
                        rotor_message="rotor immobile",
                    ),
                )
                status = w.track_status.text()
                self.assertIn("Dernière direction bille : horaire", status)
                self.assertIn("Dernière direction rotor : antihoraire", status)
                self.assertIn("Bille maintenant : non mesuré", status)
            finally:
                w.close()
                self.app.processEvents()

    def test_capture_watchdog_and_log_identify_stalled_stream(self):
        from tracker.gui import Window
        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                self.assertIn("enregistreur de lancers v11", w.windowTitle())
                w.capture_active = True
                w.capture_started_at = time.monotonic() - 4
                w.poll_capture()
                self.assertIn("Aucune nouvelle image", w.capture_status.text())
                self.assertIn("ui.stalled", w.capture_log_path.read_text())
                with w.capture_worker._lock:
                    w.capture_worker._latest = (np.zeros((48, 64, 3), np.uint8), time.monotonic(), 1.0)
                w.poll_capture()
                self.assertFalse(w.capture_stale)
                self.assertIn("Image 1", w.capture_status.text())
                self.assertIn("ui.frame.end image=1", w.capture_log_path.read_text())
            finally:
                w.close()
                self.app.processEvents()

    def test_preview_exception_is_logged_and_reported(self):
        from tracker.gui import Window
        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                w.capture_active = True
                with w.capture_worker._lock:
                    w.capture_worker._latest = (np.zeros((48, 64, 3), np.uint8), time.monotonic(), 1.0)
                with patch.object(w.live_image, "set_image", side_effect=RuntimeError("fixture display failure")):
                    w.poll_capture()
                self.assertFalse(w.capture_active)
                self.assertIn("fixture display failure", w.capture_status.text())
                self.assertIn("ui.preview_failure", w.capture_log_path.read_text())
            finally:
                w.close()
                self.app.processEvents()

    def test_mss_thread_local_resources_survive_frames_stop_and_restart(self):
        from tracker.gui import Window
        from threading import local, current_thread
        screens = []
        class ThreadLocalScreen:
            monitors = [dict(left=0, top=0, width=64, height=48)]
            def __init__(self):
                self.handles = local()
                self.handles.srcdc = object()
                self.handles.bmp = object()
                self.owner = current_thread()
                self.frames = 0
                self.closed = False
                self.fail_after = None
                screens.append(self)
            def grab(self, region):
                # Models MSS Windows' thread-local HDC and bitmap handles.
                self.handles.srcdc
                if current_thread() is not self.owner:
                    raise AssertionError("MSS thread changed")
                if self.fail_after is not None and self.frames >= self.fail_after:
                    raise RuntimeError("simulated Windows acquisition failure")
                self.frames += 1
                return np.full((48, 64, 4), self.frames, np.uint8)
            def close(self):
                self.handles.bmp
                if current_thread() is not self.owner:
                    raise AssertionError("MSS close thread changed")
                self.closed = True
        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            errors = []
            w.capture_worker.error.connect(errors.append)
            try:
                with patch("tracker.capture.client_region", return_value=dict(left=0, top=0, width=64, height=48)), patch("mss.mss", side_effect=ThreadLocalScreen):
                    for run in range(2):
                        w.capture_active = True
                        w.start_capture_signal.emit(101, 30)
                        self.wait(lambda: len(screens) == run + 1 and screens[-1].frames >= 5)
                        self.wait(lambda: w.live_image.image is not None)
                        w.stop_capture()
                        self.wait(lambda: screens[-1].closed)
                        self.wait(lambda: not screens[-1].owner.is_alive())
                    self.assertEqual(errors, [])
                    w.capture_active = True
                    w.start_capture_signal.emit(101, 30)
                    self.wait(lambda: len(screens) == 3 and screens[-1].frames >= 2)
                    screens[-1].fail_after = screens[-1].frames
                    self.wait(lambda: bool(errors))
                    self.wait(lambda: screens[-1].closed)
                    self.assertIn("simulated Windows acquisition failure", errors[0])
                    self.assertTrue(all(s.closed for s in screens))
                    # A failure must not poison subsequent starts or cleanup.
                    w.capture_active = True
                    w.start_capture_signal.emit(101, 30)
                    self.wait(lambda: len(screens) == 4 and screens[-1].frames >= 3)
                    w.stop_capture()
                    self.wait(lambda: screens[-1].closed)
                    self.assertEqual(len(errors), 1)
            finally:
                w.close()
                self.app.processEvents()

    def test_capture_continues_without_ack_and_recovers_after_ui_pause(self):
        from tracker.gui import Window

        class FakeScreen:
            monitors = [dict(left=0, top=0, width=640, height=360)]

            def __init__(self):
                self.count = 0
                self.closed = False
                self.threads = []

            def grab(self, region):
                from threading import get_ident
                self.threads.append(get_ident())
                self.count += 1
                return np.full((360, 640, 4), self.count % 256, np.uint8)

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            try:
                with (
                    patch(
                        "tracker.capture.client_region",
                        return_value=dict(left=0, top=0, width=640, height=360),
                    ),
                    patch("mss.mss", side_effect=FakeScreen) as make_screen,
                ):
                    w.capture_active = True
                    w.start_capture_signal.emit(101, 10)
                    self.wait(lambda: w.live_image.image is not None)
                    self.assertIn("640 × 360", w.capture_status.text())
                    self.wait(lambda: w.capture_count >= 5)
                    screen = w.capture_worker.screen
                    self.assertEqual(w.live_image.image.pixelColor(0, 0).red(), screen.count % 256)
                    from threading import get_ident
                    self.assertTrue(all(t != get_ident() for t in screen.threads))
                    before = screen.count
                    # Simulate a busy UI: capture must continue independently.
                    time.sleep(0.4)
                    self.assertGreaterEqual(screen.count, before + 2)
                    newest = screen.count
                    self.app.processEvents()
                    self.assertGreaterEqual(w.live_image.image.pixelColor(0, 0).red(), newest)
                    w.stop_capture()
                    self.wait(lambda: w.capture_worker.screen is None)
                    stopped_count = w.capture_count
                    time.sleep(0.15)
                    self.app.processEvents()
                    self.assertEqual(w.capture_count, stopped_count)
                    w.capture_active = True
                    w.start_capture_signal.emit(101, 30)
                    self.wait(lambda: w.capture_count >= stopped_count + 3)
                    w.stop_capture()
                    self.wait(lambda: w.capture_worker.screen is None)
            finally:
                w.close()
                self.app.processEvents()
