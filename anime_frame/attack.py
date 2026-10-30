"""Two-gesture beam with continuous audio, an anchored orb, and a visual tail."""

from __future__ import annotations

from abc import abstractmethod

import numpy as np

from anime_frame import audio
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.pose import ForwardBaseline, PoseWindow, aimed_at_camera, forward_baseline, hands_in_front, pushed_forward, report_pose
from anime_frame.vfx import camera_blast, charge_core

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


class MotionAnchor:
    """Render-time smoothing, independent of the gesture sampling cadence."""
    def __init__(self):
        self.point = None
        self.target = None
        self.velocity = np.zeros(2, np.float64)
        self.shoulder = 80.0
        self.stamp = None
        self.observation = None
        self.rendered_at = None

    def update(self, ctx):
        now = ctx.time
        dt = max(0.0, now - self.rendered_at) if self.rendered_at is not None else 0.0
        self.rendered_at = now
        if self.point is None:
            origin, self.shoulder = hand_anchor(ctx)
            self.point = self.target = np.asarray(origin, np.float64)
        identifier = observation_id(ctx)
        if fresh_tracking(ctx) and ctx.pose_landmarks is not None and identifier != self.observation:
            origin, shoulder = hand_anchor(ctx)
            stamp = ctx.landmarks_at if ctx.landmarks_at is not None else now
            point = np.asarray(origin, np.float64)
            if self.stamp is not None and stamp > self.stamp:
                velocity = (point - self.target) / (stamp - self.stamp)
                speed = float(np.linalg.norm(velocity))
                self.velocity = velocity * min(1.0, shoulder * 4.0 / max(speed, 1.0))
            self.target, self.stamp, self.observation = point, stamp, identifier
            self.shoulder += (shoulder - self.shoulder) * (1 - np.exp(-max(dt, 0.01) / 0.07))
        prediction = min(0.06, max(0.0, now - self.stamp)) if self.stamp is not None else 0.0
        target = self.target + self.velocity * prediction
        self.point = self.point + (target - self.point) * (1 - np.exp(-dt / 0.07))
        return (float(self.point[0]), float(self.point[1])), self.shoulder


class AttackEffect(Effect):
    replaces_person = False
    core_color = (255, 220, 175)

    def __init__(self) -> None:
        self.handle = None
        self.reset()

    def reset(self) -> None:
        audio.fade_stop(self.handle, 0.02)
        self._clear_state()

    def _clear_state(self) -> None:
        self.phase = "idle"
        self.window = PoseWindow(4, 3)
        self.side_missing_since: float | None = None
        self.push_window = PoseWindow(2, 1)
        self.t0 = 0.0
        self.keyboard_charge = False
        self.baseline: ForwardBaseline | None = None
        self.anchor = MotionAnchor()
        self.origin = (0.0, 0.0)
        self.shoulder = 80.0
        self.last_valid = 0.0
        self.last_motion_observation = None
        self.handle = None
        self.strength = 0.0
        self.radius = 48.0
        self.release_strength = 1.0
        self.release_radius = 48.0
        self.duration = audio.release_duration(self.id, 5.7024)

    @property
    def status(self) -> str:
        return {
            "idle": "Cup hands beside either side of your torso. Return also starts.",
            "charging": "Keep your hands cupped at your side while the orb grows.",
            "ready": "Push both hands toward the camera. Return fires. Escape cancels.",
            "firing": "Blast!",
            "fading": "Lower your hands before another attack.",
            "cancelling": "Charge cancelled. Lower your hands to try again.",
        }[self.phase]

    @abstractmethod
    def pose_ok(self, ctx: FrameContext) -> bool: ...

    def forward_pose(self, ctx: FrameContext) -> bool:
        return hands_in_front(ctx.pose_landmarks, ctx.pose_confidence) and aimed_at_camera(ctx.pose_world_landmarks, ctx.pose_confidence)

    def _start_charge(self, ctx, keyboard=False):
        self.phase, self.t0 = "charging", ctx.time
        self.keyboard_charge = keyboard
        self.last_valid = ctx.time
        self.last_motion_observation = observation_id(ctx)
        self.origin, self.shoulder = self.anchor.update(ctx)
        self.handle = audio.start_cue(self.id)

    def _ready(self, ctx):
        self.phase = "ready"
        self.side_missing_since = None
        if fresh_tracking(ctx):
            found = forward_baseline(ctx.pose_world_landmarks, ctx.pose_confidence)
            if found is not None:
                self.baseline = found
        self.last_motion_observation = observation_id(ctx)

    def _fire(self, ctx):
        self.phase, self.t0 = "firing", ctx.time
        self.release_strength, self.release_radius = self.strength, self.radius
        self.window.arm_release()
        audio.release_cue(self.handle)

    def _cancel(self, ctx):
        self.phase, self.t0 = "cancelling", ctx.time
        self.release_strength = self.strength
        audio.fade_stop(self.handle, 0.12)
        self.window.arm_release()

    def update(self, ctx: FrameContext) -> np.ndarray:
        if "escape" in ctx.keys:
            self.reset()
            self.window.arm_release()
            return ctx.frame
        if "return" in ctx.keys:
            if self.phase == "idle":
                self.window.arm_release()
                self._start_charge(ctx, keyboard=True)
            elif self.phase == "ready":
                self._fire(ctx)

        fresh = fresh_tracking(ctx)
        observation = observation_id(ctx)
        current = forward_baseline(ctx.pose_world_landmarks, ctx.pose_confidence) if fresh else None
        if self.phase == "idle":
            side = current is not None and self.pose_ok(ctx)
            self.window.update(side, ctx.time, observation)
            report_pose(ctx.debug, self.id, side, self.window)
            if self.window.fired:
                self._start_charge(ctx)
        elif self.phase in ("charging", "ready"):
            if current is not None and observation != self.last_motion_observation:
                self.last_motion_observation = observation
                self.last_valid = ctx.landmarks_at if ctx.landmarks_at is not None else ctx.time
                held = self.pose_ok(ctx)
                if self.phase == "charging" and not self.keyboard_charge:
                    # A centered push during the grow is an early release, not a queued blast.
                    if hands_in_front(ctx.pose_landmarks, ctx.pose_confidence) and not held:
                        self._cancel(ctx)
                    elif held:
                        self.side_missing_since = None
                        if ctx.time - self.t0 >= 0.7 - 1e-6:
                            self._ready(ctx)
                    else:
                        if self.side_missing_since is None:
                            self.side_missing_since = ctx.time
                        elif ctx.time - self.side_missing_since >= TRACKING_TIMEOUT:
                            self._cancel(ctx)
                elif self.phase == "ready":
                    if self.baseline is None and current is not None and not self.forward_pose(ctx):
                        self.baseline = current
                    pushed = self.baseline is not None and self.forward_pose(ctx) and pushed_forward(self.baseline, ctx.pose_world_landmarks, ctx.pose_confidence)
                    self.push_window.update(pushed, ctx.time, observation)
                    if self.push_window.fired:
                        self._fire(ctx)
            if self.phase == "charging" and self.keyboard_charge and ctx.time - self.t0 >= 0.7:
                self._ready(ctx)
            if self.phase in ("charging", "ready") and not self.keyboard_charge and ctx.time - self.last_valid > TRACKING_TIMEOUT:
                self._cancel(ctx)

        if self.phase == "idle":
            return ctx.frame
        snapshot = audio.playback_snapshot(self.handle)
        if self.phase in ("charging", "ready"):
            self.origin, self.shoulder = self.anchor.update(ctx)
            self.radius = max(48.0, self.shoulder * 0.6)
            elapsed = snapshot.elapsed if snapshot is not None else ctx.time - self.t0
            self.strength = min(1.0, elapsed / 0.7)
            return charge_core(ctx.frame, self.origin, self.radius, self.strength, self.core_color)
        if self.phase == "cancelling":
            strength = self.release_strength * max(0, 1 - (ctx.time - self.t0) / 0.12)
            if ctx.time - self.t0 >= 0.12:
                self._clear_state()
                self.window.arm_release()
                return ctx.frame
            return charge_core(ctx.frame, self.origin, self.radius, strength, self.core_color)

        elapsed = ctx.time - self.t0
        if snapshot is not None:
            elapsed = max(0.0, snapshot.release_elapsed) if snapshot.release_elapsed is not None else 0.0
        if elapsed >= self.duration:
            self._clear_state()
            self.window.arm_release()
            return ctx.frame
        if elapsed <= 0.12:
            self.origin, self.shoulder = self.anchor.update(ctx)
        handoff = min(1.0, elapsed / 0.12)
        handoff = handoff * handoff * (3 - 2 * handoff)
        progress = min(1.0, max(0.0, (elapsed - 0.12) / 0.55))
        amplitude = snapshot.amplitude if snapshot is not None else 1.0
        strength = self.release_strength * (1 - handoff) + handoff
        if elapsed > 0.67:
            fall = min(1.0, (elapsed - 0.67) / 0.53)
            strength *= 1 - 0.82 * fall * fall * (3 - 2 * fall)
        if elapsed >= 1.2:
            self.phase = "fading"
            strength *= max(0.0, (self.duration - elapsed) / max(0.1, self.duration - 1.2))
        strength *= 1 - handoff * 0.12 * (1 - amplitude)
        blast = camera_blast(ctx.frame, self.origin, progress, strength, self.core_color, initial_radius=self.release_radius * 1.7)
        if handoff < 1:
            import cv2
            core = charge_core(ctx.frame, self.origin, self.release_radius, self.release_strength, self.core_color)
            return cv2.addWeighted(core, 1-handoff, blast, handoff, 0)
        return blast
