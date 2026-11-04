"""Desktop tools for the existing manual accounting UI."""

import time
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal, Slot, QMetaObject
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QCheckBox,
    QInputDialog,
    QFileDialog,
    QMessageBox,
)

from .capture import (
    CaptureWorker,
    brave_windows,
    crop_roi,
    detect_wheel_roi,
    to_image,
)
from .ocr import OCRWorker, reconcile
from .experimental import CandidateTracker
from .scene import SceneObserver
from .widgets import FrameView


class AnalysisWorker(QObject):
    ready = Signal(object, object)
    error = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.tracker = CandidateTracker()
        self.context = None

    @Slot(object, object, float)
    def analyze(self, context, frame, seconds):
        try:
            if context != self.context:
                self.tracker.reset()
                self.context = context
            self.ready.emit(context, self.tracker.analyze(frame, seconds))
        except Exception as exc:
            self.error.emit(context, str(exc))


class SceneWorker(QObject):
    ready = Signal(object, object)
    error = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.observer = SceneObserver()
        self.context = None

    @Slot(object, object, float)
    def analyze(self, context, frame, seconds):
        try:
            if context[:4] != self.context:
                self.observer.reset()
                self.context = context[:4]
            self.ready.emit(context, self.observer.analyze(frame, seconds))
        except Exception as exc:
            self.error.emit(context, str(exc))


class DesktopTools:
    """Mixin: signals are declared on Window, a QObject subclass."""

    def make_desktop(self):
        self.capture_active = False
        self.source_epoch = 0
        self.latest_frame = None
        self.latest_kind = None
        self.last_capture_stamp = None
        self.last_ocr = 0.0
        self.ocr_busy = False
        self.ocr_candidate = None
        self.ocr_stable = 0
        self.ocr_proposal = None
        self.analysis_busy = False
        self.last_analysis = 0.0
        self.scene_busy = False
        self.last_scene = 0.0
        self.camera_epoch = 0
        self.dynamic_wheel_roi = None
        for name in ("Deutsches Roulette", "VIP Roulette", "Table manuelle"):
            if name not in self.store.profile_names():
                self.store.save_profile(name, {})
        self.direct = self.page("Direct")
        self.direct.addWidget(
            QLabel(
                "Capture de l’écran visible uniquement. Gardez Brave au premier plan, sans autre fenêtre devant la roulette."
            )
        )
        row = QHBoxLayout()
        self.direct.addLayout(row)
        self.brave_list = QComboBox()
        row.addWidget(self.brave_list, 1)
        self.button(row, "Actualiser Brave", self.list_brave)
        self.capture_rate = QSpinBox()
        self.capture_rate.setRange(1, 30)
        self.capture_rate.setValue(self.store.setting("capture_fps", 10))
        row.addWidget(QLabel("FPS cible"))
        row.addWidget(self.capture_rate)
        self.button(row, "Démarrer", self.start_capture)
        self.button(row, "Arrêter", self.stop_capture)
        self.automatic_scene = QCheckBox("Analyse automatique")
        self.automatic_scene.setChecked(self.store.setting("automatic_scene", True))
        self.automatic_scene.toggled.connect(self.toggle_automatic_scene)
        row.addWidget(self.automatic_scene)
        self.live_image = FrameView()
        self.direct.addWidget(self.live_image, 1)
        self.live_image.selected.connect(self.save_roi)
        self.capture_controls(self.direct, self.live_image)
        self.capture_status = QLabel(
            "Capture arrêtée • bille : non mesurée • rotor : non mesuré"
        )
        self.capture_status.setWordWrap(True)
        self.direct.addWidget(self.capture_status)
        self.scene_status = QLabel(
            "Scène : en attente • le cadre dynamique exige trois observations concordantes"
        )
        self.scene_status.setWordWrap(True)
        self.direct.addWidget(self.scene_status)
        self.estimate_status = QLabel("Aucune estimation fiable")
        self.estimate_status.setStyleSheet("font-size:22px;color:#f9bf66;")
        self.direct.addWidget(self.estimate_status)
        self.direct_summary = QLabel()
        self.direct_summary.setWordWrap(True)
        self.direct.addWidget(self.direct_summary)
        row = QHBoxLayout()
        self.direct.addLayout(row)
        self.button(
            row,
            "Saisir les mises / Racetrack",
            lambda: self.tabs.setCurrentWidget(self.manual.tab_widget),
        )
        self.button(
            row,
            "Historique",
            lambda: self.tabs.setCurrentWidget(self.history.tab_widget),
        )
        self.button(
            row, "Bankroll", lambda: self.tabs.setCurrentWidget(self.finance.tab_widget)
        )
        self.make_profiles()
        self.make_ocr_settings()
        self.capture_thread = QThread(self)
        self.capture_worker = CaptureWorker()
        self.capture_worker.log = self.capture_log
        self.capture_worker.moveToThread(self.capture_thread)
        self.capture_thread.finished.connect(self.capture_worker.deleteLater)
        self.start_capture_signal.connect(self.capture_worker.start)
        self.stop_capture_signal.connect(self.capture_worker.stop)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(16)
        self.preview_timer.timeout.connect(self.poll_capture)
        self.preview_timer.start()
        self.capture_worker.error.connect(
            self.capture_error, Qt.ConnectionType.QueuedConnection
        )
        self.capture_thread.start()
        self.ocr_thread = QThread(self)
        self.ocr_worker = OCRWorker()
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_request.connect(self.ocr_worker.read)
        self.ocr_worker.ready.connect(
            self.ocr_ready, Qt.ConnectionType.QueuedConnection
        )
        self.ocr_worker.error.connect(
            self.ocr_error, Qt.ConnectionType.QueuedConnection
        )
        self.ocr_thread.start()
        self.analysis_thread = QThread(self)
        self.analysis_worker = AnalysisWorker()
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_request.connect(self.analysis_worker.analyze)
        self.analysis_worker.ready.connect(
            self.analysis_ready, Qt.ConnectionType.QueuedConnection
        )
        self.analysis_worker.error.connect(
            self.analysis_error, Qt.ConnectionType.QueuedConnection
        )
        self.analysis_thread.start()
        self.scene_thread = QThread(self)
        self.scene_worker = SceneWorker()
        self.scene_worker.moveToThread(self.scene_thread)
        self.scene_thread.finished.connect(self.scene_worker.deleteLater)
        self.scene_request.connect(self.scene_worker.analyze)
        self.scene_worker.ready.connect(
            self.scene_ready, Qt.ConnectionType.QueuedConnection
        )
        self.scene_worker.error.connect(
            self.scene_error, Qt.ConnectionType.QueuedConnection
        )
        self.scene_thread.start()
        # Reorder the nine functional pages, retaining their existing widgets.
        pages = {
            self.tabs.tabText(i): self.tabs.widget(i) for i in range(self.tabs.count())
        }
        self.tabs.clear()
        for name in (
            "Direct",
            "Racetrack",
            "Historique",
            "Bankroll",
            "Statistiques",
            "Vidéos et tests",
            "Tables et profils",
            "Paramètres",
            "Diagnostics",
        ):
            self.tabs.addTab(pages[name], name)
        self.sync_profile()

    def toggle_automatic_scene(self, enabled):
        self.store.save_setting("automatic_scene", enabled)
        self.scene_busy = False
        self.camera_epoch += 1
        self.dynamic_wheel_roi = None
        self.clear_dynamic_scene()
        self.scene_status.setText(
            "Scène : recherche automatique active"
            if enabled
            else "Scène : analyse automatique désactivée"
        )

    def clear_dynamic_scene(self):
        if not hasattr(self, "live_image"):
            return
        for view in (self.live_image, self.video_image):
            view.regions.pop("wheel_dynamic", None)
            view.regions.pop("wheel_candidate", None)
            view.point = None
            view.update()

    def capture_controls(self, layout, view):
        row = QHBoxLayout()
        layout.addLayout(row)
        self.button(
            row, "Calibrer le cylindre", lambda: self.begin_roi(view, "wheel_roi")
        )
        self.button(
            row, "Détecter le cylindre", lambda: self.auto_calibrate_wheel(view)
        )
        self.button(
            row, "Calibrer les résultats", lambda: self.begin_roi(view, "results_roi")
        )
        self.button(row, "Effacer le calibrage", self.clear_calibration)

    def active_table(self):
        row = self.store.db.execute(
            "SELECT table_name FROM sessions WHERE id=?", (self.sid,)
        ).fetchone()
        return row[0] if row else "Table manuelle"

    def sync_profile(self):
        name = self.active_table()
        if name not in self.store.profile_names():
            self.store.save_profile(name, {})
        if not hasattr(self, "profiles"):
            return
        self.profiles.blockSignals(True)
        self.profiles.clear()
        self.profiles.addItems(self.store.profile_names())
        self.profiles.setCurrentText(name)
        self.profiles.blockSignals(False)
        self.show_profile()
        regions = {
            k: v
            for k, v in self.store.profile(name).items()
            if k in ("wheel_roi", "results_roi")
        }
        for view in (self.live_image, self.video_image):
            view.regions = regions
            view.point = None
            view.update()
        self.newest_left.blockSignals(True)
        self.newest_left.setChecked(self.store.profile(name).get("newest_left", True))
        self.newest_left.blockSignals(False)
        self.ocr_proposal = None
        self.ocr_candidate = None
        self.ocr_stable = 0
        self.ocr_review.setText("Aucun résultat OCR à valider. Profil actif : " + name)

    def make_profiles(self):
        page = self.page("Tables et profils")
        row = QHBoxLayout()
        page.addLayout(row)
        self.profiles = QComboBox()
        row.addWidget(self.profiles)
        self.profiles.currentTextChanged.connect(self.show_profile)
        self.button(row, "Créer un profil", self.create_profile)
        self.profile_detail = QLabel()
        self.profile_detail.setWordWrap(True)
        page.addWidget(self.profile_detail)
        self.profile_note = QLineEdit()
        self.profile_note.setPlaceholderText("Notes de table / caméra")
        page.addWidget(self.profile_note)
        self.button(page, "Sauvegarder la note", self.save_profile_note)
        page.addWidget(
            QLabel(
                "Chaque session conserve sa table. Créez une nouvelle session pour changer de table.\nLe calibrage utilise les coordonnées relatives à l’image et doit être refait après un zoom,\nun changement de disposition ou une caméra différente.\nPour le suivi expérimental, encadrez précisément l’ellipse du cylindre, sans le panneau de résultats."
            )
        )
        page.addStretch()

    def show_profile(self):
        name = self.profiles.currentText()
        config = self.store.profile(name)
        self.profile_detail.setText(
            "Profil consulté : "
            + name
            + "\n"
            + str({k: v for k, v in config.items() if k != "note"})
            + "\nProfil actif de la session : "
            + self.active_table()
        )
        self.profile_note.setText(config.get("note", ""))

    def create_profile(self):
        name, ok = QInputDialog.getText(self, "Nouveau profil", "Nom de la table")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.store.profile_names():
            raise ValueError("Ce profil existe déjà.")
        self.store.save_profile(name, {})
        self.profiles.addItem(name)
        self.profiles.setCurrentText(name)

    def save_profile_note(self):
        name = self.profiles.currentText()
        config = self.store.profile(name)
        config["note"] = self.profile_note.text()
        self.store.save_profile(name, config)

    def begin_roi(self, view, mode):
        if view.image is None:
            raise ValueError("Affichez une image avant de calibrer.")
        view.mode = mode
        view.setCursor(Qt.CursorShape.CrossCursor)
        view.update()

    def auto_calibrate_wheel(self, view):
        frame = self.latest_frame
        if frame is None or view.image is None:
            raise ValueError("Affichez une image avant de détecter le cylindre.")
        roi, confidence = detect_wheel_roi(frame)
        previous = dict(view.regions)
        view.regions["wheel_candidate"] = roi
        view.update()
        answer = QMessageBox.question(
            self,
            "Cylindre détecté",
            "Le cadre vert entoure-t-il toute la roue ?\n"
            f"Score géométrique : {confidence * 100:.0f} %",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        view.regions = previous
        if answer != QMessageBox.StandardButton.Yes:
            view.update()
            self.capture_status.setText(
                "Proposition refusée • calibrez manuellement ou attendez une autre caméra."
            )
            return
        self.save_roi(("wheel_roi", roi))
        self.capture_status.setText(
            f"Cylindre calibré automatiquement • score géométrique {confidence * 100:.0f} %"
        )

    def save_roi(self, data):
        mode, roi = data
        name = self.active_table()
        config = self.store.profile(name)
        config[mode] = roi
        self.store.save_profile(name, config)
        self.source_epoch += 1
        self.sync_profile()

    def clear_calibration(self):
        name = self.active_table()
        config = self.store.profile(name)
        for key in ("wheel_roi", "results_roi"):
            config.pop(key, None)
        self.store.save_profile(name, config)
        self.source_epoch += 1
        self.sync_profile()

    def list_brave(self):
        windows = brave_windows()
        self.brave_list.clear()
        for w in windows:
            self.brave_list.addItem(w.title, w.handle)
        if not windows:
            self.capture_status.setText(
                "Aucune fenêtre Brave visible. Ouvrez Brave puis actualisez."
            )

    def start_capture(self):
        if self.brave_list.currentData() is None:
            self.list_brave()
        handle = self.brave_list.currentData()
        if handle is None:
            return
        self.timer.stop()
        self.source_epoch += 1
        self.camera_epoch += 1
        self.dynamic_wheel_roi = None
        self.clear_dynamic_scene()
        self.capture_active = True
        self.latest_frame = None
        self.store.save_setting("capture_fps", self.capture_rate.value())
        self.last_capture_stamp = None
        self.capture_count = 0
        self.capture_started_at = time.monotonic()
        self.capture_stale = False
        self.capture_log.info("ui.start")
        self.start_capture_signal.emit(handle, self.capture_rate.value())
        self.capture_status.setText("Démarrage de la capture visible…")
        self.scene_status.setText("Scène : recherche de la roue et de la caméra…")

    def stop_capture(self):
        self.capture_log.info("ui.stop")
        self.capture_active = False
        self.source_epoch += 1
        self.camera_epoch += 1
        self.dynamic_wheel_roi = None
        self.clear_dynamic_scene()
        self.latest_frame = None
        self.stop_capture_signal.emit()
        self.capture_status.setText("Capture arrêtée • Aucune estimation fiable")
        self.scene_status.setText("Scène : analyse arrêtée")

    @Slot(str)
    def capture_error(self, message):
        self.capture_log.error("ui.capture_error %s", message)
        self.capture_active = False
        self.source_epoch += 1
        self.latest_frame = None
        self.capture_status.setText(message)

    def poll_capture(self):
        packet = self.capture_worker.take_frame()
        if not self.capture_active:
            return
        if packet is None:
            since = self.last_capture_stamp or self.capture_started_at
            if since is not None and time.monotonic() - since > 3:
                if not self.capture_stale:
                    self.capture_log.error("ui.stalled last_frame=%s", getattr(self, "capture_count", 0))
                    self.capture_stale = True
                self.capture_status.setText("Aucune nouvelle image depuis plus de 3 s. Exportez le journal dans Diagnostics.")
            return
        try:
            self.capture_log.info("ui.frame.begin")
            self.capture_frame(*packet)
            self.capture_stale = False
            self.capture_log.info("ui.frame.end image=%s", self.capture_count)
        except Exception as exc:
            self.capture_log.exception("ui.preview_failure")
            self.stop_capture()
            self.capture_status.setText("Erreur d’aperçu : " + str(exc))

    @Slot(object, float, float)
    def capture_frame(self, frame, stamp, latency):
        if not self.capture_active:
            return
        self.live_image.set_image(to_image(frame))
        fps = (
            1 / (stamp - self.last_capture_stamp)
            if self.last_capture_stamp and stamp > self.last_capture_stamp
            else 0
        )
        self.last_capture_stamp = stamp
        self.capture_count = getattr(self, "capture_count", 0) + 1
        self.capture_status.setText(
            f"Image {self.capture_count} • Capture {frame.shape[1]} × {frame.shape[0]} • {fps:.1f} FPS • capture {latency:.1f} ms • âge {max(0, time.monotonic() - stamp) * 1000:.1f} ms • bille / rotor non validés"
        )
        self.receive_source(frame, stamp, "live")

    def make_ocr_settings(self):
        self.settings_page.addWidget(
            QLabel("OCR local expérimental — moteur Tesseract externe facultatif")
        )
        self.tesseract = QLineEdit(self.store.setting("tesseract", ""))
        self.tesseract.setPlaceholderText(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe (vide : PATH)"
        )
        self.settings_page.addWidget(self.tesseract)
        self.tesseract.editingFinished.connect(
            lambda: self.store.save_setting("tesseract", self.tesseract.text())
        )
        self.ocr_enabled = QCheckBox(
            "Analyser le panneau de résultats (région calibrée obligatoire)"
        )
        self.settings_page.addWidget(self.ocr_enabled)
        self.ocr_auto = QCheckBox(
            "Ajouter automatiquement après deux lectures stables concordantes"
        )
        self.settings_page.addWidget(self.ocr_auto)
        self.newest_left = QCheckBox(
            "Le résultat le plus récent est le premier dans le sens de lecture"
        )
        self.newest_left.setChecked(True)
        self.settings_page.addWidget(self.newest_left)
        self.ocr_enabled.toggled.connect(lambda _: self.reset_ocr_proposal())
        self.newest_left.toggled.connect(self.save_ocr_direction)
        self.ocr_review = QLabel()
        self.ocr_review.setWordWrap(True)
        self.settings_page.addWidget(self.ocr_review)
        row = QHBoxLayout()
        self.settings_page.addLayout(row)
        self.button(row, "Valider les résultats OCR proposés", self.accept_ocr)
        self.button(row, "Ignorer / relire", self.reset_ocr_proposal)
        self.settings_page.addWidget(
            QLabel(
                "L’OCR n’engage et ne règle aucune mise. Vérifiez le sens de lecture avant de l’activer.\nL’ajout initial importe le panneau visible. Une répétition immobile ne crée aucun résultat.\nLes répétitions identiques indiscernables, les images illisibles et les recoupements ambigus exigent une saisie manuelle."
            )
        )
        self.experimental_enabled = QCheckBox(
            "Chercher un candidat bille lorsque la roue est stable (expérimental)"
        )
        self.settings_page.addWidget(self.experimental_enabled)
        self.track_status = QLabel(
            "Suivi désactivé • rotor non mesuré • Aucune estimation fiable"
        )
        self.track_status.setWordWrap(True)
        self.diagnostic_page.addWidget(self.track_status)
        self.settings_page.addStretch()
        self.button(
            self.diagnostic_page,
            "Sauvegarder toute la base SQLite",
            self.backup_database,
        )

    def backup_database(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarde complète",
            "roulette-sauvegarde.sqlite3",
            "SQLite (*.sqlite3)",
        )
        if not path:
            return
        source = self.store.db.execute("PRAGMA database_list").fetchone()[2]
        if Path(path).resolve() == Path(source).resolve():
            raise ValueError("Choisissez un autre fichier que la base active.")
        with sqlite3.connect(path) as target:
            self.store.db.backup(target)

    def reset_ocr_proposal(self):
        self.source_epoch += 1
        self.ocr_candidate = None
        self.ocr_stable = 0
        self.ocr_proposal = None
        self.ocr_review.setText(
            "Proposition effacée • en attente de nouvelles lectures"
        )

    def save_ocr_direction(self, value):
        config = self.store.profile(self.active_table())
        config["newest_left"] = value
        self.store.save_profile(self.active_table(), config)
        self.reset_ocr_proposal()

    def receive_source(self, frame, seconds, kind):
        if self._closing:
            return
        if kind == "video" and self.capture_active:
            return
        if self.latest_kind != kind:
            self.source_epoch += 1
            self.latest_kind = kind
            self.reset_ocr_proposal()
        self.latest_frame = frame
        config = self.store.profile(self.active_table())
        clock = time.monotonic()
        context = (
            self.source_epoch,
            self.sid,
            kind,
            self.video_path if kind == "video" else "",
            self.camera_epoch,
        )
        if (
            self.automatic_scene.isChecked()
            and not self.scene_busy
            and clock - self.last_scene >= 0.55
        ):
            self.scene_busy = True
            self.last_scene = clock
            self.scene_request.emit(context, frame.copy(), seconds)
        if (
            self.ocr_enabled.isChecked()
            and not self.ocr_busy
            and clock - self.last_ocr >= 1.5
        ):
            if "results_roi" not in config:
                self.ocr_review.setText(
                    "OCR : calibrez le panneau de résultats sur l’image."
                )
            else:
                try:
                    roi = crop_roi(frame, config["results_roi"]).copy()
                    self.ocr_busy = True
                    self.last_ocr = clock
                    self.ocr_request.emit(
                        context,
                        roi,
                        self.tesseract.text(),
                        self.newest_left.isChecked(),
                    )
                except ValueError as exc:
                    self.ocr_review.setText(str(exc))
        if (
            self.experimental_enabled.isChecked()
            and not self.analysis_busy
            and clock - self.last_analysis > 0.05
        ):
            wheel_roi = self.dynamic_wheel_roi or config.get("wheel_roi")
            if wheel_roi is None:
                self.track_status.setText(
                    "Suivi suspendu : aucune zone de roue stable."
                )
            else:
                try:
                    roi = crop_roi(frame, wheel_roi).copy()
                    self.analysis_busy = True
                    self.last_analysis = clock
                    self.analysis_request.emit(context, roi, seconds)
                except ValueError as exc:
                    self.track_status.setText(str(exc))

    def context_valid(self, context):
        return (
            not self._closing
            and context[:2] == (self.source_epoch, self.sid)
            and (len(context) < 5 or context[4] == self.camera_epoch)
        )

    def scene_context_valid(self, context):
        return (
            not self._closing
            and context[:2] == (self.source_epoch, self.sid)
            and context[2] == self.latest_kind
        )

    @Slot(object, object)
    def scene_ready(self, context, observation):
        self.scene_busy = False
        if not self.scene_context_valid(context) or not self.automatic_scene.isChecked():
            return
        if observation.camera_changed:
            self.camera_epoch += 1
            self.analysis_busy = False
            self.dynamic_wheel_roi = None
            self.clear_dynamic_scene()
            self.track_status.setText(
                "Changement de caméra : suivi réinitialisé • Aucune estimation fiable"
            )
        view = self.live_image if context[2] == "live" else self.video_image
        view.regions.pop("wheel_candidate", None)
        view.regions.pop("wheel_dynamic", None)
        if observation.wheel_roi is not None:
            self.dynamic_wheel_roi = observation.wheel_roi
            view.regions["wheel_dynamic"] = observation.wheel_roi
        elif observation.candidate_roi is not None:
            self.dynamic_wheel_roi = None
            view.regions["wheel_candidate"] = observation.candidate_roi
        else:
            self.dynamic_wheel_roi = None
        view.update()
        self.scene_status.setText("Scène : " + observation.message)

    @Slot(object, str)
    def scene_error(self, context, message):
        self.scene_busy = False
        if self.scene_context_valid(context):
            self.dynamic_wheel_roi = None
            self.clear_dynamic_scene()
            self.scene_status.setText("Analyse de scène interrompue : " + message)

    @Slot(object, object)
    def ocr_ready(self, context, snapshot):
        self.ocr_busy = False
        if not self.context_valid(context) or not self.ocr_enabled.isChecked():
            return
        if snapshot == self.ocr_candidate:
            self.ocr_stable += 1
        else:
            self.ocr_candidate = snapshot
            self.ocr_stable = 1
        if self.ocr_stable < 2:
            self.ocr_review.setText(
                "OCR : première lecture "
                + ", ".join(map(str, snapshot))
                + " • attente de confirmation"
            )
            return
        previous = self.store.ocr_snapshot(self.sid)
        if not previous:
            previous = [r["number"] for r in self.store.spins(self.sid, 100)]
        prefix = reconcile(previous, snapshot)
        if prefix is None:
            self.ocr_review.setText(
                "OCR : recoupement ambigu. Vérifiez le panneau et corrigez manuellement."
            )
            self.ocr_proposal = None
            return
        if not prefix:
            self.store.commit_ocr(self.sid, snapshot, [])
            self.ocr_review.setText("OCR : panneau inchangé • aucun ajout")
            self.ocr_proposal = None
            return
        self.ocr_proposal = (context, snapshot, prefix)
        self.ocr_review.setText(
            "Proposition (plus récent en premier) : " + ", ".join(map(str, prefix))
        )
        if self.ocr_auto.isChecked():
            self.accept_ocr()

    @Slot(object, str)
    def ocr_error(self, context, message):
        self.ocr_busy = False
        if self.context_valid(context):
            self.ocr_candidate = None
            self.ocr_stable = 0
            self.ocr_proposal = None
            self.ocr_review.setText(message)

    def accept_ocr(self):
        if not self.ocr_proposal:
            return
        context, snapshot, prefix = self.ocr_proposal
        if not self.context_valid(context):
            self.reset_ocr_proposal()
            return
        self.store.commit_ocr(self.sid, snapshot, prefix)
        self.ocr_proposal = None
        self.offset = 0
        self.refresh()
        self.ocr_review.setText(
            f"OCR : {len(prefix)} résultat(s) ajouté(s), sans règlement financier."
        )

    @Slot(object, object)
    def analysis_ready(self, context, track):
        self.analysis_busy = False
        if not self.context_valid(context):
            return
        self.track_status.setText(
            f"{track.message}\nScore de continuité : {track.confidence:.2f} • ω : {track.omega if track.omega is not None else '—'} rad/s • α : {track.alpha if track.alpha is not None else '—'} rad/s²\nRotor non mesuré • Aucune estimation fiable"
        )
        roi = self.dynamic_wheel_roi or self.store.profile(
            self.active_table()
        ).get("wheel_roi")
        view = self.live_image if context[2] == "live" else self.video_image
        if roi and track.point:
            frame = self.latest_frame
            if frame is not None:
                h, w = crop_roi(frame, roi).shape[:2]
                x, y = track.point
                view.point = (
                    roi[0] + x / w * roi[2],
                    roi[1] + y / h * roi[3],
                )
                view.update()
        else:
            view.point = None
            view.update()

    @Slot(object, str)
    def analysis_error(self, context, message):
        self.analysis_busy = False
        if self.context_valid(context):
            self.track_status.setText("Analyse interrompue : " + message)

    def refresh_desktop(self):
        if not hasattr(self, "direct_summary"):
            return
        s = self.store.summary(self.sid)
        recent = self.store.spins(self.sid, 12)
        latest = self.store.db.execute(
            "SELECT amount FROM operations WHERE session_id=? AND kind='tour' AND voided=0 ORDER BY id DESC LIMIT 1",
            (self.sid,),
        ).fetchone()
        from .gui import euros

        self.direct_summary.setText(
            "Table : "
            + self.active_table()
            + " • derniers numéros : "
            + ", ".join(str(r["number"]) for r in recent)
            + f"\nBankroll : {euros(s['balance'])} • jeton : {self.chip.currentText()} € • en attente : {euros(sum(b['stake'] for b in self.bets))}\nDernier tour déclaré : "
            + (euros(latest[0]) if latest else "aucun")
            + " • fermeture des mises : non détectée"
        )

    def shutdown_desktop(self):
        self.preview_timer.stop()
        self.capture_active = False
        self.source_epoch += 1
        QMetaObject.invokeMethod(
            self.capture_worker, "stop", Qt.ConnectionType.BlockingQueuedConnection
        )
        for thread in (
            self.capture_thread,
            self.ocr_thread,
            self.analysis_thread,
            self.scene_thread,
        ):
            thread.quit()
            thread.wait()
