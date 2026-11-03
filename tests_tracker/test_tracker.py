import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import time
import sys
import unittest
from pathlib import Path
from tracker.domain import WHEEL, sector, cents, payout, attributes
from tracker.storage import Store


class DomainTests(unittest.TestCase):
    def test_sectors_wrap_and_money(self):
        self.assertEqual(len(set(WHEEL)), 37)
        for n in WHEEL:
            for size in (9, 15, 19):
                s = sector(n, size)
                self.assertEqual(len(set(s)), size)
                self.assertEqual(s[size // 2], n)
        self.assertEqual(cents("0,10"), 10)
        for invalid in ("NaN", "Infinity", "0", "-1", "0.001"):
            with self.assertRaises(ValueError):
                cents(invalid)

    def test_payouts_and_zero(self):
        self.assertEqual(payout("plein", "0", 10, 0), 360)
        self.assertEqual(payout("couleur", "rouge", 50, 3), 100)
        self.assertEqual(payout("douzaine", "2", 100, 13), 300)
        self.assertEqual(payout("colonne", "3", 100, 36), 300)
        for k, t in [
            ("couleur", "rouge"),
            ("parité", "pair"),
            ("hauteur", "manque"),
            ("douzaine", "1"),
            ("colonne", "1"),
        ]:
            self.assertEqual(payout(k, t, 100, 0), 0)
        self.assertEqual(attributes(0)["parité"], "—")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite"
        self.store = Store(self.path)
        self.sid = self.store.create_session("Essai", "Table A")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_finance_corrections_and_restart(self):
        s = self.store
        s.cash(self.sid, "initial", 10000)
        s.cash(self.sid, "dépôt", 1000)
        s.cash(self.sid, "retrait", 500)
        spin = s.add_spin(
            self.sid,
            0,
            [
                {"kind": "plein", "target": "0", "stake": 10},
                {"kind": "plein", "target": "32", "stake": 10},
            ],
        )
        self.assertEqual(s.summary(self.sid)["balance"], 10840)
        s.edit_spin(spin, 1)
        self.assertEqual(s.summary(self.sid)["balance"], 10480)
        s.edit_spin(spin)
        self.assertEqual(s.summary(self.sid)["balance"], 10500)
        s.add_spin(self.sid, 7)
        self.assertEqual(s.summary(self.sid)["balance"], 10500)
        s.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.counts(self.sid), {7: 1})
        self.assertEqual(self.store.summary(self.sid)["balance"], 10500)

    def test_import_atomic_export_and_pagination(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_text('[{"number":2},{"number":37}]')
        with self.assertRaises(ValueError):
            self.store.import_file(self.sid, path)
        self.assertEqual(self.store.counts(self.sid), {})
        for i in range(105):
            self.store.add_spin(self.sid, i % 37)
        self.assertEqual(len(self.store.spins(self.sid, 100, 100)), 5)
        for ext in ("json", "csv"):
            path = Path(self.tmp.name) / ("export." + ext)
            self.store.export(self.sid, path)
            sid = self.store.create_session(ext, "B")
            self.assertEqual(self.store.import_file(sid, path), 105)
            self.assertEqual(self.store.counts(sid), self.store.counts(self.sid))

    def test_void_audit_and_session_isolation(self):
        self.store.cash(self.sid, "initial", 5000)
        with self.assertRaises(ValueError):
            self.store.cash(self.sid, "initial", 5)
        sid = self.store.create_session("Autre", "B")
        self.assertEqual(self.store.summary(sid)["balance"], 0)
        self.store.void(self.store.operations(self.sid)[0]["id"])
        self.assertEqual(self.store.summary(self.sid)["balance"], 0)
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1
        )


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

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
        self.assertEqual(self.qt_errors, [])

    def test_window_manual_workflow(self):
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "gui.sqlite")
            w.show()
            self.app.processEvents()
            try:
                w.store.cash(w.sid, "initial", 10000)
                w.center.setValue(0)
                w.chip.setCurrentText("0,10")
                w.add_bet("plein", "0")
                w.result.setValue(0)
                w.record()
                self.assertEqual(w.store.summary(w.sid)["balance"], 10350)
                self.assertEqual(w.history_table.rowCount(), 1)
                self.assertEqual(w.stats_table.rowCount(), 37)
                self.assertEqual(w.tabs.count(), 9)
            finally:
                w.bets.clear()
                w.close()
                self.app.processEvents()

    def test_generated_video_seek_and_annotations(self):
        import cv2
        import numpy as np
        from tracker.gui import Window

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "fixture.avi")
            writer = cv2.VideoWriter(
                path, cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48)
            )
            for i in range(20):
                writer.write(np.full((48, 64, 3), i * 10, dtype=np.uint8))
            writer.release()
            w = Window(Path(tmp) / "gui.sqlite")
            w.video_path = path

            def wait(predicate):
                end = time.monotonic() + 5
                while not predicate() and time.monotonic() < end:
                    self.app.processEvents()
                    time.sleep(0.01)
                self.assertTrue(predicate())

            try:
                w.busy = True
                w.open_video.emit(path)
                wait(lambda: not w.busy)
                self.assertAlmostEqual(w.duration, 2, places=1)
                w.busy = True
                w.seek_video.emit(1.0)
                wait(lambda: not w.busy)
                self.assertAlmostEqual(w.seconds, 1, places=1)
                w.annotation.setText("Repère manuel")
                w.annotate()
                self.assertEqual(w.annotations.rowCount(), 1)
            finally:
                w.close()
                self.app.processEvents()
