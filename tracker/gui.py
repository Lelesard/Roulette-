import os
import argparse
import tempfile
import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot, QMetaObject, QByteArray
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QSlider,
    QScrollArea,
)
from .domain import WHEEL, RED, sector, cents, attributes
from .storage import Store
from .video import VideoWorker
from .widgets import Racetrack, BalanceChart
from .widgets import FrameView
from .live import DesktopTools
from .capture import enable_dpi_awareness


def euros(n):
    return f"{n / 100:.2f} €".replace(".", ",")


class Window(QMainWindow, DesktopTools):
    start_capture_signal = Signal(object, int)
    stop_capture_signal = Signal()
    ocr_request = Signal(object, object, str, bool)
    analysis_request = Signal(object, object, float)

    # Concrete QObject slots are required: PySide does not register slots inherited
    # from a plain Python mixin. These bridges keep SQLite and widgets on the UI thread.
    @Slot(object, float, float)
    def capture_frame(self, frame, stamp, latency):
        DesktopTools.capture_frame(self, frame, stamp, latency)

    @Slot()
    def poll_capture(self):
        DesktopTools.poll_capture(self)

    @Slot(str)
    def capture_error(self, message):
        DesktopTools.capture_error(self, message)

    @Slot(object, object)
    def ocr_ready(self, context, snapshot):
        DesktopTools.ocr_ready(self, context, snapshot)

    @Slot(object, str)
    def ocr_error(self, context, message):
        DesktopTools.ocr_error(self, context, message)

    @Slot(object, object)
    def analysis_ready(self, context, track):
        DesktopTools.analysis_ready(self, context, track)

    @Slot(object, str)
    def analysis_error(self, context, message):
        DesktopTools.analysis_error(self, context, message)

    open_video = Signal(str)
    seek_video = Signal(float)
    read_video = Signal()

    def __init__(self, db_path=None):
        super().__init__()
        self._closing = False
        self.setWindowTitle("Tracker Roulette — calibrage automatique v4")
        self.resize(1300, 850)
        if db_path is None:
            root = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
                / "RouletteTracker"
            )
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "tracker.sqlite3"
        self.capture_log_path = Path(db_path).parent / "capture-diagnostic.log"
        self.capture_log = logging.getLogger(f"roulette.capture.{id(self)}")
        self.capture_log.setLevel(logging.INFO)
        self.capture_log.propagate = False
        self.capture_log_handler = RotatingFileHandler(
            self.capture_log_path, maxBytes=2_000_000, backupCount=1, encoding="utf-8"
        )
        self.capture_log_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(threadName)s %(message)s"
        ))
        self.capture_log.addHandler(self.capture_log_handler)
        self.capture_log.info("version=capture-corrected-v3 source=%s", Path(__file__).resolve())
        self.capture_started_at = None
        self.capture_stale = False
        self.store = Store(db_path)
        self.bets = []
        self.offset = 0
        self.video_path = ""
        self.seconds = 0.0
        self.duration = 0.0
        self.fps = 30.0
        self.busy = False
        if not self.store.sessions():
            self.store.create_session("Session 1", "Table manuelle")
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        top = QHBoxLayout()
        layout.addLayout(top)
        self.sessions = QComboBox()
        top.addWidget(QLabel("Session / table"))
        top.addWidget(self.sessions, 1)
        self.button(top, "Nouvelle session", self.new_session)
        self.balance = QLabel()
        top.addWidget(self.balance)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.manual = self.page("Racetrack")
        self.make_manual()
        self.history = self.page("Historique")
        self.make_history()
        self.finance = self.page("Bankroll")
        self.make_finance()
        self.stats = self.page("Statistiques")
        self.make_stats()
        self.video = self.page("Vidéos et tests")
        self.make_video()
        self.settings_page = self.page("Paramètres")
        self.diagnostic_page = self.page("Diagnostics")
        info = self.settings_page
        self.diagnostic_page.addWidget(
            QLabel(
                "Application locale • aucune connexion au casino • aucune mise automatique.\nLes sélections du Racetrack sont manuelles et ne constituent pas une prédiction.\nLes fréquences historiques ne prédisent pas une roulette équilibrée.\nSQLite : "
                + str(db_path)
            )
        )
        row = QHBoxLayout()
        info.addLayout(row)
        row.addWidget(QLabel("Alerte de perte nette par session (€), 0 = désactivée"))
        self.loss_limit = QSpinBox()
        self.loss_limit.setRange(0, 1000000)
        self.loss_limit.setValue(self.store.setting("loss_limit", 0))
        row.addWidget(self.loss_limit)
        self.loss_limit.valueChanged.connect(
            lambda n: (self.store.save_setting("loss_limit", n), self.refresh())
        )
        self.diagnostics = QLabel("Prêt")
        self.diagnostic_page.addWidget(self.diagnostics)
        self.diagnostic_page.addWidget(QLabel("Version : capture corrigée v3\nJournal : " + str(self.capture_log_path)))
        log_row = QHBoxLayout()
        self.diagnostic_page.addLayout(log_row)
        self.button(log_row, "Exporter le journal de capture", self.export_capture_log)
        self.sessions.currentIndexChanged.connect(self.session_changed)
        self.load_sessions()
        self.bets = self.store.setting(f"pending_{self.sid}", [])
        self.refresh()
        self.make_desktop()
        self.refresh_desktop()
        geometry = self.store.setting("geometry")
        if geometry:
            self.restoreGeometry(QByteArray.fromHex(geometry.encode()))

    def page(self, name):
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, name)
        layout = QVBoxLayout(w)
        layout.tab_widget = scroll
        return layout

    def button(self, row, text, fn):
        b = QPushButton(text)
        b.setMinimumHeight(40)
        b.clicked.connect(lambda checked=False: self.guard(fn))
        row.addWidget(b)
        return b

    def guard(self, fn):
        try:
            return fn()
        except Exception as e:
            QMessageBox.warning(self, "Opération impossible", str(e))

    def table(self, layout, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(t)
        return t

    def fill(self, t, rows):
        t.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                t.setItem(i, j, QTableWidgetItem(str(v)))
        t.resizeColumnsToContents()

    @property
    def sid(self):
        return self.sessions.currentData()

    def load_sessions(self, selected=None):
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for s in self.store.sessions():
            self.sessions.addItem(f"{s['name']} — {s['table_name']}", s["id"])
        idx = self.sessions.findData(
            selected or self.store.setting("session", self.sessions.itemData(0))
        )
        self.sessions.setCurrentIndex(max(0, idx))
        self.sessions.blockSignals(False)

    def new_session(self):
        if self.bets:
            raise ValueError(
                "Videz ou réglez les mises en attente avant de changer de session."
            )
        name, ok = QInputDialog.getText(self, "Session", "Nom de la session")
        if not ok:
            return
        table, ok = QInputDialog.getItem(
            self,
            "Table",
            "Nom du profil / de la table",
            self.store.profile_names(),
            0,
            True,
        )
        if ok:
            self.stop_capture()
            self.load_sessions(self.store.create_session(name, table))
            self.offset = 0
            self.store.save_setting("session", self.sid)
            self.bets = []
            self.sync_profile()
            self.refresh()

    def session_changed(self):
        self.timer.stop()
        if hasattr(self, "capture_worker"):
            self.stop_capture()
        self.bets = self.store.setting(f"pending_{self.sid}", [])
        self.offset = 0
        self.store.save_setting("session", self.sid)
        if hasattr(self, "profiles"):
            self.sync_profile()
        self.refresh()

    def make_manual(self):
        self.manual.addWidget(
            QLabel(
                "Sélection manuelle : cliquez un numéro du cylindre pour centrer ses voisins."
            )
        )
        controls = QHBoxLayout()
        self.manual.addLayout(controls)
        self.zone = QComboBox()
        self.zone.addItems(["9", "15", "19"])
        self.zone.setCurrentText(self.store.setting("zone", "9"))
        controls.addWidget(QLabel("Taille de zone"))
        controls.addWidget(self.zone)
        self.center = QSpinBox()
        self.center.setRange(0, 36)
        self.center.setValue(self.store.setting("center", 0))
        controls.addWidget(QLabel("Centre"))
        controls.addWidget(self.center)
        self.zone_text = QLabel()
        self.manual.addWidget(self.zone_text)
        self.racetrack = Racetrack(self.center.setValue)
        self.manual.addWidget(self.racetrack)
        self.wheel_buttons = self.racetrack.buttons
        self.center.valueChanged.connect(self.paint_zone)
        self.zone.currentTextChanged.connect(self.paint_zone)
        row = QHBoxLayout()
        self.manual.addLayout(row)
        row.addWidget(QLabel("Valeur du jeton (€)"))
        self.chip = QComboBox()
        self.chip.setEditable(True)
        self.chip.addItems(["0,10", "0,50", "1,00"])
        self.chip.setCurrentText(self.store.setting("chip", "0,10"))
        row.addWidget(self.chip)
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 100000)
        self.quantity.setValue(self.store.setting("quantity", 1))
        row.addWidget(QLabel("Jetons par cible"))
        row.addWidget(self.quantity)
        self.center.valueChanged.connect(lambda n: self.store.save_setting("center", n))
        self.zone.currentTextChanged.connect(
            lambda n: self.store.save_setting("zone", n)
        )
        self.quantity.valueChanged.connect(
            lambda n: self.store.save_setting("quantity", n)
        )
        self.chip.currentTextChanged.connect(
            lambda text: self.store.save_setting("chip", text)
        )
        self.chip.currentTextChanged.connect(lambda _: self.refresh_desktop())
        self.button(
            row,
            "Miser sur le centre",
            lambda: self.add_bet("plein", str(self.center.value())),
        )
        self.button(row, "Miser sur toute la zone", self.bet_zone)
        row = QHBoxLayout()
        self.manual.addLayout(row)
        self.kind = QComboBox()
        self.kind.addItems(["couleur", "parité", "hauteur", "douzaine", "colonne"])
        row.addWidget(self.kind)
        self.target = QComboBox()
        row.addWidget(self.target)
        self.kind.currentTextChanged.connect(self.targets)
        self.targets()
        self.button(
            row,
            "Ajouter cette mise",
            lambda: self.add_bet(self.kind.currentText(), self.target.currentText()),
        )
        self.pending = QLabel()
        self.pending.setWordWrap(True)
        self.manual.addWidget(self.pending)
        row = QHBoxLayout()
        self.manual.addLayout(row)
        self.button(row, "Vider les mises en attente", self.clear_bets)
        row.addWidget(QLabel("Résultat observé"))
        self.result = QSpinBox()
        self.result.setRange(0, 36)
        row.addWidget(self.result)
        self.button(row, "Enregistrer et régler le tour", self.record)
        self.manual.addWidget(
            QLabel(
                "Sans mise déclarée, le résultat est enregistré sans gain ni perte. Les mises sont virtuelles et ne sont envoyées nulle part."
            )
        )
        self.manual.addStretch()

    def targets(self):
        self.target.clear()
        self.target.addItems(
            {
                "couleur": ["rouge", "noir"],
                "parité": ["pair", "impair"],
                "hauteur": ["manque", "passe"],
                "douzaine": ["1", "2", "3"],
                "colonne": ["1", "2", "3"],
            }[self.kind.currentText()]
        )

    def paint_zone(self):
        selected = sector(self.center.value(), int(self.zone.currentText()))
        self.zone_text.setText("Zone manuelle : " + ", ".join(map(str, selected)))
        latest = self.store.spins(self.sid, 1) if self.sid else []
        last = latest[0]["number"] if latest else None
        declared = {int(b["target"]) for b in self.bets if b["kind"] == "plein"}
        for n, b in self.wheel_buttons.items():
            color = "#12613d" if n == 0 else "#8d2634" if n in RED else "#272d39"
            border = "3px solid #39c9e7" if n in selected else "1px solid #566074"
            b.setText(
                str(n) + (" ●" if n == last else "") + (" ◆" if n in declared else "")
            )
            b.setToolTip("● dernier résultat ; ◆ mise déclarée ; cyan : zone manuelle")
            b.setStyleSheet(
                f"background:{color}; border:{border}; border-radius:5px; color:white; padding:0; font-size:13px;"
            )

    def add_bet(self, kind, target):
        amount = cents(self.chip.currentText())
        self.store.save_setting("chip", self.chip.currentText())
        self.bets.append(
            {"kind": kind, "target": target, "stake": amount * self.quantity.value()}
        )
        self.refresh()

    def bet_zone(self):
        amount = cents(self.chip.currentText()) * self.quantity.value()
        self.bets.extend(
            {"kind": "plein", "target": str(n), "stake": amount}
            for n in sector(self.center.value(), int(self.zone.currentText()))
        )
        self.refresh()

    def clear_bets(self):
        self.bets.clear()
        self.refresh()

    def record(self):
        self.store.add_spin(
            self.sid, self.result.value(), self.bets, settle_pending=True
        )
        self.bets.clear()
        self.offset = 0
        self.refresh()

    def make_history(self):
        row = QHBoxLayout()
        self.history.addLayout(row)
        self.button(row, "Précédents", lambda: self.page_history(-100))
        self.button(row, "Suivants", lambda: self.page_history(100))
        self.page_label = QLabel()
        row.addWidget(self.page_label)
        self.button(row, "Corriger la sélection", self.correct)
        self.button(row, "Supprimer la sélection", self.delete)
        self.button(row, "Importer CSV / JSON", self.import_history)
        self.button(row, "Exporter CSV / JSON", self.export_history)
        self.history_table = self.table(
            self.history,
            [
                "ID",
                "Numéro",
                "Date UTC",
                "Couleur",
                "Parité",
                "Hauteur",
                "Douzaine",
                "Colonne",
            ],
        )

    def page_history(self, delta):
        self.offset = max(0, self.offset + delta)
        self.refresh()

    def selected_id(self, t):
        if t.currentRow() < 0:
            raise ValueError("Sélectionnez une ligne.")
        return int(t.item(t.currentRow(), 0).text())

    def correct(self):
        spin = self.selected_id(self.history_table)
        n, ok = QInputDialog.getInt(
            self, "Correction", "Nouveau résultat (recalcul du tour déclaré)", 0, 0, 36
        )
        if ok:
            self.store.edit_spin(spin, n)
            self.refresh()

    def delete(self):
        spin = self.selected_id(self.history_table)
        if (
            QMessageBox.question(
                self,
                "Suppression",
                "Supprimer ce résultat et annuler son règlement financier ?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.store.edit_spin(spin)
            self.refresh()

    def import_history(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer des résultats", "", "Résultats (*.csv *.json)"
        )
        if path:
            self.store.import_file(self.sid, path)
            self.offset = 0
            self.refresh()

    def export_history(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les résultats",
            "resultats.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if path:
            self.store.export(self.sid, path)

    def make_finance(self):
        row = QHBoxLayout()
        self.finance.addLayout(row)
        self.cash_kind = QComboBox()
        self.cash_kind.addItems(["initial", "dépôt", "retrait", "ajustement"])
        row.addWidget(self.cash_kind)
        self.cash_amount = QLineEdit()
        self.cash_amount.setPlaceholderText(
            "Montant € (signe autorisé pour ajustement)"
        )
        row.addWidget(self.cash_amount)
        self.cash_note = QLineEdit()
        self.cash_note.setPlaceholderText("Motif")
        row.addWidget(self.cash_note)
        self.button(row, "Enregistrer", self.cash)
        self.button(row, "Annuler la sélection", self.void)
        self.chart = BalanceChart()
        self.finance.addWidget(self.chart)
        self.finance_summary = QLabel()
        self.finance_summary.setWordWrap(True)
        self.finance.addWidget(self.finance_summary)
        self.ledger = self.table(
            self.finance,
            [
                "ID",
                "Date UTC",
                "Type",
                "Variation",
                "Engagé",
                "Retour brut",
                "Solde",
                "État",
                "Détail",
            ],
        )

    def cash(self):
        text = self.cash_amount.text().strip()
        sign = -1 if text.startswith("-") else 1
        if sign < 0 and self.cash_kind.currentText() != "ajustement":
            raise ValueError("Seul un ajustement accepte un signe négatif.")
        self.store.cash(
            self.sid,
            self.cash_kind.currentText(),
            sign * cents(text.lstrip("-")),
            self.cash_note.text(),
        )
        self.refresh()

    def void(self):
        op = self.selected_id(self.ledger)
        if (
            QMessageBox.question(
                self, "Annulation", "Annuler cette opération en conservant sa trace ?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.store.void(op)
            self.refresh()

    def make_stats(self):
        self.stats_summary = QLabel()
        self.stats.addWidget(self.stats_summary)
        self.stats_table = self.table(
            self.stats, ["Numéro", "Effectif", "Fréquence", "Histogramme"]
        )
        self.stats.addWidget(
            QLabel(
                "Références théoriques des zones : 9/37 = 24,32 % ; 15/37 = 40,54 % ; 19/37 = 51,35 %.\nAucune estimation prédictive."
            )
        )

    def make_video(self):
        row = QHBoxLayout()
        self.video.addLayout(row)
        self.button(row, "Ouvrir une vidéo", self.choose_video)
        self.play = self.button(row, "Lecture / pause", self.toggle_video)
        self.button(row, "Image suivante", self.step_video)
        self.speed = QComboBox()
        self.speed.addItems(["0.25", "0.5", "1", "2"])
        self.speed.setCurrentText("1")
        row.addWidget(QLabel("Vitesse"))
        row.addWidget(self.speed)
        self.video_image = FrameView()
        self.video.addWidget(self.video_image, 1)
        self.video_image.selected.connect(self.save_roi)
        self.capture_controls(self.video, self.video_image)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.video.addWidget(self.timeline)
        self.timeline.sliderReleased.connect(self.seek)
        self.video_status = QLabel("Aucun fichier")
        self.video.addWidget(self.video_status)
        row = QHBoxLayout()
        self.video.addLayout(row)
        self.annotation = QLineEdit()
        self.annotation.setPlaceholderText(
            "Annotation à cet instant (caméra, bille visible, résultat…)"
        )
        row.addWidget(self.annotation)
        self.button(row, "Enregistrer l’annotation", self.annotate)
        self.annotations = self.table(self.video, ["Temps (s)", "Note"])
        self.thread = QThread(self)
        self.worker = VideoWorker()
        self.worker.moveToThread(self.thread)
        self.thread.finished.connect(self.worker.deleteLater)
        self.open_video.connect(self.worker.open)
        self.seek_video.connect(self.worker.seek)
        self.read_video.connect(self.worker.read)
        self.worker.ended.connect(self.on_end)
        self.worker.frame.connect(self.on_frame)
        self.worker.opened.connect(self.on_opened)
        self.worker.error.connect(self.video_error)
        self.thread.start()
        self.worker.raw_frame.connect(
            self.on_raw_frame, Qt.ConnectionType.QueuedConnection
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.speed.currentTextChanged.connect(self.set_speed)

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Vidéo enregistrée", "", "Vidéos (*.mp4 *.avi *.mov *.mkv)"
        )
        if path:
            self.stop_capture()
            self.reset_ocr_proposal()
            self.timer.stop()
            self.busy = True
            self.video_path = path
            self.open_video.emit(path)
            self.refresh_annotations()

    def toggle_video(self):
        if not self.video_path or self.busy:
            return
        if self.capture_active:
            self.stop_capture()
        if self.timer.isActive():
            self.timer.stop()
        else:
            self.set_speed()
            self.timer.start()

    def set_speed(self):
        self.timer.setInterval(
            max(1, round(1000 / (self.fps * float(self.speed.currentText()))))
        )

    def tick(self):
        if self.seconds >= max(0, self.duration - 1 / self.fps):
            self.timer.stop()
            return
        if not self.busy:
            self.busy = True
            self.read_video.emit()

    def step_video(self):
        self.timer.stop()
        self.tick()

    def seek(self):
        if not self.video_path or self.busy:
            return
        self.ocr_enabled.setChecked(False)
        self.ocr_auto.setChecked(False)
        self.reset_ocr_proposal()
        self.timer.stop()
        self.busy = True
        self.seek_video.emit(self.timeline.value() / 1000)

    @Slot(float, float)
    def on_opened(self, duration, fps):
        self.duration = duration
        self.fps = fps
        self.timeline.setRange(0, max(0, round((duration - 1 / fps) * 1000)))
        self.set_speed()

    @Slot(object, float, str)
    def on_frame(self, image, seconds, diagnostic):
        self.busy = False
        self.seconds = seconds
        self.timeline.setValue(round(seconds * 1000))
        self.video_image.set_image(image)
        self.video_status.setText(
            f"{Path(self.video_path).name} • {seconds:.3f} / {self.duration:.3f} s • {self.fps:.2f} FPS source • {diagnostic}"
        )

    @Slot(object, float)
    def on_raw_frame(self, frame, seconds):
        self.receive_source(frame, seconds, "video")

    @Slot()
    def on_end(self):
        self.busy = False
        self.timer.stop()

    @Slot(str)
    def video_error(self, message):
        self.busy = False
        self.timer.stop()
        self.video_path = ""
        self.video_status.setText(message)

    def annotate(self):
        if not self.video_path:
            raise ValueError("Ouvrez une vidéo.")
        self.store.annotate(self.video_path, self.seconds, self.annotation.text())
        self.annotation.clear()
        self.refresh_annotations()

    def refresh_annotations(self):
        self.fill(
            self.annotations,
            self.store.db.execute(
                "SELECT seconds,note FROM annotations WHERE video=? ORDER BY seconds,id",
                (self.video_path,),
            ).fetchall(),
        )

    def refresh(self):
        if self.sid is None:
            return
        self.store.save_setting(f"pending_{self.sid}", self.bets)
        self.paint_zone()
        s = self.store.summary(self.sid)
        all_s = self.store.summary()
        self.balance.setText("Bankroll : " + euros(s["balance"]))
        self.pending.setText(
            "Mises en attente : "
            + euros(sum(b["stake"] for b in self.bets))
            + " — "
            + " ; ".join(
                f"{b['kind']} {b['target']} : {euros(b['stake'])}" for b in self.bets
            )
        )
        spins = self.store.spins(self.sid, 100, self.offset)
        self.fill(
            self.history_table,
            [
                (r["id"], r["number"], r["created"], *attributes(r["number"]).values())
                for r in spins
            ],
        )
        self.page_label.setText(
            f"À partir de {self.offset + 1} • {len(spins)} résultat(s)"
        )
        balance = 0
        rows = []
        curve = [0]
        for op in self.store.operations(self.sid):
            if not op["voided"]:
                balance += op["amount"]
            curve.append(balance)
            rows.append(
                (
                    op["id"],
                    op["created"],
                    op["kind"],
                    euros(op["amount"]),
                    euros(op["stake"]),
                    euros(op["gross"]),
                    euros(balance),
                    "annulé" if op["voided"] else "actif",
                    op["note"],
                )
            )
        self.fill(self.ledger, rows)
        self.chart.set_values(curve)
        self.finance_summary.setText(
            f"Session — engagé : {euros(s['stake'])} • retours bruts : {euros(s['gross'])} • résultat net : {euros(s['net'])} • ROI : {s['roi']:.2f} %\nTours bénéficiaires : +{euros(s['profits'])} • pertes nettes des tours déficitaires : {euros(s['losses'])}\nCumul — bankroll : {euros(all_s['balance'])} • engagé : {euros(all_s['stake'])} • retours : {euros(all_s['gross'])} • net : {euros(all_s['net'])} • ROI : {all_s['roi']:.2f} %"
        )
        counts = self.store.counts(self.sid)
        total = sum(counts.values())
        current, longest = self.store.streaks(self.sid)
        self.stats_summary.setText(
            f"{total} résultats • historique indépendant par session et table\n"
            + " • ".join(
                f"{k} : {v[0]} × {v[1]} (max {longest[k]})" for k, v in current.items()
            )
        )
        self.stats_summary.setWordWrap(True)
        maximum = max(counts.values(), default=1)
        self.fill(
            self.stats_table,
            [
                (
                    n,
                    counts.get(n, 0),
                    f"{100 * counts.get(n, 0) / total:.2f} %" if total else "—",
                    "█" * round(30 * counts.get(n, 0) / maximum),
                )
                for n in WHEEL
            ],
        )
        limit = self.loss_limit.value()
        self.diagnostics.setText(
            "Limite de perte atteinte"
            if limit and s["net"] <= -limit * 100
            else "SQLite actif • OCR et candidat bille expérimentaux • aucune prédiction validée"
        )
        self.balance.setStyleSheet(
            "color:#ff7a7a" if limit and s["net"] <= -limit * 100 else "color:#60dfba"
        )
        self.refresh_desktop()

    def export_capture_log(self):
        target, _ = QFileDialog.getSaveFileName(self, "Exporter le journal de capture", "capture-diagnostic.txt", "Texte (*.txt)")
        if target:
            self.capture_log_handler.flush()
            if Path(target).resolve() != self.capture_log_path.resolve():
                shutil.copyfile(self.capture_log_path, target)

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.store.save_setting(f"pending_{self.sid}", self.bets)
        self.store.save_setting("geometry", self.saveGeometry().toHex().data().decode())
        self.shutdown_desktop()
        self.timer.stop()
        QMetaObject.invokeMethod(
            self.worker, "close", Qt.ConnectionType.BlockingQueuedConnection
        )
        self.thread.quit()
        self.thread.wait()
        self.store.close()
        self.capture_log.removeHandler(self.capture_log_handler)
        self.capture_log_handler.close()
        event.accept()


STYLE = "QWidget { background:#171d29; color:#e9edf7; font-size:14px; } QPushButton,QComboBox,QLineEdit,QSpinBox { padding:7px; border:1px solid #566074; border-radius:5px; min-height:26px; } QTabBar::tab { padding:12px 10px; } QTabBar::tab:selected { background:#30435c; color:#65dfcf; } QTableWidget { alternate-background-color:#252c3a; } QHeaderView::section { background:#293449; padding:5px; } QSlider::groove:horizontal { height:12px; background:#34435a; } QSlider::handle:horizontal { background:#60dfba; width:26px; margin:-6px 0; border-radius:8px; }"


def main():
    parser = argparse.ArgumentParser(description="Tracker Roulette local")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Ouvrir et fermer avec une base temporaire, sans modifier les données utilisateur",
    )
    args = parser.parse_args()
    enable_dpi_awareness()
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    scratch = (
        tempfile.TemporaryDirectory(prefix="roulette-smoke-")
        if args.smoke_test
        else None
    )
    window = Window(Path(scratch.name) / "smoke.sqlite" if scratch else None)
    window.show()
    if scratch:
        QTimer.singleShot(800, window.close)
    result = app.exec()
    if scratch:
        scratch.cleanup()
    return result
