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


def render_transmission(
    background: np.ndarray,
    person: np.ndarray,
    mask: np.ndarray,
    progress: float,
    forehead_x: float,
    forehead_y: float,
    returning: bool = False,
) -> np.ndarray:
    """Speed lines, then the body collapses through the forehead.

    progress 0 is the start of this direction and 1 is the end. Leave keeps
    the person for a brief moment, pulls the silhouette out from the forehead
    downward, and finishes on fading lines. Return brings the lines back first
    and restores the body from the forehead downward.
    """
    progress = float(np.clip(progress, 0.0, 1.0))
    timeline = DURATION * ((1.0 - progress) if returning else progress)
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
    rows = np.arange(top, bottom, dtype=np.float32)[:, None]
    collapse = float(np.clip((timeline - 0.12) / 0.16, 0.0, 1.0))
    if collapse <= 0.0:
        survival = np.ones_like(rows)
    elif collapse >= 1.0:
        survival = np.zeros_like(rows)
    else:
        amount = (1.0 - collapse) if returning else collapse
        front = float(forehead_y) + amount * max(bottom - float(forehead_y), 1.0)
        survival = np.clip((front - rows) / 5.0 + 0.5, 0.0, 1.0)
        if not returning:
            survival = 1.0 - survival
    alpha = (local_mask * survival)[:, :, None]
    output = person[top:bottom, left:right].astype(np.float32) * alpha
    output += background[top:bottom, left:right].astype(np.float32) * (1.0 - alpha)
    strength = min(1.0, timeline / 0.035, max(0.0, (DURATION - timeline) / 0.17))
    if strength > 0.0:
        lines = np.zeros((bottom - top, right - left, 3), np.uint8)
        rng = np.random.default_rng(147)
        span = right - left
        for column in range(2, span, 9):
            column = min(span - 1, column + int(rng.integers(-2, 4)))
            length = int(rng.integers(18, 80))
            offset = int(rng.integers(0, bottom - top + 80))
            line_y = int((offset + timeline * 1250) % (bottom - top + 160)) - 80
            color = (255, 255, int(rng.integers(200, 256)))
            cv2.line(
                lines,
                (column, line_y),
                (column, line_y + length),
                color,
                int(rng.integers(1, 4)),
                cv2.LINE_AA,
            )
        if 0.0 < timeline < 0.12:
            fx = int(round(forehead_x)) - left
            fy = int(round(forehead_y)) - top
            cv2.line(lines, (fx - 28, fy), (fx + 28, fy), (255, 255, 255), 2, cv2.LINE_AA)
        glow = lines.astype(np.float32) / 255.0 * local_mask[:, :, None] * strength
        output = output * (1.0 - glow) + 255.0 * glow
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
        pose_ok = instant_transmission_pose(ctx.hands, ctx.face)
        self.window.update(pose_ok, ctx.time)
        report_pose(ctx.debug, self.id, pose_ok, self.window)
        self._handle(ctx)
        return self._render(ctx)

    def _handle(self, ctx: FrameContext) -> None:
        if "escape" in ctx.keys:
            self._on_escape(ctx)
        trigger = self.window.fired or "return" in ctx.keys
        if not trigger:
            return
        if self.phase == "idle":
            self._begin_leave(ctx)
        elif self.phase == "gone":
            self._begin_return(ctx)

    def _on_escape(self, ctx: FrameContext) -> None:
        if self.phase == "gone":
            self._begin_return(ctx)
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
        if self.frozen_mask is None or self.frozen_person is None:
            self.phase = "idle"
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
        if self.phase == "returning" and self.frozen_mask is not None and self.frozen_person is not None:
            progress = (ctx.time - self.t0) / DURATION
            if progress >= 1.0 - 1e-4:
                self.phase = "idle"
                self._clear_frozen()
                return ctx.frame
            base = ctx.background if ctx.background is not None else ctx.frame
            return render_transmission(
                base,
                self.frozen_person,
                self.frozen_mask,
                progress,
                self.forehead_x,
                self.forehead_y,
                returning=True,
            )
        if self.phase == "gone":
            return self._empty_room(ctx)
        return ctx.frame
