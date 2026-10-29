"""Staged beam lifecycle: hands forward, cup at the side, then thrust forward."""

from __future__ import annotations

from abc import abstractmethod

import numpy as np

from anime_frame import audio
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.pose import ForwardBaseline, PoseWindow, aimed_at_camera, forward_baseline, hands_in_front, pushed_forward, report_pose
from anime_frame.vfx import camera_blast, charge_core

BEAM_SECONDS = 0.55
FADE_SECONDS = 0.25
TRACKING_TIMEOUT = 0.3


def observation_id(ctx: FrameContext) -> int | float:
    if ctx.landmark_timestamp_ms is not None:
        return ctx.landmark_timestamp_ms
    return ctx.landmarks_at if ctx.landmarks_at is not None else ctx.time


def fresh_tracking(ctx: FrameContext) -> bool:
    return ctx.landmarks_at is None or 0 <= ctx.time - ctx.landmarks_at <= TRACKING_TIMEOUT


def hand_anchor(ctx: FrameContext) -> tuple[tuple[float, float], float]:
    body = ctx.pose_landmarks
    if body is not None and len(body) >= 17 and np.isfinite(body[[11, 12, 15, 16]]).all():
        point = (body[15] + body[16]) / 2.0
        return (float(point[0]), float(point[1])), max(8.0, float(np.linalg.norm(body[11] - body[12])))
    height, width = ctx.frame.shape[:2]
    return (width * 0.5, height * 0.58), width * 0.17


class AttackEffect(Effect):
    replaces_person = False
    core_color = (255, 220, 175)
    charge_sound: str
    release_sound: str

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        audio.stop(f"{self.id}_hold")
        audio.stop(self.charge_sound)
        audio.stop(self.release_sound)
        self._clear_state()

    def _clear_state(self) -> None:
        self.phase = "idle"
        self.window = PoseWindow()
        self.side_window = PoseWindow(4, 2)
        self.push_window = PoseWindow(2, 1)
        self.t0 = 0.0
        self.keyboard_charge = False
        self.baseline: ForwardBaseline | None = None
        self.origin = (0.0, 0.0)
        self.shoulder = 80.0
        self.last_valid = 0.0
        self.last_motion_observation: int | float | None = None

    @property
    def status(self) -> str:
        return {
            "idle": "1/3  Hands together toward the camera to begin. Return also starts.",
            "charging": "2/3  Cup your hands beside either side of your torso. Return advances.",
            "ready": "3/3  Push both hands toward the camera to fire. Return fires. Esc cancels.",
            "firing": "Blast!",
            "fading": "Lower your hands before starting again.",
        }[self.phase]

    @abstractmethod
    def pose_ok(self, ctx: FrameContext) -> bool: ...

    def forward_pose(self, ctx: FrameContext) -> bool:
        return hands_in_front(ctx.pose_landmarks, ctx.pose_confidence) and aimed_at_camera(ctx.pose_world_landmarks, ctx.pose_confidence)

    def blast(self, frame: np.ndarray, progress: float, strength: float) -> np.ndarray:
        return camera_blast(frame, self.origin, progress, strength, self.core_color)

    def _anchor(self, ctx: FrameContext) -> None:
        self.origin, self.shoulder = hand_anchor(ctx)

    def _start_charge(self, ctx: FrameContext, keyboard: bool = False) -> None:
        audio.stop(self.release_sound)
        self.phase = "charging"
        self.t0 = ctx.time
        self.last_valid = ctx.time
        self.last_motion_observation = observation_id(ctx)
        self.keyboard_charge = keyboard
        self._anchor(ctx)
        audio.play(self.charge_sound)

    def _ready(self, ctx: FrameContext) -> None:
        self.phase = "ready"
        self.t0 = ctx.time
        self.baseline = forward_baseline(ctx.pose_world_landmarks, ctx.pose_confidence) if fresh_tracking(ctx) else None
        self.last_motion_observation = observation_id(ctx)
        self._anchor(ctx)
        # Each physical stage owns its sound. Moving to the side establishes
        # the hold immediately, even if the opening clip has not finished.
        audio.stop(self.charge_sound)
        audio.loop(f"{self.id}_hold")

    def _fire(self, ctx: FrameContext) -> None:
        audio.stop(f"{self.id}_hold")
        audio.stop(self.charge_sound)
        self.phase = "firing"
        self.t0 = ctx.time
        self.window.arm_release()
        self._anchor(ctx)
        audio.play(self.release_sound)

    def update(self, ctx: FrameContext) -> np.ndarray:
        if "escape" in ctx.keys:
            self.reset()
            self.window.arm_release()
            return ctx.frame
        if "return" in ctx.keys:
            if self.phase == "idle":
                self.window.arm_release()
                self._start_charge(ctx, keyboard=True)
            elif self.phase == "charging":
                self.keyboard_charge = True
                self._ready(ctx)
            elif self.phase == "ready":
                self._fire(ctx)

        fresh = fresh_tracking(ctx)
        observation = observation_id(ctx)
        if self.phase == "idle":
            pose_ok = fresh and self.forward_pose(ctx)
            self.window.update(pose_ok, ctx.time, observation)
            report_pose(ctx.debug, self.id, pose_ok, self.window)
            if self.window.fired:
                self._start_charge(ctx)
        elif self.phase in ("charging", "ready"):
            current = forward_baseline(ctx.pose_world_landmarks, ctx.pose_confidence)
            if fresh and current is not None and observation != self.last_motion_observation:
                self.last_motion_observation = observation
                self.last_valid = ctx.landmarks_at if ctx.landmarks_at is not None else ctx.time
                self._anchor(ctx)
                if self.phase == "charging":
                    side_pose = self.pose_ok(ctx) and not aimed_at_camera(ctx.pose_world_landmarks, ctx.pose_confidence)
                    self.side_window.update(side_pose, ctx.time, observation)
                    if self.side_window.fired:
                        self._ready(ctx)
                else:
                    if self.baseline is None and self.pose_ok(ctx) and not aimed_at_camera(ctx.pose_world_landmarks, ctx.pose_confidence):
                        self.baseline = current
                    pushed = self.baseline is not None and self.forward_pose(ctx) and pushed_forward(self.baseline, ctx.pose_world_landmarks, ctx.pose_confidence)
                    self.push_window.update(pushed, ctx.time, observation)
                    if self.push_window.fired:
                        self._fire(ctx)
            # Keyboard demonstrations work without a person. Gesture sessions
            # cancel on lost depth, including repeatedly replayed observations.
            if self.phase in ("charging", "ready") and not self.keyboard_charge and ctx.time - self.last_valid > TRACKING_TIMEOUT:
                self.reset()
                self.window.arm_release()

        if self.phase in ("firing", "fading"):
            elapsed = ctx.time - self.t0
            if elapsed >= BEAM_SECONDS + FADE_SECONDS:
                self._clear_state()
                self.window.arm_release()
            elif elapsed >= BEAM_SECONDS:
                self.phase = "fading"
        if self.phase == "idle":
            return ctx.frame
        if self.phase in ("charging", "ready"):
            strength = min(1.0, (ctx.time - self.t0) / 0.7) if self.phase == "charging" else 1.0
            return charge_core(ctx.frame, self.origin, max(48.0, self.shoulder * 0.6), strength, self.core_color)
        elapsed = ctx.time - self.t0
        progress = min(1.0, elapsed / BEAM_SECONDS)
        strength = min(1.0, max(0.0, (BEAM_SECONDS + FADE_SECONDS - elapsed) / FADE_SECONDS))
        return self.blast(ctx.frame, progress, strength)
