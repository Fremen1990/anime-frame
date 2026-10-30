"""Continuous golden flames and a textured, head-anchored hair transformation."""
from __future__ import annotations

import cv2
import numpy as np

from anime_frame import audio
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.hair_geometry import head_anchor, head_bounds, warp_mask
from anime_frame.pose import PoseWindow, report_pose, super_saiyan_pose
from anime_frame.vfx import feather, silhouette_aura

POWER_UP = 1.7
POWER_DOWN = 0.4


def golden_hair(frame, hair_mask, face, strength, *, bounds=None):
    anchor = head_anchor(face)
    if hair_mask is None or anchor is None or strength <= 0:
        return frame
    left, top, right, bottom = bounds or head_bounds(anchor, frame.shape)
    if right <= left or bottom <= top:
        return frame
    local = frame[top:bottom, left:right]
    alpha = hair_mask if bounds is not None else hair_mask[top:bottom, left:right]
    alpha = np.clip(alpha, 0, 1).astype(np.float32)
    forehead = anchor[0] - (left, top)
    height = float(np.linalg.norm(anchor[1] - anchor[0]))
    down = (anchor[1] - anchor[0]) / height
    ys, xs = np.mgrid[:bottom-top, :right-left].astype(np.float32)
    vertical = (xs-forehead[0]) * down[0] + (ys-forehead[1]) * down[1]
    # Only the crown above the forehead is eligible. This also excludes skin,
    # facial hair and the facial oval, independent of imperfect segmentation.
    protection = np.clip(-vertical / max(2.0, height * 0.035), 0, 1)
    alpha *= protection
    if not np.any(alpha > 0.08):
        return frame
    hsv = cv2.cvtColor(local, cv2.COLOR_BGR2HSV)
    gold = hsv.astype(np.float32)
    # Keep the real hair's light and dark strands. Only the hue moves toward gold.
    gold[:, :, 0] = 23
    gold[:, :, 1] = np.clip(gold[:, :, 1] * 0.45 + 90, 0, 255)
    gold[:, :, 2] = np.clip(gold[:, :, 2] * 1.02 + 6, 0, 255)
    gold = cv2.cvtColor(gold.astype(np.uint8), cv2.COLOR_HSV2BGR)
    blend = feather(alpha, 0.8) * float(np.clip(strength, 0.0, 1.0))
    colored = local * (1 - blend[:, :, None]) + gold * blend[:, :, None]
    result = frame.copy()
    result[top:bottom, left:right] = np.clip(colored, 0, 255).astype(np.uint8)
    return result


class HairTreatment:
    def __init__(self):
        self.mask = None
        self.anchor = None
        self.origin = (0, 0)
        self.stamp = None
        self.last_time = None
        self.visibility = 0.0

    def apply(self, frame, ctx, strength):
        current = head_anchor(ctx.face)
        fresh_face = ctx.landmarks_at is None or 0 <= ctx.time - ctx.landmarks_at <= 0.25
        if current is None or not fresh_face:
            self.__init__()
            return frame
        bounds = head_bounds(current, frame.shape)
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            return frame
        dt = max(0.0, ctx.time - self.last_time) if self.last_time is not None else 0.0
        self.last_time = ctx.time
        prior = None
        if self.mask is not None:
            prior = warp_mask(self.mask, self.anchor, self.origin, current, bounds)
        fresh_mask = ctx.hair_mask is not None and ctx.hair_mask_at is not None and 0 <= ctx.time - ctx.hair_mask_at < 0.25
        if fresh_mask and ctx.hair_mask_at != self.stamp:
            reference = ctx.hair_reference_anchor if ctx.hair_reference_anchor is not None else current
            incoming = warp_mask(ctx.hair_mask, reference, (0, 0), current, bounds)
            elapsed = ctx.hair_mask_at - self.stamp if self.stamp is not None else 1.0
            alpha = 1 - np.exp(-max(0.0, elapsed) / 0.08)
            self.mask = incoming if prior is None else prior * (1-alpha) + incoming * alpha
            self.stamp = ctx.hair_mask_at
        elif prior is not None:
            self.mask = prior
        self.anchor, self.origin = current, (left, top)
        age = ctx.time - self.stamp if self.stamp is not None else 1.0
        target = float(np.clip((0.25-age) / 0.10, 0, 1))
        # Fast confidence fade, gradual recovery; stale masks never remain visible.
        self.visibility = min(target, self.visibility + dt / 0.12)
        if age >= 0.25:
            self.mask = None
            self.visibility = 0.0
            return frame
        return golden_hair(frame, self.mask, ctx.face, strength * self.visibility, bounds=bounds)


class SuperSaiyan(Effect):
    id = "super_saiyan"
    title = "Super Saiyan"
    hint = "Hold both fists beside your shoulders"
    order = 2
    replaces_person = False
    needs_hair_mask = True

    def __init__(self):
        self.handle = None
        self.reset()

    def reset(self):
        audio.fade_stop(self.handle, 0.02)
        self.handle = None
        self.phase = "idle"
        self.t0 = 0.0
        self.fade_from = 1.0
        self.strength = 0.0
        self.window = PoseWindow()
        self.hair = HairTreatment()
        self.flow_started = 0.0

    def update(self, ctx: FrameContext) -> np.ndarray:
        if "escape" in ctx.keys and self.phase == "idle":
            self.window.arm_release()
            return ctx.frame
        fresh = ctx.landmarks_at is None or 0 <= ctx.time - ctx.landmarks_at <= 0.3
        pose_ok = fresh and super_saiyan_pose(ctx.hands, ctx.pose_landmarks, ctx.pose_confidence)
        self.window.update(pose_ok, ctx.time, ctx.landmark_timestamp_ms if fresh else None)
        report_pose(ctx.debug, self.id, pose_ok, self.window)
        if "escape" in ctx.keys and self.phase not in ("idle", "fading"):
            self._fade(ctx.time)
        elif self.window.fired or "return" in ctx.keys:
            if "return" in ctx.keys:
                self.window.arm_release()
            if self.phase in ("idle", "fading"):
                self.phase = "powering"
                self.t0 = self.flow_started = ctx.time
                self.handle = audio.start_cue(self.id)
                self.hair = HairTreatment()
            elif self.phase in ("powering", "active"):
                self._fade(ctx.time)
        if self.phase == "idle":
            return ctx.frame
        snapshot = audio.playback_snapshot(self.handle)
        elapsed = snapshot.elapsed if snapshot is not None else ctx.time - self.flow_started
        flare = 0.0
        if self.phase == "powering":
            progress = min(1.0, elapsed / POWER_UP)
            self.strength = progress * progress * (3 - 2 * progress)
            peak = snapshot.opening_peak if snapshot is not None else 0.25
            flare = max(0, 1 - abs(elapsed - peak) / 0.10) * 0.65
            if progress >= 1:
                self.phase = "active"
        elif self.phase == "fading":
            self.strength = self.fade_from * max(0, 1 - (ctx.time - self.t0) / POWER_DOWN)
            if self.strength <= 0:
                self.phase = "idle"
                self.hair = HairTreatment()
                return ctx.frame
        else:
            self.strength = 1.0
        out = silhouette_aura(ctx.frame, ctx.mask, ctx.time-self.flow_started, self.strength + flare)
        # Slightly faster hair reveal, still tied to the same audible entrance.
        hair_strength = min(1.0, self.strength * 1.35)
        return self.hair.apply(out, ctx, hair_strength)

    def _fade(self, now):
        audio.fade_stop(self.handle, POWER_DOWN)
        self.fade_from = self.strength
        self.phase, self.t0 = "fading", now
