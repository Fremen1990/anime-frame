"""Two windows, the key map, the session, and the optional virtual camera."""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from ctypes import CDLL, Structure, c_char_p, c_double, c_ulong, c_void_p
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")

import cv2
import numpy as np
import pyvirtualcam

from anime_frame import audio
from anime_frame.background import STEP_OUT, Background
from anime_frame.camera import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    Camera,
    CameraError,
    CameraPermissionError,
    fit_frame,
    list_camera_names,
    resolve_index,
)
from anime_frame.downloads import ensure_models
from anime_frame.effects.base import FrameContext
from anime_frame.guide import draw_card, draw_countdown
from anime_frame.hair import HairTracker
from anime_frame.landmarks import Landmarks, LandmarkObservation
from anime_frame.registry import load_effects
from anime_frame.segment import Segmenter

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / ".anime-frame.json"
PREVIEW_TITLE = "Anime Frame Preview"
CHOOSER_TITLE = "Anime Frame"
CHOOSER_WIDTH = 980
CHOOSER_HEIGHT = 680
ROW_TOP = 84
ROW_HEIGHT = 88
LIST_LEFT = 20
LIST_RIGHT = 430
CARD_BOX = (456, 84, 956, 612)
LOAD_BACKGROUND = "Load background"
CAPTURE_RESTART_GAP = 0.75
WINDOW_MISS_LIMIT = 45
PREVIEW_STAYS = "Background saved. The preview stays open. Press Q to quit."


class _NSRect(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("width", c_double), ("height", c_double)]


class _NSSize(Structure):
    _fields_ = [("width", c_double), ("height", c_double)]


class _NSPoint(Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


_OBJC = None


def _objc():
    global _OBJC
    if _OBJC is None:
        lib = CDLL("/usr/lib/libobjc.A.dylib")
        CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        lib.objc_getClass.restype = c_void_p
        lib.objc_getClass.argtypes = [c_char_p]
        lib.sel_registerName.restype = c_void_p
        lib.sel_registerName.argtypes = [c_char_p]
        _OBJC = lib
    return _OBJC


def _msg(obj, name: str, *args, restype=c_void_p, argtypes=None):
    lib = _objc()
    lib.objc_msgSend.restype = restype
    extra = [c_void_p] * len(args) if argtypes is None else list(argtypes)
    lib.objc_msgSend.argtypes = [c_void_p, c_void_p, *extra]
    return lib.objc_msgSend(obj, lib.sel_registerName(name.encode()), *args)


def main_visible_frame() -> _NSRect | None:
    """The display with the menu bar, in Cocoa points. Origin is the bottom left."""
    try:
        screen = _msg(_objc().objc_getClass(b"NSScreen"), "mainScreen")
        if not screen:
            return None
        rect = _msg(screen, "visibleFrame", restype=_NSRect, argtypes=[])
    except OSError:
        return None
    if rect.width < 800 or rect.height < 600:
        return None
    return rect


def screen_size() -> tuple[int, int]:
    rect = main_visible_frame()
    if rect is None:
        return 1440, 900
    return int(rect.width), int(rect.height)


def _ns_window(title: str):
    app = _msg(_objc().objc_getClass(b"NSApplication"), "sharedApplication")
    windows = _msg(app, "windows") if app else None
    if not windows:
        return None
    count = int(_msg(windows, "count", restype=c_ulong, argtypes=[]))
    for index in range(count):
        window = _msg(windows, "objectAtIndex:", index, argtypes=[c_ulong])
        label = _msg(window, "title")
        raw = _msg(label, "UTF8String", restype=c_char_p, argtypes=[]) if label else None
        if raw and raw.decode() == title:
            return window
    return None


def place_on_main_screen(
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    resize: bool,
    key: bool = False,
) -> bool:
    """Put a window on the main display. OpenCV's moveWindow will not.

    The first tall frame grows onto a display above this one, and moveWindow
    then keeps using that display. The camera window leaves the screen in front
    of the person.
    """
    window = _ns_window(title)
    visible = main_visible_frame()
    if window is None or visible is None:
        return False
    if resize:
        _msg(
            window,
            "setContentSize:",
            _NSSize(float(width), float(height)),
            restype=None,
            argtypes=[_NSSize],
        )
    frame = _msg(window, "frame", restype=_NSRect, argtypes=[])
    origin = _NSPoint(visible.x + float(x), visible.y + visible.height - float(y) - frame.height)
    _msg(window, "setFrameOrigin:", origin, restype=None, argtypes=[_NSPoint])
    _msg(window, "makeKeyAndOrderFront:" if key else "orderFront:", 0, restype=None, argtypes=[c_void_p])
    return True


def window_layout(screen_w: int, screen_h: int) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    """Preview (x, y, width, height) and chooser (x, y), on screen and not covering each other."""
    margin = 16
    gap = 12
    width = max(int(screen_w), 1)
    height = max(int(screen_h), 1)
    room = width - CHOOSER_WIDTH - margin * 2 - gap
    if room >= 320 and height >= CHOOSER_HEIGHT + margin + 40:
        preview_w = min(960, room)
        preview_h = min(int(round(preview_w * 9 / 16)), height - margin * 2)
        preview_w = min(room, max(320, int(round(preview_h * 16 / 9))))
        preview_h = max(180, int(round(preview_w * 9 / 16)))
        return (margin, margin, preview_w, preview_h), (margin + preview_w + gap, margin)
    preview_w = min(960, max(320, width - margin * 2))
    preview_h = min(int(round(preview_w * 9 / 16)), max(180, height // 3))
    return (margin, margin, preview_w, preview_h), (margin, margin + preview_h + 36)


def window_fate(visible: float, misses: int) -> tuple[str, int]:
    """Keep a live window. Recreate one OpenCV has lost. Quit only after it stays gone."""
    if visible >= 1:
        return "keep", 0
    misses += 1
    if misses >= WINDOW_MISS_LIMIT:
        return "quit", misses
    if misses in (1, 15, 30):
        return "revive", misses
    return "wait", misses


def _window_visible(title: str) -> float:
    try:
        return float(cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE))
    except cv2.error:
        return -1.0


def put_label(image: np.ndarray, label: str, origin: tuple[int, int], scale: float, color: tuple[int, int, int]) -> None:
    """OpenCV's Hershey face has no macron; draw it over the ASCII glyph."""
    plain = label.replace("ō", "o")
    cv2.putText(image, plain, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    for index, character in enumerate(label):
        if character == "ō":
            prefix = cv2.getTextSize(plain[:index], cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
            glyph = cv2.getTextSize("o", cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
            y = origin[1] - int(round(19 * scale))
            cv2.line(image, (origin[0] + prefix + 2, y), (origin[0] + prefix + glyph - 2, y), color, 1, cv2.LINE_AA)

OBS_SETUP = """OBS Virtual Camera is not available.

One-time setup:
1. Install OBS Studio.
2. Allow the camera extension if macOS asks.
3. In OBS, start Virtual Camera, then stop it.
4. Quit OBS.
5. Run ./run teams again.
"""


def decode_key(code: int) -> str | None:
    if code is None or code < 0:
        return None
    low = code & 0xFF
    if code in (10, 13) or low in (10, 13):
        return "return"
    if code == 27 or low == 27:
        return "escape"
    if low == 32:
        return "space"
    if low in (ord("q"), ord("Q")):
        return "q"
    if low in (ord("f"), ord("F")):
        return "f"
    if low == ord("["):
        return "["
    if low == ord("]"):
        return "]"
    if ord("0") <= low <= ord("9"):
        return chr(low)
    return None


def row_at(x: int, y: int, count: int) -> int | None:
    if not LIST_LEFT <= x <= LIST_RIGHT or y < ROW_TOP:
        return None
    index = (y - ROW_TOP) // ROW_HEIGHT
    if 0 <= index < count and (y - ROW_TOP) % ROW_HEIGHT < ROW_HEIGHT - 12:
        return int(index)
    return None


def render_chooser(effects, active_id: str, status: str, countdown: int | None = None, audio_warning: str = "") -> np.ndarray:
    image = np.full((CHOOSER_HEIGHT, CHOOSER_WIDTH, 3), (32, 32, 36), np.uint8)
    cv2.putText(
        image,
        CHOOSER_TITLE,
        (24, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.95,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    if audio_warning:
        put_label(image, audio_warning, (456, 52), 0.43, (150, 195, 240))
    for index, effect in enumerate(effects):
        y = ROW_TOP + index * ROW_HEIGHT
        selected = effect.id == active_id
        fill = (64, 68, 78) if selected else (44, 46, 52)
        edge = (150, 186, 210) if selected else (90, 94, 104)
        cv2.rectangle(image, (LIST_LEFT, y), (LIST_RIGHT, y + ROW_HEIGHT - 14), fill, -1)
        cv2.rectangle(image, (LIST_LEFT, y), (LIST_RIGHT, y + ROW_HEIGHT - 14), edge, 1, cv2.LINE_AA)
        title_color = (250, 250, 250) if selected else (214, 214, 214)
        put_label(image, f"{effect.order}   {effect.title}", (LIST_LEFT + 16, y + 34), 0.62, title_color)
        cv2.putText(
            image,
            effect.hint,
            (LIST_LEFT + 16, y + 61),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (168, 176, 186),
            1,
            cv2.LINE_AA,
        )
    load_y = ROW_TOP + len(effects) * ROW_HEIGHT
    loading = countdown is not None
    load_fill = (64, 68, 78) if loading else (44, 46, 52)
    load_edge = (150, 186, 210) if loading else (90, 94, 104)
    cv2.rectangle(image, (LIST_LEFT, load_y), (LIST_RIGHT, load_y + ROW_HEIGHT - 14), load_fill, -1)
    cv2.rectangle(image, (LIST_LEFT, load_y), (LIST_RIGHT, load_y + ROW_HEIGHT - 14), load_edge, 1, cv2.LINE_AA)
    cv2.putText(
        image,
        LOAD_BACKGROUND,
        (LIST_LEFT + 16, load_y + 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (250, 250, 250) if loading else (214, 214, 214),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "Step out. Counts down from 3",
        (LIST_LEFT + 16, load_y + 61),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (168, 176, 186),
        1,
        cv2.LINE_AA,
    )
    if countdown is None:
        draw_card(image, active_id, CARD_BOX)
    else:
        draw_countdown(image, CARD_BOX, countdown)
    footer = status or "Click a row, or press 0-4    Load background    Return fire    Esc cancel"
    footer_color = (190, 220, 255) if status else (150, 150, 158)
    put_label(
        image,
        footer,
        (24, CHOOSER_HEIGHT - 28),
        0.48,
        footer_color,
    )
    return image


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _camera_label(index: int, names: list[str] | None) -> str:
    if names and 0 <= index < len(names):
        return f"{names[index]} (index {index})"
    return f"index {index}"


class App:
    def __init__(self, debug: bool = False, teams: bool = False) -> None:
        self.debug = debug
        self.teams = teams
        self.camera: Camera | None = None
        self.virtual = None
        self.segmenter: Segmenter | None = None
        self.landmarks: Landmarks | None = None
        self.background = Background()
        self.capture_reason: str | None = None
        self.effects = []
        self.active = None
        self.settings = load_settings(SETTINGS_PATH)
        self.names: list[str] | None = None
        self.fullscreen = False
        self.shown = False
        self.clicked_row: int | None = None
        self._timestamp = 0
        self._observation: LandmarkObservation | None = None
        self._landmarks_at: float | None = None
        self.hair: HairTracker | None = None
        self._countdown_mark: int | None = None
        self._screen: tuple[int, int] | None = None
        self._window_misses: dict[str, int] = {}
        self._place_again = False
        self._apply_failed = False
        self.exit_code = 0

    def run(self) -> int:
        ensure_models(ROOT / "models")
        audio.ensure_all(ROOT / "assets")
        audio.initialize(ROOT / "assets")
        self.effects = load_effects()
        if not self.effects:
            print("No effects were found.")
            return 1
        wanted = self.settings.get("effect_id", "clear")
        self.active = next((effect for effect in self.effects if effect.id == wanted), self.effects[0])
        if not self._open_camera():
            return 1
        if self.teams and not self._open_virtual():
            return 1
        self._open_models()
        self._open_windows()
        try:
            self._loop()
        except KeyboardInterrupt:
            pass
        return self.exit_code

    def close(self) -> None:
        if self.active is not None:
            self.active.reset()
        audio.shutdown()
        if self.virtual is not None:
            try:
                self.virtual.close()
            except Exception:
                pass
            self.virtual = None
        if self.segmenter is not None:
            self.segmenter.close()
            self.segmenter = None
        if self.landmarks is not None:
            self.landmarks.close()
            self.landmarks = None
        if self.hair is not None:
            self.hair.close()
            self.hair = None
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        cv2.destroyAllWindows()

    def _open_camera(self) -> bool:
        self.names = list_camera_names()
        remembered = self.settings.get("camera_index")
        try:
            remembered = None if remembered is None else int(remembered)
        except (TypeError, ValueError):
            remembered = None
        index = resolve_index(remembered, self.names, self.settings.get("camera_name"))
        wanted = self.names[index] if self.names and 0 <= index < len(self.names) else None
        try:
            self.camera = Camera(index)
        except CameraPermissionError as exc:
            print(exc)
            self.camera = None
            return False
        self._align_camera(wanted)
        print(f"Camera: {_camera_label(self.camera.index, self.names)}", flush=True)
        self._remember_known()
        return True

    def _open_virtual(self) -> bool:
        try:
            self.virtual = pyvirtualcam.Camera(
                width=FRAME_WIDTH,
                height=FRAME_HEIGHT,
                fps=20,
                fmt=pyvirtualcam.PixelFormat.BGR,
            )
        except Exception as exc:
            print(OBS_SETUP)
            print(exc)
            return False
        print("Teams receives the picture only. Effect sounds stay on this Mac.")
        return True

    def _open_models(self) -> None:
        models = ROOT / "models"
        self.segmenter = Segmenter(models / "selfie_segmenter_landscape.tflite")
        self.landmarks = Landmarks(models)
        self.hair = HairTracker(models / "hair_segmenter.tflite")

    def _open_windows(self) -> None:
        self._screen = screen_size()
        cv2.namedWindow(PREVIEW_TITLE, cv2.WINDOW_NORMAL)
        cv2.namedWindow(CHOOSER_TITLE, cv2.WINDOW_AUTOSIZE)
        self._window_misses = {PREVIEW_TITLE: 0, CHOOSER_TITLE: 0}
        # The first image forces the window back to the frame size. Place again after that.
        self._place_again = True
        self._mouse_ready = False

    def _place_windows(self) -> None:
        if self._screen is None:
            self._screen = screen_size()
        preview, chooser = window_layout(*self._screen)
        preview_ok = place_on_main_screen(PREVIEW_TITLE, *preview, resize=True)
        chooser_ok = place_on_main_screen(
            CHOOSER_TITLE,
            chooser[0],
            chooser[1],
            CHOOSER_WIDTH,
            CHOOSER_HEIGHT,
            resize=False,
            key=True,
        )
        if preview_ok and chooser_ok:
            return
        x, y, width, height = preview
        cv2.resizeWindow(PREVIEW_TITLE, int(width), int(height))
        cv2.moveWindow(PREVIEW_TITLE, int(x), int(y))
        cv2.moveWindow(CHOOSER_TITLE, int(chooser[0]), int(chooser[1]))

    def _arm_mouse(self) -> None:
        if self._mouse_ready:
            return
        cv2.setMouseCallback(CHOOSER_TITLE, self._on_mouse)
        self._mouse_ready = True

    def _on_mouse(self, event, x, y, _flags, _param) -> None:
        # Press and release both arrive. Acting on both restarts the countdown twice per click.
        if event == cv2.EVENT_LBUTTONUP:
            self.clicked_row = row_at(x, y, len(self.effects) + 1)

    def _loop(self) -> None:
        while True:
            if self.shown and not self._keep_windows():
                break
            try:
                raw = self.camera.read()
            except CameraError as exc:
                print(exc)
                self.exit_code = 1
                break
            frame = cv2.flip(fit_frame(raw), 1)
            now = time.monotonic()
            command = decode_key(cv2.waitKey(1))
            if command == "q":
                break
            if command == "f":
                self._toggle_fullscreen()
            elif command == "[":
                self._switch_camera(-1)
                continue
            elif command == "]":
                self._switch_camera(1)
                continue
            elif command is not None and command.isdigit():
                self._select_order(int(command), now)
            if self.clicked_row is not None:
                if self.clicked_row == len(self.effects):
                    self._load_background(now)
                else:
                    self._select_index(self.clicked_row, now)
                self.clicked_row = None
            if command == "space":
                self._begin_capture("space", now)
            if (
                self.active.replaces_person
                and self.background.image is None
                and not self.background.capturing
            ):
                self._begin_capture("effect", now)

            status = ""
            countdown = None
            if self.background.capturing:
                self.background.update(frame, now)
                if not self.background.capturing:
                    self.capture_reason = None
                    self._countdown_mark = None
                    print(PREVIEW_STAYS, flush=True)
            if self.background.capturing:
                output = frame
                countdown = self.background.seconds_left(now)
                if countdown != self._countdown_mark:
                    print(f"{STEP_OUT} {countdown}", flush=True)
                    self._countdown_mark = countdown
                status = f"{STEP_OUT} {countdown}"
            else:
                try:
                    output = self._apply(frame, now, command)
                except Exception:
                    if not self._apply_failed:
                        traceback.print_exc()
                        self._apply_failed = True
                    output = frame
                else:
                    self._apply_failed = False
                status = self.active.status
            cv2.imshow(PREVIEW_TITLE, output)
            cv2.imshow(CHOOSER_TITLE, render_chooser(self.effects, self.active.id, status, countdown, audio.warning(self.active.id)))
            if self._place_again:
                self._place_windows()
                self._place_again = False
            self._arm_mouse()
            self.shown = True
            if self.virtual is not None and not self._send(output):
                self.exit_code = 1
                break

    def _apply(self, frame: np.ndarray, now: float, command: str | None) -> np.ndarray:
        timestamp = self._clock()
        mask = self.segmenter.segment(frame, timestamp)
        # Gesture models run on their own thread, about ten times a second.
        # This frame reuses the latest finished observation.
        observation, observed_at = self.landmarks.sample(frame, timestamp, now)
        if observed_at is not None:
            self._observation = observation
            self._landmarks_at = observed_at
        observation = self._observation
        hair_mask, hair_mask_at = (None, None)
        if self.active.needs_hair_mask and self.hair is not None:
            hair_mask, hair_mask_at = self.hair.sample(frame, timestamp, now, observation.face if observation is not None else None)
        keys = set()
        if command in {"return", "escape"}:
            keys.add(command)
        context = FrameContext(
            frame=frame,
            mask=mask,
            background=self.background.image,
            time=now,
            hands=observation.hands if observation is not None else [],
            face=observation.face if observation is not None else None,
            pose_landmarks=observation.body if observation is not None else None,
            hand_world_landmarks=observation.hand_world if observation is not None else [],
            pose_world_landmarks=observation.body_world if observation is not None else None,
            pose_confidence=observation.body_confidence if observation is not None else None,
            landmarks_at=self._landmarks_at,
            landmark_timestamp_ms=observation.timestamp_ms if observation is not None else None,
            hair_mask=hair_mask,
            hair_mask_at=hair_mask_at,
            hair_reference_anchor=self.hair.reference_anchor if self.hair is not None and hair_mask is not None else None,
            keys=keys,
            debug=self.debug,
        )
        return self.active.update(context)

    def _send(self, frame: np.ndarray) -> bool:
        image = np.ascontiguousarray(frame)
        if image.shape[1] != FRAME_WIDTH or image.shape[0] != FRAME_HEIGHT:
            image = cv2.resize(image, (FRAME_WIDTH, FRAME_HEIGHT))
            image = np.ascontiguousarray(image)
        try:
            self.virtual.send(image)
            self.virtual.sleep_until_next_frame()
        except Exception as exc:
            print("The virtual camera stopped.")
            print(exc)
            return False
        return True

    def _clock(self) -> int:
        now = int(time.monotonic() * 1000)
        if now <= self._timestamp:
            now = self._timestamp + 1
        self._timestamp = now
        return now

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flag = cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL
        cv2.setWindowProperty(PREVIEW_TITLE, cv2.WND_PROP_FULLSCREEN, flag)
        if not self.fullscreen:
            self._place_again = True

    def _keep_windows(self) -> bool:
        """The preview stays up after the empty room is saved. Q is what quits."""
        if self.fullscreen:
            return True
        still_here = True
        for title, flags in (
            (PREVIEW_TITLE, cv2.WINDOW_NORMAL),
            (CHOOSER_TITLE, cv2.WINDOW_AUTOSIZE),
        ):
            fate, misses = window_fate(_window_visible(title), self._window_misses.get(title, 0))
            self._window_misses[title] = misses
            if fate == "revive":
                self._recreate_window(title, flags)
            elif fate == "quit":
                still_here = False
        return still_here

    def _recreate_window(self, title: str, flags: int) -> None:
        try:
            cv2.destroyWindow(title)
        except cv2.error:
            pass
        cv2.namedWindow(title, flags)
        if title == CHOOSER_TITLE:
            self._mouse_ready = False
        self._place_again = True

    def _select_order(self, order: int, now: float) -> None:
        for index, effect in enumerate(self.effects):
            if effect.order == order:
                self._select_index(index, now)
                return

    def _select_index(self, index: int, now: float) -> None:
        if not 0 <= index < len(self.effects):
            return
        effect = self.effects[index]
        if effect is self.active:
            return
        self.active.reset()
        self.active = effect
        self.active.reset()
        if self.hair is not None:
            self.hair.reset()
        self._remember(effect_id=effect.id)
        if self.background.capturing and self.capture_reason == "effect" and not effect.replaces_person:
            self.background.cancel()
            self.capture_reason = None
        if effect.replaces_person and self.background.image is None and not self.background.capturing:
            self._begin_capture("effect", now)

    def _load_background(self, now: float) -> None:
        """Start a fresh empty-room capture and its countdown."""
        if self.background.capturing and now - self.background.started_at < CAPTURE_RESTART_GAP:
            return
        if self.background.capturing:
            self.background.cancel()
            self._countdown_mark = None
        self._reset_tracking()
        self.capture_reason = "menu"
        self.background.start(now)

    def _begin_capture(self, reason: str, now: float) -> None:
        if self.background.capturing:
            if reason == "space":
                self.capture_reason = "space"
            return
        self.capture_reason = reason
        self._reset_tracking()
        self.background.start(now)

    def _reset_tracking(self) -> None:
        if self.active is not None:
            self.active.reset()
        if self.hair is not None:
            self.hair.reset()
        if self.landmarks is not None:
            self.landmarks.reset()
        self._observation = None
        self._landmarks_at = None

    def _switch_camera(self, delta: int) -> None:
        names = list_camera_names()
        nxt = self.camera.index + delta
        if nxt < 0:
            return
        if names is not None and nxt >= len(names):
            return
        try:
            opened = Camera(nxt)
        except CameraError:
            print(f"No camera at index {nxt}.")
            return
        self.camera.release()
        self.camera = opened
        self.names = names
        self.background.cancel()
        self.background.image = None
        self.capture_reason = None
        self._reset_tracking()
        self._remember_camera()
        print(f"Camera: {_camera_label(opened.index, names)}", flush=True)

    def _align_camera(self, wanted: str | None) -> None:
        """Re-open if the device list moved between the name lookup and capture."""
        fresh = list_camera_names()
        if not fresh:
            return
        current = fresh[self.camera.index] if 0 <= self.camera.index < len(fresh) else None
        self.names = fresh
        if not wanted or current == wanted or wanted not in fresh:
            return
        try:
            opened = Camera(fresh.index(wanted))
        except CameraError:
            return
        self.camera.release()
        self.camera = opened

    def _remember_known(self) -> None:
        updates = {}
        if self.settings.get("camera_index") != self.camera.index:
            updates["camera_index"] = self.camera.index
        name = self._camera_name()
        if name and self.settings.get("camera_name") != name:
            updates["camera_name"] = name
        if self.settings.get("effect_id") != self.active.id:
            updates["effect_id"] = self.active.id
        if updates:
            self._remember(**updates)

    def _remember_camera(self) -> None:
        values = {"camera_index": self.camera.index}
        name = self._camera_name()
        if name:
            values["camera_name"] = name
        self._remember(**values)

    def _camera_name(self) -> str | None:
        if self.names and 0 <= self.camera.index < len(self.names):
            return self.names[self.camera.index]
        return None

    def _remember(self, **values) -> None:
        self.settings.update(values)
        save_settings(SETTINGS_PATH, self.settings)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="anime-frame")
    parser.add_argument("--debug", action="store_true", help="Print pose decisions. Draws nothing on the video.")
    parser.add_argument("--teams", action="store_true", help="Also send the preview to OBS Virtual Camera.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = App(debug=args.debug, teams=args.teams)
    try:
        return app.run()
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
