"""Two windows, the key map, the session, and the optional virtual camera."""

from __future__ import annotations

import argparse
import json
import os
import time
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
from anime_frame.landmarks import Landmarks
from anime_frame.registry import load_effects
from anime_frame.segment import Segmenter

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / ".anime-frame.json"
PREVIEW_TITLE = "Anime Frame Preview"
CHOOSER_TITLE = "Anime Frame"
CHOOSER_WIDTH = 980
CHOOSER_HEIGHT = 680
ROW_TOP = 84
ROW_HEIGHT = 128
LIST_LEFT = 20
LIST_RIGHT = 430
CARD_BOX = (456, 84, 956, 612)
LOAD_BACKGROUND = "Load background"

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


def render_chooser(effects, active_id: str, status: str, countdown: int | None = None) -> np.ndarray:
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
    for index, effect in enumerate(effects):
        y = ROW_TOP + index * ROW_HEIGHT
        selected = effect.id == active_id
        fill = (64, 68, 78) if selected else (44, 46, 52)
        edge = (150, 186, 210) if selected else (90, 94, 104)
        cv2.rectangle(image, (LIST_LEFT, y), (LIST_RIGHT, y + ROW_HEIGHT - 14), fill, -1)
        cv2.rectangle(image, (LIST_LEFT, y), (LIST_RIGHT, y + ROW_HEIGHT - 14), edge, 1, cv2.LINE_AA)
        title_color = (250, 250, 250) if selected else (214, 214, 214)
        cv2.putText(
            image,
            f"{effect.order}   {effect.title}",
            (LIST_LEFT + 16, y + 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            title_color,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            effect.hint,
            (LIST_LEFT + 16, y + 72),
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
        (LIST_LEFT + 16, load_y + 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (250, 250, 250) if loading else (214, 214, 214),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "Step out. Counts down from 3",
        (LIST_LEFT + 16, load_y + 72),
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
    footer = status or "Click a row, or press 0-1    Load background    Return fire    Esc cancel"
    footer_color = (190, 220, 255) if status else (150, 150, 158)
    cv2.putText(
        image,
        footer,
        (24, CHOOSER_HEIGHT - 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        footer_color,
        1,
        cv2.LINE_AA,
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
        self._hands: list = []
        self._face = None
        self._body = None
        self._landmarks_at: float | None = None
        self._countdown_mark: int | None = None
        self.exit_code = 0

    def run(self) -> int:
        ensure_models(ROOT / "models")
        audio.ensure_all(ROOT / "assets")
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

    def _open_windows(self) -> None:
        cv2.namedWindow(PREVIEW_TITLE, cv2.WINDOW_NORMAL)
        cv2.namedWindow(CHOOSER_TITLE, cv2.WINDOW_AUTOSIZE)
        cv2.resizeWindow(PREVIEW_TITLE, FRAME_WIDTH, FRAME_HEIGHT)
        cv2.moveWindow(PREVIEW_TITLE, 40, 40)
        cv2.moveWindow(CHOOSER_TITLE, 700, 36)
        self._mouse_ready = False

    def _arm_mouse(self) -> None:
        if self._mouse_ready:
            return
        cv2.setMouseCallback(CHOOSER_TITLE, self._on_mouse)
        self._mouse_ready = True

    def _on_mouse(self, event, x, y, _flags, _param) -> None:
        if event in (cv2.EVENT_LBUTTONUP, cv2.EVENT_LBUTTONDOWN):
            self.clicked_row = row_at(x, y, len(self.effects) + 1)

    def _loop(self) -> None:
        while True:
            if self.shown and self._windows_closed():
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
            if self.background.capturing:
                output = frame
                countdown = self.background.seconds_left(now)
                if countdown != self._countdown_mark:
                    print(f"{STEP_OUT} {countdown}", flush=True)
                    self._countdown_mark = countdown
                status = f"{STEP_OUT} {countdown}"
            else:
                output = self._apply(frame, now, command)
            cv2.imshow(PREVIEW_TITLE, output)
            cv2.imshow(CHOOSER_TITLE, render_chooser(self.effects, self.active.id, status, countdown))
            self._arm_mouse()
            self.shown = True
            if self.virtual is not None and not self._send(output):
                self.exit_code = 1
                break

    def _apply(self, frame: np.ndarray, now: float, command: str | None) -> np.ndarray:
        timestamp = self._clock()
        mask = self.segmenter.segment(frame, timestamp)
        # Gestures are sampled about ten times a second. The landmark models run
        # on that cadence and the latest points are reused in between, which keeps
        # a full session around 30 fps on this Mac.
        if self._landmarks_at is None or now - self._landmarks_at >= 0.09:
            self._hands, self._face, self._body = self.landmarks.detect(frame, timestamp)
            self._landmarks_at = now
        keys = set()
        if command in {"return", "escape"}:
            keys.add(command)
        context = FrameContext(
            frame=frame,
            mask=mask,
            background=self.background.image,
            time=now,
            hands=self._hands,
            face=self._face,
            pose_landmarks=self._body,
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

    def _windows_closed(self) -> bool:
        preview = cv2.getWindowProperty(PREVIEW_TITLE, cv2.WND_PROP_VISIBLE)
        chooser = cv2.getWindowProperty(CHOOSER_TITLE, cv2.WND_PROP_VISIBLE)
        return preview < 0 or chooser < 0

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
        self._remember(effect_id=effect.id)
        if self.background.capturing and self.capture_reason == "effect" and not effect.replaces_person:
            self.background.cancel()
            self.capture_reason = None
        if effect.replaces_person and self.background.image is None and not self.background.capturing:
            self._begin_capture("effect", now)

    def _load_background(self, now: float) -> None:
        """Start a fresh empty-room capture and its countdown."""
        if self.background.capturing:
            self.background.cancel()
            self._countdown_mark = None
        self.capture_reason = "menu"
        self.background.start(now)

    def _begin_capture(self, reason: str, now: float) -> None:
        if self.background.capturing:
            if reason == "space":
                self.capture_reason = "space"
            return
        self.capture_reason = reason
        self.background.start(now)

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
        self._landmarks_at = None
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
