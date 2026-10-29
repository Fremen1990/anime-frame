"""Camera choice and capture.

On macOS the device order matches OpenCV's AVFoundation backend: video devices
first, then muxed devices. A permission failure raises and does not try another
index.
"""

from __future__ import annotations

import os
import subprocess
import sys
from ctypes import c_char_p, c_ulong, c_void_p, cdll

import cv2
import numpy as np

# Drop this to (960, 540) if a full session cannot hold about 20 fps.
CAPTURE_SIZE = (1280, 720)
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
    def __init__(self, index: int) -> None:
        self.index = int(index)
        self.cap = open_capture(self.index)

    def read(self) -> np.ndarray:
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise CameraError("The camera stopped sending frames.")
        return frame.copy()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
