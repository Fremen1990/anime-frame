"""Goku Instant Transmission: the person collapses into the forehead and the empty room stays."""

from __future__ import annotations

import cv2
import numpy as np

from anime_frame import audio
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.pose import PoseWindow, instant_transmission_pose, report_pose

DURATION = 0.45
MARGIN = 8


def mask_bounds(mask: np.ndarray, margin: int = MARGIN) -> tuple[int, int, int, int] | None:
    binary = (np.squeeze(mask) > 0.5).astype(np.uint8)
    if binary.ndim != 2 or int(binary.max()) == 0:
        return None
    x, y, width, height = cv2.boundingRect(binary)
    limit_y, limit_x = binary.shape
    return (
        max(0, x - margin),
        max(0, y - margin),
        min(limit_x, x + width + margin),
        min(limit_y, y + height + margin),
    )


def _forehead(face: np.ndarray | None, mask: np.ndarray) -> tuple[float, float]:
    if face is not None and len(face) > 10:
        return float(face[10, 0]), float(face[10, 1])
    bounds = mask_bounds(mask, margin=0)
    if bounds is None:
        height, width = np.squeeze(mask).shape[:2]
        return width / 2.0, height / 3.0
    x0, y0, x1, _y1 = bounds
    return (x0 + x1) / 2.0, float(y0)


def _wipe_amount(progress: float) -> float:
    """Hold the full figure, then sweep. The body never scales or fades."""
    start, end = 0.30, 0.72
    return float(np.clip((progress - start) / (end - start), 0.0, 1.0))


def render_transmission(
    background: np.ndarray,
    person: np.ndarray,
    mask: np.ndarray,
    progress: float,
    forehead_x: float,
    forehead_y: float,
    returning: bool = False,
) -> np.ndarray:
    """Sweep the full-size figure out from the forehead downward. Streaks stay inside the mask."""
    progress = float(np.clip(progress, 0.0, 1.0))
    canvas = background.copy()
    flat = np.squeeze(mask).astype(np.float32)
    points = cv2.findNonZero((flat > 0.01).astype(np.uint8))
    if points is None:
        return canvas
    x, y, width, height = cv2.boundingRect(points)
    left, top = max(0, x - MARGIN), max(0, y - MARGIN)
    right = min(flat.shape[1], x + width + MARGIN)
    bottom = min(flat.shape[0], y + height + MARGIN)
    if right <= left or bottom <= top:
        return canvas
    local_mask = flat[top:bottom, left:right]
    local_person = person[top:bottom, left:right]
    local_background = background[top:bottom, left:right]
    amount = _wipe_amount(progress)
    rows = np.arange(top, bottom, dtype=np.float32)[:, None]
    if amount <= 0:
        survival = np.zeros_like(rows) if returning else np.ones_like(rows)
    elif amount >= 1:
        survival = np.ones_like(rows) if returning else np.zeros_like(rows)
    else:
        front = float(forehead_y) + amount * max(float(bottom) - float(forehead_y), 1.0)
        passed = np.clip((front - rows) / 5.0 + 0.5, 0.0, 1.0)
        survival = passed if returning else 1.0 - passed
    alpha = np.clip(local_mask * survival, 0.0, 1.0)[:, :, None]
    output = local_person.astype(np.float32) * alpha + local_background.astype(np.float32) * (1.0 - alpha)

    if progress < 0.12:
        streak_strength = progress / 0.12
    elif progress < 0.88:
        streak_strength = 1.0
    else:
        streak_strength = max(0.0, (1.0 - progress) / 0.12)
    if streak_strength > 0:
        lines = np.zeros_like(local_person)
        rng = np.random.default_rng(147)
        span = right - left
        column_height = bottom - top
        for column in range(2, span, 9):
            line_x = min(span - 1, column + int(rng.integers(-2, 4)))
            line_y = int((int(rng.integers(0, column_height + 80)) + progress * 560) % (column_height + 120)) - 60
            color = (255, 255, int(rng.integers(210, 256)))
            cv2.line(
                lines,
                (line_x, line_y),
                (line_x, line_y + int(rng.integers(18, 75))),
                color,
                int(rng.integers(1, 3)),
                cv2.LINE_AA,
            )
        if not returning and 0.04 < progress < 0.28:
            fx = int(round(forehead_x)) - left
            fy = int(round(forehead_y)) - top
            cv2.line(lines, (fx - 22, fy), (fx + 22, fy), (255, 255, 255), 2, cv2.LINE_AA)
        light = lines.astype(np.float32) / 255.0 * local_mask[:, :, None] * streak_strength * 0.85
        output = output * (1.0 - light) + 255.0 * light
    canvas[top:bottom, left:right] = np.clip(output, 0, 255).astype(np.uint8)
    return canvas


class InstantTransmission(Effect):
    id = "instant_transmission"
    title = "Goku Instant Transmission"
    hint = "Two fingers together on the forehead"
    order = 1
    replaces_person = True

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.phase = "idle"
        self.t0 = 0.0
        self.frozen_mask: np.ndarray | None = None
        self.frozen_person: np.ndarray | None = None
        self.forehead_x = 0.0
        self.forehead_y = 0.0
        self.window = PoseWindow()

    def update(self, ctx: FrameContext) -> np.ndarray:
        fresh = ctx.landmarks_at is None or ctx.time - ctx.landmarks_at <= 0.3
        pose_ok = fresh and instant_transmission_pose(ctx.hands, ctx.face)
        self.window.update(pose_ok, ctx.time, ctx.landmark_timestamp_ms if fresh else None)
        report_pose(ctx.debug, self.id, pose_ok, self.window)
        self._handle(ctx)
        return self._render(ctx)

    def _handle(self, ctx: FrameContext) -> None:
        if "escape" in ctx.keys:
            self._on_escape(ctx)
            return
        trigger = self.window.fired or "return" in ctx.keys
        if not trigger:
            return
        if self.phase == "idle":
            if "return" in ctx.keys:
                self.window.arm_release()
            self._begin_leave(ctx)
        elif self.phase == "gone":
            if "return" in ctx.keys:
                self.window.arm_release()
            self._begin_return(ctx)

    def _on_escape(self, ctx: FrameContext) -> None:
        if ctx.mask is None or not np.any(ctx.mask):
            self.reset()
            return
        if self.phase == "gone":
            self._begin_return(ctx)
            return
        if self.phase == "returning":
            self.reset()
            return
        if self.phase != "leaving" or self.frozen_mask is None:
            return
        progress = min(1.0, max(0.0, (ctx.time - self.t0) / DURATION))
        self.phase = "returning"
        self.t0 = ctx.time - (1.0 - progress) * DURATION
        audio.play("instant_transmission")

    def _begin_leave(self, ctx: FrameContext) -> None:
        if ctx.mask is None or ctx.background is None:
            return
        self.frozen_mask = np.squeeze(ctx.mask).astype(np.float32).copy()
        self.frozen_person = ctx.frame.copy()
        self.forehead_x, self.forehead_y = _forehead(ctx.face, self.frozen_mask)
        self.phase = "leaving"
        self.t0 = ctx.time
        audio.play("instant_transmission")

    def _begin_return(self, ctx: FrameContext) -> None:
        if ctx.mask is None or not np.any(ctx.mask):
            return
        self.phase = "returning"
        self.t0 = ctx.time
        audio.play("instant_transmission")

    def _empty_room(self, ctx: FrameContext) -> np.ndarray:
        if ctx.background is not None:
            return ctx.background.copy()
        return ctx.frame

    def _clear_frozen(self) -> None:
        self.frozen_mask = None
        self.frozen_person = None

    def _render(self, ctx: FrameContext) -> np.ndarray:
        if self.phase == "leaving" and self.frozen_mask is not None and self.frozen_person is not None:
            progress = (ctx.time - self.t0) / DURATION
            if progress >= 1.0 - 1e-4:
                self.phase = "gone"
                return self._empty_room(ctx)
            base = ctx.background if ctx.background is not None else ctx.frame
            return render_transmission(
                base,
                self.frozen_person,
                self.frozen_mask,
                progress,
                self.forehead_x,
                self.forehead_y,
            )
        if self.phase == "returning":
            progress = (ctx.time - self.t0) / DURATION
            if progress >= 1.0 - 1e-4:
                self.phase = "idle"
                self._clear_frozen()
                return ctx.frame
            base = ctx.background if ctx.background is not None else ctx.frame
            if ctx.mask is None or not np.any(ctx.mask):
                return base.copy()
            forehead_x, forehead_y = _forehead(ctx.face, ctx.mask)
            return render_transmission(
                base,
                ctx.frame,
                ctx.mask,
                progress,
                forehead_x,
                forehead_y,
                returning=True,
            )
        if self.phase == "gone":
            return self._empty_room(ctx)
        return ctx.frame
