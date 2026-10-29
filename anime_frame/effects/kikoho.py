"""One forward gesture, one complete Shin Kikōhō clip and blast."""

from __future__ import annotations

import numpy as np

from anime_frame import audio
from anime_frame.attack import fresh_tracking, hand_anchor, observation_id
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.pose import PoseWindow, aimed_at_camera, kikoho_pose, report_pose
from anime_frame.vfx import square_blast

# Length of the user's selected Shin Kikōhō recording, including its tail.
CLIP_SECONDS = 4.023
EXPAND_SECONDS = 0.55


class Kikoho(Effect):
    id = "kikoho"
    title = "Kikōhō"
    hint = "Hands together, aim forward: one complete blast"
    order = 4
    replaces_person = False

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        audio.stop("kikoho_release")
        self.phase = "idle"
        self.window = PoseWindow(3, 1)
        self.t0 = 0.0
        self.origin = (0.0, 0.0)
        self.shoulder = 80.0

    @property
    def status(self) -> str:
        if self.phase == "firing":
            return "Kikōhō! One blast; Escape cancels."
        return "Hands together at chest height, aimed at the camera. Return fires once."

    def pose_ok(self, ctx: FrameContext) -> bool:
        return kikoho_pose(ctx.hands, ctx.pose_landmarks, ctx.pose_confidence) and aimed_at_camera(ctx.pose_world_landmarks, ctx.pose_confidence)

    def update(self, ctx: FrameContext) -> np.ndarray:
        if "escape" in ctx.keys:
            self.reset()
            self.window.arm_release()
            return ctx.frame
        if self.phase == "idle":
            pose_ok = fresh_tracking(ctx) and self.pose_ok(ctx)
            self.window.update(pose_ok, ctx.time, observation_id(ctx))
            report_pose(ctx.debug, self.id, pose_ok, self.window)
            if self.window.fired or "return" in ctx.keys:
                self.phase = "firing"
                self.t0 = ctx.time
                self.window.arm_release()
                self.origin, self.shoulder = hand_anchor(ctx)
                audio.play("kikoho_release")
        if self.phase == "idle":
            return ctx.frame
        elapsed = ctx.time - self.t0
        if elapsed >= CLIP_SECONDS:
            self.reset()
            self.window.arm_release()
            return ctx.frame
        # One expanding impact followed by a dying glow, never a waiting core
        # or a repeated pulse. The glow ends with the selected voice/SFX clip.
        progress = min(1.0, elapsed / EXPAND_SECONDS)
        tail = max(0.0, (elapsed - EXPAND_SECONDS) / (CLIP_SECONDS - EXPAND_SECONDS))
        strength = (1.0 - tail) ** 1.5
        return square_blast(ctx.frame, self.origin, progress, strength, self.shoulder)
