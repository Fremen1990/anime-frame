"""Effect interface and the per-frame context passed into update."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class FrameContext:
    frame: np.ndarray
    mask: np.ndarray | None
    background: np.ndarray | None
    time: float
    hands: list[np.ndarray] = field(default_factory=list)
    face: np.ndarray | None = None
    pose_landmarks: np.ndarray | None = None
    keys: set[str] = field(default_factory=set)
    debug: bool = False
    landmarks_at: float | None = None
    landmark_timestamp_ms: int | None = None
    hand_world_landmarks: list[np.ndarray] = field(default_factory=list)
    pose_world_landmarks: np.ndarray | None = None
    pose_confidence: np.ndarray | None = None
    hair_mask: np.ndarray | None = None
    hair_mask_at: float | None = None


class Effect(ABC):
    id: str
    title: str
    hint: str
    order: int
    replaces_person: bool
    needs_hair_mask = False

    @property
    def status(self) -> str:
        """Optional guidance displayed only in the chooser."""
        return ""

    @abstractmethod
    def reset(self) -> None:
        """Drop animation state and return to live video on the next update."""

    @abstractmethod
    def update(self, ctx: FrameContext) -> np.ndarray:
        """Return the BGR frame to show and to send. Do not open windows, cameras, or files."""
