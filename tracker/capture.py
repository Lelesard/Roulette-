"""Visible Windows desktop capture only. No browser injection or casino connection."""

import ctypes
import os
import time
import logging
from threading import Event, Lock, Thread, current_thread, get_ident
from ctypes import wintypes
from dataclasses import dataclass

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage


@dataclass(frozen=True)
class BraveWindow:
    handle: int
    title: str


def windows_api():
    if os.name != "nt":
        raise RuntimeError(
            "La capture Brave nécessite Windows 11. Le lecteur vidéo reste disponible."
        )
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return user, kernel


def is_brave(handle, user, kernel):
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        return False
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        return bool(
            kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size))
        ) and path.value.lower().endswith("\\brave.exe")
    finally:
        kernel.CloseHandle(process)


def brave_windows():
    user, kernel = windows_api()
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(handle, _):
        if user.IsWindowVisible(handle) and is_brave(handle, user, kernel):
            title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(handle) + 1)
            user.GetWindowTextW(handle, title, len(title))
            if title.value:
                windows.append(BraveWindow(int(handle), title.value))
        return True

    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows(visit, 0)
    return windows


def client_region(handle):
    user, kernel = windows_api()
    if (
        not is_brave(handle, user, kernel)
        or not user.IsWindowVisible(handle)
        or user.IsIconic(handle)
    ):
        raise RuntimeError(
            "Fenêtre Brave fermée, masquée ou minimisée. Capture arrêtée."
        )
    rect, origin = wintypes.RECT(), wintypes.POINT()
    if not user.GetClientRect(handle, ctypes.byref(rect)) or not user.ClientToScreen(
        handle, ctypes.byref(origin)
    ):
        raise RuntimeError("Région Brave inaccessible.")
    if rect.right < 32 or rect.bottom < 32:
        raise RuntimeError("Fenêtre trop petite.")
    return dict(left=origin.x, top=origin.y, width=rect.right, height=rect.bottom)


def enable_dpi_awareness():
    if os.name == "nt":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass  # Qt also enables per-monitor DPI awareness.


def crop_roi(frame, roi):
    if roi is None:
        return frame
    x, y, w, h = map(float, roi)
    if not (
        0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-6 and 0 < h <= 1 - y + 1e-6
    ):
        raise ValueError("Région calibrée invalide. Recalibrez le profil.")
    height, width = frame.shape[:2]
    result = frame[
        int(y * height) : min(height, round((y + h) * height)),
        int(x * width) : min(width, round((x + w) * width)),
    ]
    if min(result.shape[:2]) < 8:
        raise ValueError("Région trop petite (minimum 8 pixels).")
    return result


def to_image(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()


class CaptureWorker(QObject):
    error = Signal(str)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger("roulette.capture")
        self.screen = None
        self.handle = 0
        self._lock = Lock()
        self._latest = None
        self._thread = None
        self._cancel = Event()
        self._owner = None

    @Slot(object, int)
    def start(self, handle, fps):
        self.stop()
        if self._thread is not None and self._thread.is_alive():
            self.error.emit("La capture précédente ne répond pas encore. Fermez le Tracker avant de réessayer.")
            return
        self.handle = handle
        self._cancel = Event()
        self._thread = Thread(
            target=self._capture_loop, args=(handle, fps, self._cancel),
            name="RouletteScreenCapture", daemon=True,
        )
        self._thread.start()

    def _capture_loop(self, handle, fps, cancel):
        # Keep a live Python stack for the entire MSS lifetime. Qt callbacks can
        # run with transient Python thread states: an equal native thread ID is
        # not sufficient to preserve MSS's threading.local Windows handles.
        self._owner = get_ident()
        interval = 1 / max(1, min(30, fps))
        self.log.info("capture.start fps=%s owner=%s", fps, self._owner)
        try:
            import mss
            client_region(handle)
            self.screen = mss.mss()
            while not cancel.is_set():
                started = time.monotonic()
                self.grab()
                cancel.wait(max(0, interval - (time.monotonic() - started)))
        except Exception as exc:
            self.log.exception("capture.failure")
            self.error.emit(str(exc))
        finally:
            # Close on the same persistent Python thread, including failures.
            screen, self.screen = self.screen, None
            if screen is not None:
                try:
                    screen.close()
                except Exception as exc:
                    self.log.exception("capture.close_failure")
                    self.error.emit("Fermeture de la capture : " + str(exc))
            with self._lock:
                self._latest = None
            self.log.info("capture.stopped owner=%s", self._owner)
            self._owner = None
            self.stopped.emit()

    def grab(self):
        if get_ident() != self._owner:
            raise RuntimeError("Capture appelée hors du thread propriétaire MSS.")
        started = time.perf_counter()
        self.log.info("capture.region.begin")
        region = client_region(self.handle)
        desktop = self.screen.monitors[0]
        if (
            region["left"] < desktop["left"]
            or region["top"] < desktop["top"]
            or region["left"] + region["width"] > desktop["left"] + desktop["width"]
            or region["top"] + region["height"] > desktop["top"] + desktop["height"]
        ):
            raise RuntimeError("Gardez toute la fenêtre Brave dans les écrans visibles.")
        self.log.info("capture.grab.begin width=%s height=%s", region["width"], region["height"])
        frame = np.array(self.screen.grab(region))[:, :, :3].copy()
        self.log.info("capture.grab.end")
        packet = (frame, time.monotonic(), (time.perf_counter() - started) * 1000)
        with self._lock:
            self._latest = packet
        self.log.info("capture.published")

    @Slot()
    def stop(self):
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2)
            if thread.is_alive():
                self.log.error("capture.stop_timeout")
                self.error.emit("La capture Windows ne répond pas à l’arrêt.")
                return
        with self._lock:
            self._latest = None

    def take_frame(self):
        """Thread-safe handoff; never touches the MSS object."""
        with self._lock:
            packet, self._latest = self._latest, None
        return packet
