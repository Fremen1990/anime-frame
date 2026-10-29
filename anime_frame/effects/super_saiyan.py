"""Gold hair and a live, persistent silhouette aura."""

from __future__ import annotations

import cv2
import numpy as np

from anime_frame import audio
from anime_frame.effects.base import Effect, FrameContext
from anime_frame.pose import PoseWindow, report_pose, super_saiyan_pose
from anime_frame.vfx import feather, screen_blend, silhouette_aura

POWER_UP = 0.7
POWER_DOWN = 0.4


def golden_hair(frame: np.ndarray, hair_mask: np.ndarray | None, face: np.ndarray | None, strength: float) -> np.ndarray:
    """Gold on the hair only, with a soft upward fringe. Skin below the forehead stays as it is."""
    if hair_mask is None or face is None or len(face) <= 152 or strength <= 0:
        return frame
    height, width = frame.shape[:2]
    face_height = float(np.linalg.norm(face[10] - face[152]))
    if face_height <= 1:
        return frame
    y_limit = int(np.clip(face[10, 1], 0, height))
    y0 = max(0, int(face[10, 1] - 0.9 * face_height))
    x0 = max(0, int(face[10, 0] - 0.9 * face_height))
    x1 = min(width, int(face[10, 0] + 0.9 * face_height))
    if y_limit <= y0 or x1 <= x0:
        return frame
    local_frame = frame[y0:y_limit, x0:x1]
    alpha = np.clip(np.asarray(hair_mask[y0:y_limit, x0:x1], np.float32), 0.0, 1.0)
    alpha = feather(alpha, 6.0) * np.clip(strength, 0, 1)
    if not np.any(alpha > 0.04):
        return frame
    hsv = cv2.cvtColor(local_frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    gold_hsv = hsv.copy()
    gold_hsv[:, :, 0] = 23
    gold_hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 0.4 + 115, 0, 255)
    gold_hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.1 + 30, 0, 255)
    gold = cv2.cvtColor(gold_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    local_height, local_width = alpha.shape
    rows = np.linspace(0.0, 1.0, local_height, dtype=np.float32)[:, None]
    top = np.clip(rows / 0.18, 0.0, 1.0)
    bottom = np.clip((1.0 - rows) / 0.28, 0.0, 1.0)
    edge_fade = (top * top * (3.0 - 2.0 * top)) * (bottom * bottom * (3.0 - 2.0 * bottom))
    mix = np.clip(alpha * 0.7, 0.0, 1.0) * edge_fade
    out = np.clip(local_frame * (1.0 - mix[:, :, None]) + gold * mix[:, :, None], 0, 255).astype(np.uint8)

    lift = max(10, int(face_height * 0.42 * strength))
    shifted = cv2.warpAffine(alpha, np.float32([[1, 0, 0], [0, 1, -lift]]), (local_width, local_height))
    clear = 1.0 - np.clip(alpha, 0.0, 1.0)
    haze = np.maximum(feather(shifted, 8.0), feather(alpha, 6.0) * 0.85) * clear * 0.66 * edge_fade
    light = (np.array([52, 196, 255], np.float32) / 255.0) * haze[:, :, None]
    out = screen_blend(out, light)
    result = frame.copy()
    result[y0:y_limit, x0:x1] = out
    return result


class SuperSaiyan(Effect):
    id = "super_saiyan"
    title = "Super Saiyan"
    hint = "Hold both fists beside your shoulders"
    order = 2
    replaces_person = False
    needs_hair_mask = True

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        audio.stop_saiyan()
        self.phase = "idle"
        self.t0 = 0.0
        self.fade_from = 1.0
        self.window = PoseWindow()

    def update(self, ctx: FrameContext) -> np.ndarray:
        if "escape" in ctx.keys and self.phase == "idle":
            self.window.arm_release()
            return ctx.frame
        fresh = ctx.landmarks_at is None or ctx.time - ctx.landmarks_at <= 0.3
        pose_ok = fresh and super_saiyan_pose(ctx.hands, ctx.pose_landmarks, ctx.pose_confidence)
        self.window.update(pose_ok, ctx.time, ctx.landmark_timestamp_ms if fresh else None)
        report_pose(ctx.debug, self.id, pose_ok, self.window)
        if "escape" in ctx.keys and self.phase != "idle":
            self._fade(ctx.time)
        elif self.window.fired or "return" in ctx.keys:
            if "return" in ctx.keys:
                self.window.arm_release()
            if self.phase == "idle" or self.phase == "fading":
                self.phase = "powering"
                self.t0 = ctx.time
                audio.start_saiyan()
            elif self.phase in ("powering", "active"):
                self._fade(ctx.time)
        if self.phase == "idle":
            return ctx.frame
        if self.phase == "powering":
            strength = min(1.0, (ctx.time - self.t0) / POWER_UP)
            if strength >= 1:
                self.phase = "active"
        elif self.phase == "fading":
            strength = self.fade_from * max(0.0, 1.0 - (ctx.time - self.t0) / POWER_DOWN)
            if strength <= 0:
                self.phase = "idle"
                return ctx.frame
        else:
            strength = 1.0
        out = silhouette_aura(ctx.frame, ctx.mask, ctx.time, strength)
        if ctx.hair_mask is not None and ctx.hair_mask_at is not None and ctx.time - ctx.hair_mask_at <= 0.25:
            out = golden_hair(out, ctx.hair_mask, ctx.face, strength)
        return out

    def _fade(self, now: float) -> None:
        audio.stop_saiyan()
        self.fade_from = min(1.0, max(0.0, (now - self.t0) / POWER_UP)) if self.phase == "powering" else 1.0
        self.phase = "fading"
        self.t0 = now
