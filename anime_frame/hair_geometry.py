"""Head-relative geometry shared by hair inference and compositing."""
from __future__ import annotations
import cv2
import numpy as np


def head_anchor(face: np.ndarray | None) -> np.ndarray | None:
    if face is None or len(face) <= 152:
        return None
    top, chin = np.asarray(face[[10, 152], :2], np.float32)
    axis = chin - top
    if not np.isfinite(axis).all() or np.linalg.norm(axis) < 5:
        return None
    side = np.array((axis[1], -axis[0]), np.float32) * 0.5
    return np.asarray((top, chin, top + side), np.float32)


def head_bounds(anchor: np.ndarray, shape) -> tuple[int, int, int, int]:
    height = float(np.linalg.norm(anchor[1] - anchor[0]))
    top = anchor[0]
    down = (anchor[1] - top) / height
    side = np.array((down[1], -down[0]))
    corners = np.array([top + side * x * height + down * y * height for x in (-0.9, 0.9) for y in (-1.1, 0.08)])
    left, upper = np.floor(corners.min(axis=0)).astype(int)
    right, bottom = np.ceil(corners.max(axis=0)).astype(int)
    return max(0, left), max(0, upper), min(shape[1], right), min(shape[0], bottom)


def warp_mask(mask, source_anchor, source_origin, target_anchor, bounds):
    left, top, right, bottom = bounds
    transform = cv2.getAffineTransform(np.asarray(source_anchor, np.float32), np.asarray(target_anchor, np.float32))
    transform[:, 2] += transform[:, :2] @ np.asarray(source_origin) - (left, top)
    return cv2.warpAffine(mask, transform, (right-left, bottom-top), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
