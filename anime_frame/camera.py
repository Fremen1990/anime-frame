"""Camera choice and capture.

On macOS the device order matches OpenCV's AVFoundation backend: video devices
first, then muxed devices. A permission failure raises and does not try another
index.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from ctypes import c_char_p, c_ulong, c_void_p, cdll

import cv2
import numpy as np

# Super Saiyan at 1280×720 held about 15 fps on this Mac. 960×540 holds above 20.
CAPTURE_SIZE = (960, 540)
FRAME_WIDTH, FRAME_HEIGHT = CAPTURE_SIZE


class CameraError(RuntimeError):
    pass


class CameraPermissionError(CameraError):
    pass


def fit_frame(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if width == FRAME_WIDTH and height == FRAME_HEIGHT:
        return frame
    return cv2.resize(frame, CAPTURE_SIZE, interpolation=cv2.INTER_LINEAR)


def ordered_names(devices: list[tuple[str, str]]) -> list[str]:
    """OpenCV sorts AVFoundation devices by uniqueID before it assigns indexes."""
    return [name for name, _unique_id in sorted(devices, key=lambda item: item[1])]


def preferred_index(names: list[str] | None) -> int:
    if not names:
        return 0
    for index, name in enumerate(names):
        lowered = name.lower()
        if "facetime" in lowered or "macbook" in lowered:
            return index
    return 0


def resolve_index(
    remembered: int | None,
    names: list[str] | None,
    remembered_name: str | None = None,
) -> int:
    """Pick a camera index.

    A remembered name wins when the device list has moved, because AVFoundation
    does not promise a stable order. A remembered index is used when that name
    is missing. Otherwise the built-in camera is preferred.
    """
    if names and remembered_name:
        for index, name in enumerate(names):
            if name == remembered_name:
                return index
    if remembered is not None and (not names or 0 <= int(remembered) < len(names)):
        return int(remembered)
    return preferred_index(names)


def host_app_name() -> str:
    """The app macOS will show in the Camera privacy pane."""
    pid = os.getpid()
    for _ in range(16):
        command = _process_command(pid)
        if "Cursor" in command:
            return "Cursor"
        base = os.path.basename(command.split()[0]) if command else ""
        if base in {"Terminal", "iTerm2"} or "Terminal.app" in command:
            return "Terminal"
        parent = _parent_pid(pid)
        if parent <= 1 or parent == pid:
            break
        pid = parent
    if os.environ.get("TERM_PROGRAM") == "Apple_Terminal":
        return "Terminal"
    return "Terminal"


def permission_message() -> str:
    app = host_app_name()
    return (
        f"Could not open the camera. If macOS denied access, allow {app} "
        "under System Settings → Privacy & Security → Camera, then run ./run again."
    )


def list_camera_names() -> list[str] | None:
    if sys.platform != "darwin":
        return None
    try:
        names = _avfoundation_names()
    except Exception:
        return None
    return names or None


def _process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return (result.stdout or "").strip()


def _parent_pid(pid: int) -> int:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "ppid="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    try:
        return int((result.stdout or "0").strip() or "0")
    except ValueError:
        return 0


def _avfoundation_names() -> list[str]:
    objc = cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]

    def selector(name: str) -> c_void_p:
        return objc.sel_registerName(name.encode())

    def message(obj, name: str, *args, restype=c_void_p, argtypes=None):
        objc.objc_msgSend.restype = restype
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p] + (argtypes or [c_void_p] * len(args))
        return objc.objc_msgSend(obj, selector(name), *args)

    def ns_string(text: str):
        objc.objc_msgSend.restype = c_void_p
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_char_p]
        factory = objc.objc_getClass(b"NSString")
        return objc.objc_msgSend(factory, selector("stringWithUTF8String:"), text.encode())

    def names_for(media: str) -> list[str]:
        devices = message(objc.objc_getClass(b"AVCaptureDevice"), "devicesWithMediaType:", ns_string(media))
        if not devices:
            return []
        count = int(message(devices, "count", restype=c_ulong, argtypes=[]))
        found = []
        for index in range(count):
            device = message(devices, "objectAtIndex:", c_ulong(index), argtypes=[c_ulong])
            label = message(device, "localizedName")
            raw = message(label, "UTF8String", restype=c_char_p, argtypes=[])
            unique = message(device, "uniqueID")
            unique_raw = message(unique, "UTF8String", restype=c_char_p, argtypes=[])
            found.append(
                (
                    raw.decode() if raw else "",
                    unique_raw.decode() if unique_raw else "",
                )
            )
        return found

    pool_class = objc.objc_getClass(b"NSAutoreleasePool")
    pool = message(message(pool_class, "alloc"), "init")
    try:
        # OpenCV asks for video devices, then muxed devices, then sorts by uniqueID.
        return ordered_names(names_for("vide") + names_for("muxx"))
    finally:
        message(pool, "drain")


def open_capture(index: int):
    backend = getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)
    capture = cv2.VideoCapture(index, backend)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not capture.isOpened():
        capture.release()
        raise CameraPermissionError(permission_message())
    ok, frame = capture.read()
    if not ok or frame is None:
        capture.release()
        raise CameraPermissionError(permission_message())
    # The first frames from the built-in camera are often black while exposure settles.
    for _ in range(12):
        capture.read()
    return capture


class Camera:
    """Reads on a side thread so the preview can keep the newest frame without waiting out the exposure."""

    def __init__(self, index: int) -> None:
        self.index = int(index)
        self.cap = open_capture(self.index)
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._seq = 0
        self._seen = 0
        self._failed = False
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="anime-camera", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with self._lock:
                ready = self._latest is not None or self._failed
            if ready:
                break
            time.sleep(0.01)
        if self._latest is None:
            self.release()
            raise CameraError("The camera stopped sending frames.")

    def _pump(self) -> None:
        try:
            while not self._stop.is_set():
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    with self._lock:
                        self._failed = True
                    self._ready.set()
                    return
                snapshot = frame.copy()
                with self._lock:
                    self._latest = snapshot
                    self._seq += 1
                self._ready.set()
        finally:
            self.cap.release()
            self.cap = None

    def read(self) -> np.ndarray:
        """Return the next frame the camera produced. Skips any that arrived while the last one was on screen."""
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with self._lock:
                failed = self._failed
                if self._latest is not None and self._seq != self._seen:
                    self._seen = self._seq
                    frame = self._latest
                else:
                    frame = None
            if frame is not None:
                return frame.copy()
            if failed:
                raise CameraError("The camera stopped sending frames.")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._ready.wait(remaining):
                break
            self._ready.clear()
        raise CameraError("The camera stopped sending frames.")

    def release(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
            self._thread = None
