"""Soft light shared by effects. Colors are OpenCV BGR.

Energy is a blurred falloff composited with a screen blend. Spikes and
lightning are drawn thick and then blurred, so they read as flames rather
than wireframe.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

_GOLD = np.array((0.18, 0.68, 1.0), np.float32)
_WARM_WHITE = np.array((0.86, 0.96, 1.0), np.float32)
_BEAM_BLUE = np.array((1.0, 0.78, 0.46), np.float32)
_BEAM_CORE = np.array((1.0, 0.96, 0.90), np.float32)
_BLAST_GOLD = np.array((0.40, 0.74, 1.0), np.float32)
_ARC = np.array((1.0, 0.88, 0.72), np.float32)


def feather(mask: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    return np.clip(cv2.GaussianBlur(np.asarray(mask, np.float32), (0, 0), sigma), 0.0, 1.0)


def screen_blend(base: np.ndarray, light: np.ndarray) -> np.ndarray:
    """Screen `light` (float image, 0..1 per channel) over an 8-bit BGR image."""
    image = base.astype(np.float32)
    mixed = image + (255.0 - image) * np.clip(light, 0.0, 1.0)
    return np.clip(np.rint(mixed), 0, 255).astype(np.uint8)


def _smooth(progress: float) -> float:
    t = float(np.clip(progress, 0.0, 1.0))
    eased = t * t * (3.0 - 2.0 * t)
    return max(eased, 0.045)


def _crop_bounds(height: int, width: int, x: float, y: float, pad: int) -> tuple[int, int, int, int] | None:
    left, top = max(0, int(x) - pad), max(0, int(y) - pad)
    right, bottom = min(width, int(x) + pad + 1), min(height, int(y) + pad + 1)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _outward_normals(points: np.ndarray) -> np.ndarray:
    count = len(points)
    tangent = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    normal = np.stack((-tangent[:, 1], tangent[:, 0]), axis=1)
    centroid = points.mean(axis=0)
    inward = np.sum(normal * (points - centroid), axis=1) < 0
    normal[inward] *= -1
    length = np.linalg.norm(normal, axis=1)
    length[length < 1e-3] = 1.0
    return normal / length[:, None]


def _point(pos: np.ndarray, width: int, height: int) -> tuple[int, int]:
    return int(np.clip(pos[0], -40, width + 40)), int(np.clip(pos[1], -40, height + 40))


def _electricity(small: np.ndarray, now: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Persistent, upward-flowing flames in body coordinates; sparse soft arcs.

    `small` is the person mask already reduced to a third of the crop.
    """
    points = cv2.findNonZero(small)
    if points is None:
        return None
    bx, by, bw, bh = cv2.boundingRect(points)
    h, w = small.shape
    x = (np.arange(w, dtype=np.float32)[None, :] - (bx + bw * 0.5)) / max(bw, 1)
    y = (np.arange(h, dtype=np.float32)[:, None] - by) / max(bh, 1)
    flow = y + np.float32(now * 0.32)
    noise = (np.sin(x * 21 + flow * 9) + 0.5 * np.sin(x * 43 - flow * 14 + 1.7) + 0.3 * np.sin(x * 71 + flow * 22)) / 1.8
    radius = max(5.0, bh * 0.12) * (0.45 + 0.55 * ((noise + 1) * 0.5) ** 2)
    dist = cv2.distanceTransform((small == 0).astype(np.uint8), cv2.DIST_L2, 3)
    flame = np.clip(1 - dist / radius, 0, 1).astype(np.float32)
    flame[small > 0] = 0
    flame = cv2.GaussianBlur(flame, (0, 0), 0.85)
    accents = np.zeros((h, w), np.float32)
    # Repeatable particle lifetimes and positions, with zero intensity at wrap.
    for index in range(9):
        phase = (now * 0.22 + index * 0.137) % 1
        side = -1 if index % 2 else 1
        px = bx + bw * 0.5 + side * bw * (0.55 + 0.08 * np.sin(index * 2.4 + now * 0.8))
        py = by + bh * (1.05 - phase * 1.2)
        brightness = float(np.sin(np.pi * phase) ** 2) * 0.65
        cv2.circle(accents, (int(px), int(py)), 1, brightness, -1, cv2.LINE_AA)
    cycle = int(now / 1.8)
    life = (now % 1.8) / 0.18
    if life < 1:
        generator = np.random.default_rng(cycle & 0xFFFF)
        contours, _ = cv2.findContours(small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            contour = max(contours, key=cv2.contourArea)[:, 0, :].astype(np.float32)
            normals = _outward_normals(contour)
            for _ in range(2):
                index = int(generator.integers(len(contour)))
                pos = contour[index] + normals[index] * 5
                poly = [tuple(pos.astype(int))]
                for _ in range(5):
                    pos = pos + generator.normal(size=2) * 5 + normals[index] * 2
                    poly.append(tuple(pos.astype(int)))
                cv2.polylines(accents, [np.asarray(poly, np.int32)], False, float(np.sin(np.pi * life) ** 2), 1, cv2.LINE_AA)
    accents[small > 0] = 0
    accents = cv2.GaussianBlur(accents, (0, 0), 0.65)
    return flame, accents


def silhouette_aura(frame: np.ndarray, mask: np.ndarray, now: float, strength: float) -> np.ndarray:
    """Wide gold light around the person. The middle of the body stays the photo."""
    if mask is None or strength <= 0:
        return frame
    mask2 = np.squeeze(mask)
    if mask2.ndim != 2:
        return frame
    binary_u8 = (mask2 > 0.5).astype(np.uint8)
    points = cv2.findNonZero(binary_u8)
    if points is None:
        return frame
    x, y, w, h = cv2.boundingRect(points)
    wide_sigma = 28.0
    pad = int(wide_sigma * 3.1)
    left, top = max(0, x - pad), max(0, y - pad)
    right, bottom = min(frame.shape[1], x + w + pad), min(frame.shape[0], y + h + pad)
    local_u8 = binary_u8[top:bottom, left:right]
    if local_u8.size == 0:
        return frame
    local_frame = frame[top:bottom, left:right]
    crop_h, crop_w = local_u8.shape
    small_w, small_h = max(2, crop_w // 3), max(2, crop_h // 3)
    small = cv2.resize(local_u8, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    small_f = small.astype(np.float32)
    # Blur sigmas are in the reduced image, so they match the old full-crop falloff.
    wide = cv2.GaussianBlur(small_f, (0, 0), wide_sigma / 3.0)
    near = cv2.GaussianBlur(small_f, (0, 0), 9.0 / 3.0)
    protect = np.clip((near - 0.58) / 0.42, 0.0, 1.0)
    veil = np.clip(wide * (1.0 - protect), 0.0, 1.0)
    edge = np.clip(near * (1.0 - protect), 0.0, 1.0)
    pulse = 0.88 + 0.12 * (0.5 + 0.5 * np.sin(now * 2.2))
    amount = float(np.clip(strength, 0.0, 1.5)) * pulse
    light = _GOLD * veil[:, :, None] * (0.9 * amount) + _WARM_WHITE * edge[:, :, None] * (0.34 * amount)
    electric = _electricity(small, now)
    if electric is not None:
        flame, arc = electric
        light += _GOLD * flame[:, :, None] * (1.25 * amount)
        light += _ARC * arc[:, :, None] * (1.05 * amount)
    deep = near >= 0.985
    light[deep] = 0
    preview = cv2.resize(local_frame, (small_w, small_h), interpolation=cv2.INTER_AREA)
    lit = cv2.resize(screen_blend(preview, np.clip(light, 0.0, 1.0)), (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
    # The body interior stays the original photo. copyTo is much faster than boolean indexing.
    interior = cv2.resize((deep.astype(np.uint8) * 255), (crop_w, crop_h), interpolation=cv2.INTER_NEAREST)
    cv2.copyTo(local_frame, interior, lit)
    result = frame.copy()
    result[top:bottom, left:right] = lit
    return result


def charge_core(frame: np.ndarray, center: tuple[float, float], radius: float, strength: float, color: tuple[int, int, int]) -> np.ndarray:
    """A radial glow. Bright in the middle, gone a short distance out."""
    if strength <= 0:
        return frame
    sigma = max(14.0, float(radius) * 0.85)
    reach = sigma * 3.8
    bounds = _crop_bounds(frame.shape[0], frame.shape[1], center[0], center[1], int(reach))
    if bounds is None:
        return frame
    left, top, right, bottom = bounds
    ys = np.arange(top, bottom, dtype=np.float32)[:, None]
    xs = np.arange(left, right, dtype=np.float32)[None, :]
    dist2 = (xs - np.float32(center[0])) ** 2 + (ys - np.float32(center[1])) ** 2
    dist = np.sqrt(dist2)
    halo = np.exp(-dist2 / (2.0 * sigma * sigma))
    core = np.exp(-dist2 / (2.0 * (sigma * 0.34) ** 2))
    fade = np.clip((np.float32(reach) - dist) / max(8.0, sigma * 0.9), 0.0, 1.0)
    fade = fade * fade * (3.0 - 2.0 * fade)
    tint = np.asarray(color, np.float32) / 255.0
    amount = float(np.clip(strength, 0.0, 1.5))
    light = tint * (0.78 * halo)[:, :, None] + _WARM_WHITE * (0.74 * core)[:, :, None]
    light *= fade[:, :, None]
    result = frame.copy()
    result[top:bottom, left:right] = screen_blend(frame[top:bottom, left:right], np.clip(light * amount, 0.0, 1.0))
    return result


def camera_blast(frame: np.ndarray, origin: tuple[float, float], progress: float, strength: float, color: tuple[int, int, int], initial_radius: float = 36.0) -> np.ndarray:
    """A wash of light that grows from the hands until it fills the frame."""
    if strength <= 0 or progress < 0:
        return frame
    shown = _smooth(progress)
    height, width = frame.shape[:2]
    small_h, small_w = max(1, height // 3), max(1, width // 3)
    ys = np.arange(small_h, dtype=np.float32)[:, None]
    xs = np.arange(small_w, dtype=np.float32)[None, :]
    dist = np.hypot(xs - np.float32(origin[0] / 3.0), ys - np.float32(origin[1] / 3.0)) * 3.0
    far = float(math.hypot(width, height))
    radius = max(initial_radius, far * shown)
    halo = np.exp(-(dist * dist) / (2.0 * (radius * 0.5) ** 2))
    core = np.exp(-(dist * dist) / (2.0 * (max(18.0, radius * 0.2)) ** 2))
    ring_at = radius * 0.78
    ring = np.exp(-((dist - ring_at) ** 2) / (2.0 * (max(14.0, radius * 0.07)) ** 2))
    tint = np.asarray(color, np.float32) / 255.0
    light = tint * (0.92 * halo + 0.5 * ring)[:, :, None] + _WARM_WHITE * (0.95 * core)[:, :, None]
    light *= float(np.clip(strength, 0.0, 1.5)) * (0.7 + 1.1 * shown)
    light = cv2.resize(np.clip(light, 0.0, 1.0), (width, height), interpolation=cv2.INTER_LINEAR)
    return screen_blend(frame, light)


def horizontal_beam(frame: np.ndarray, origin: tuple[float, float], side: int, progress: float, strength: float, width: float) -> np.ndarray:
    """A blue-white beam that fades across its width and at the tip."""
    if strength <= 0 or progress < 0:
        return frame
    height, frame_width = frame.shape[:2]
    x0 = float(np.clip(origin[0], 0, frame_width - 1))
    y0 = float(np.clip(origin[1], 0, height - 1))
    direction = np.float32(1 if side >= 0 else -1)
    reach = (frame_width - 1 - x0) if direction > 0 else x0
    length = max(1.0, float(reach) * _smooth(progress))
    sigma = max(16.0, float(width) * 0.36)
    pad = int(sigma * 3.2)
    tip_x = x0 + float(direction) * length
    left, right = int(min(x0, tip_x) - pad), int(max(x0, tip_x) + pad + 1)
    top, bottom = int(y0 - pad), int(y0 + pad + 1)
    left, top = max(0, left), max(0, top)
    right, bottom = min(frame_width, right), min(height, bottom)
    if right <= left or bottom <= top:
        return frame
    ys = np.arange(top, bottom, dtype=np.float32)[:, None]
    xs = np.arange(left, right, dtype=np.float32)[None, :]
    along = (xs - np.float32(x0)) * direction
    across2 = (ys - np.float32(y0)) ** 2
    ahead = np.maximum(along - np.float32(length), 0.0)
    behind = np.maximum(-along, 0.0)
    length_env = np.exp(-ahead * ahead / (2.0 * (sigma * 1.25) ** 2))
    length_env *= np.exp(-behind * behind / (2.0 * (sigma * 0.7) ** 2))
    halo = np.exp(-across2 / (2.0 * sigma * sigma))
    core = np.exp(-across2 / (2.0 * (sigma * 0.30) ** 2))
    tip = np.exp(-((xs - np.float32(tip_x)) ** 2 + across2) / (2.0 * (sigma * 0.95) ** 2))
    amount = float(np.clip(strength, 0.0, 1.5))
    light = _BEAM_BLUE * (0.58 * halo + 0.36 * tip)[:, :, None] + _BEAM_CORE * (0.74 * core)[:, :, None]
    light *= length_env[:, :, None] * amount
    result = frame.copy()
    result[top:bottom, left:right] = screen_blend(frame[top:bottom, left:right], np.clip(light, 0.0, 1.0))
    return result


def square_blast(frame: np.ndarray, origin: tuple[float, float], progress: float, strength: float, shoulder: float) -> np.ndarray:
    """A soft square of warm light, brightest at the center, growing toward the camera."""
    if strength <= 0 or progress < 0:
        return frame
    height, width = frame.shape[:2]
    cx, cy = float(origin[0]), float(origin[1])
    half = max(18.0, float(shoulder) * (0.42 + _smooth(progress) * 2.45))
    thick = max(10.0, half * 0.22)
    pad = int(half + thick * 4.5)
    bounds = _crop_bounds(height, width, cx, cy, pad)
    if bounds is None:
        return frame
    left, top, right, bottom = bounds
    # Evaluate the soft light on a small grid. Doing the exponential fields
    # at full 720p took almost an entire 50 ms frame budget on this Mac.
    ys = np.linspace(top, bottom - 1, max(2, (bottom - top) // 3), dtype=np.float32)[:, None]
    xs = np.linspace(left, right - 1, max(2, (right - left) // 3), dtype=np.float32)[None, :]
    cheb = np.maximum(np.abs(xs - np.float32(cx)), np.abs(ys - np.float32(cy)))
    ring = np.exp(-((cheb - np.float32(half)) ** 2) / (2.0 * thick * thick))
    fill = np.exp(-(cheb * cheb) / (2.0 * (half * 0.75) ** 2))
    core = np.exp(-(cheb * cheb) / (2.0 * (half * 0.22) ** 2))
    fade = np.clip((np.float32(pad) - np.hypot(xs - np.float32(cx), ys - np.float32(cy))) / max(8.0, thick * 2.0), 0.0, 1.0)
    fade = fade * fade * (3.0 - 2.0 * fade)
    amount = float(np.clip(strength, 0.0, 1.5))
    light = _BLAST_GOLD * (0.70 * ring + 0.18 * fill)[:, :, None] + _WARM_WHITE * (0.28 * core)[:, :, None]
    light *= amount * fade[:, :, None]
    light = cv2.GaussianBlur(light, (0, 0), 0.8)
    light = cv2.resize(light, (right - left, bottom - top), interpolation=cv2.INTER_LINEAR)
    result = frame.copy()
    result[top:bottom, left:right] = screen_blend(frame[top:bottom, left:right], np.clip(light, 0.0, 1.0))
    return result
