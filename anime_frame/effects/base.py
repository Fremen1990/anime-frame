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


class Effect(ABC):
    id: str
    title: str
    hint: str
    order: int
    replaces_person: bool

    @abstractmethod
    def reset(self) -> None:
        """Drop animation state and return to live video on the next update."""

    @abstractmethod
    def update(self, ctx: FrameContext) -> np.ndarray:
        """Return the BGR frame to show and to send. Do not open windows, cameras, or files."""
