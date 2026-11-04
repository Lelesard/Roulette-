import json
import tempfile
import unittest
from pathlib import Path

from tracker.experimental import Track
from tracker.measurements import MeasurementRecorder


class MeasurementRecorderTests(unittest.TestCase):
    def track(self, seconds, ball=None, rotor=-0.2):
        return Track(
            seconds,
            point=(20.0, 30.0) if ball is not None else None,
            omega=ball,
            alpha=-0.3 if ball is not None else None,
            confidence=0.8 if ball is not None else 0.0,
            message="bille",
            rotor_omega=rotor,
            rotor_confidence=0.7 if rotor is not None else 0.0,
            rotor_message="rotor",
        )

    def test_records_preroll_finishes_and_attaches_manual_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "measurements.json"
            recorder = MeasurementRecorder(path, quiet_seconds=1.0)
            context = (1, 7, "live", "", 3)
            recorder.add(context, self.track(10.0), 100.0)
            recorder.add(context, self.track(10.2, ball=3.0), 100.2)
            self.assertIsNotNone(recorder.current)
            self.assertEqual(len(recorder.current["samples"]), 2)
            recorder.add(context, self.track(11.4), 101.4)
            self.assertIsNone(recorder.current)
            self.assertEqual(len(recorder.runs), 1)
            self.assertEqual(recorder.runs[0]["sample_count"], 3)
            self.assertTrue(recorder.attach_result(17, 42, session_id=7))
            self.assertEqual(recorder.runs[0]["result"], 17)
            self.assertFalse(recorder.attach_result(9, 43, session_id=8))

            exported = Path(tmp) / "export.json"
            recorder.export(exported)
            payload = json.loads(exported.read_text(encoding="utf-8"))
            self.assertEqual(payload["tracker_version"], "measurements-v11")
            self.assertEqual(payload["runs"][0]["result"], 17)
            self.assertNotIn("_received", json.dumps(payload))
            self.assertIn("elapsed_seconds", payload["runs"][0]["samples"][0])

    def test_recovers_interrupted_active_run_and_separates_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "measurements.json"
            first = MeasurementRecorder(path)
            first.add((1, 1, "live", "", 2), self.track(1.0, ball=2.0), 5.0)
            self.assertTrue(path.exists())

            recovered = MeasurementRecorder(path)
            self.assertEqual(len(recovered.runs), 1)
            self.assertEqual(
                recovered.runs[0]["ended_reason"], "interruption de l’application"
            )
            recovered.add(
                (2, 2, "video", "ignored.mp4", 0),
                self.track(2.0, ball=-2.0),
                8.0,
            )
            self.assertEqual(recovered.current["session_id"], 2)
            recovered.add(
                (3, 3, "live", "", 1), self.track(2.1, ball=-2.0), 8.1
            )
            self.assertEqual(len(recovered.runs), 2)
            self.assertEqual(recovered.current["session_id"], 3)


if __name__ == "__main__":
    unittest.main()
