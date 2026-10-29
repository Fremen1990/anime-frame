"""Synthetic landmark tests. No camera and no window."""

from __future__ import annotations

import math
import unittest

import numpy as np

from anime_frame.pose import CHIN, FOREHEAD, instant_transmission_pose


def _hand() -> np.ndarray:
    hand = np.zeros((21, 2), dtype=np.float64)
    hand[0] = (0.0, 0.0)
    hand[5] = (0.0, 40.0)
    hand[6] = (0.0, 70.0)
    hand[7] = (1.0, 90.0)
    hand[8] = (2.0, 110.0)
    hand[9] = (8.0, 42.0)
    hand[10] = (8.0, 74.0)
    hand[11] = (9.0, 96.0)
    hand[12] = (10.0, 116.0)
    hand[13] = (20.0, 36.0)
    hand[14] = (24.0, 58.0)
    hand[15] = (22.0, 40.0)
    hand[16] = (16.0, 28.0)
    hand[17] = (30.0, 34.0)
    hand[18] = (34.0, 52.0)
    hand[19] = (30.0, 36.0)
    hand[20] = (26.0, 20.0)
    return hand


def _face_at(forehead: np.ndarray, height: float = 200.0) -> np.ndarray:
    face = np.zeros((478, 2), dtype=np.float64)
    face[FOREHEAD] = forehead
    face[CHIN] = np.asarray(forehead, dtype=np.float64) + np.array([0.0, height])
    return face


def _transform(points: np.ndarray, scale: float, rotation: float, mirror: bool, translate) -> np.ndarray:
    out = np.array(points, dtype=np.float64, copy=True)
    xy = out[:, :2]
    cosine, sine = math.cos(rotation), math.sin(rotation)
    rotation_matrix = np.array([[cosine, -sine], [sine, cosine]])
    xy = xy @ rotation_matrix.T
    if mirror:
        xy[:, 0] *= -1.0
    xy *= scale
    xy += np.asarray(translate, dtype=np.float64)
    out[:, :2] = xy
    return out


class InstantTransmissionPoseTests(unittest.TestCase):
    def test_fingers_together_on_the_forehead_are_accepted(self) -> None:
        hand = _hand()
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        self.assertTrue(instant_transmission_pose([hand], _face_at(midpoint)))

    def test_rotated_mirrored_scaled_hand_is_accepted(self) -> None:
        hand = _hand()
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        face = _face_at(midpoint)
        kwargs = dict(scale=1.7, rotation=0.8, mirror=True, translate=(25.0, -12.0))
        moved_hand = _transform(hand, **kwargs)
        moved_face = _transform(face, **kwargs)
        self.assertTrue(instant_transmission_pose([moved_hand], moved_face))

    def test_spread_v_is_rejected(self) -> None:
        hand = _hand()
        hand[9] = (36.0, 42.0)
        hand[10] = (52.0, 74.0)
        hand[11] = (64.0, 96.0)
        hand[12] = (78.0, 116.0)
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        self.assertFalse(instant_transmission_pose([hand], _face_at(midpoint)))

    def test_single_index_finger_is_rejected(self) -> None:
        hand = _hand()
        hand[11] = (7.0, 30.0)
        hand[12] = (6.0, 18.0)
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        self.assertFalse(instant_transmission_pose([hand], _face_at(midpoint)))

    def test_open_palm_is_rejected(self) -> None:
        hand = _hand()
        hand[16] = (24.0, 110.0)
        hand[20] = (34.0, 108.0)
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        self.assertFalse(instant_transmission_pose([hand], _face_at(midpoint)))

    def test_tips_down_at_the_chest_are_rejected(self) -> None:
        hand = _hand()
        midpoint = (hand[8, :2] + hand[12, :2]) / 2.0
        forehead = midpoint + np.array([0.0, -400.0])
        self.assertFalse(instant_transmission_pose([hand], _face_at(forehead)))

    def test_missing_face_is_rejected(self) -> None:
        self.assertFalse(instant_transmission_pose([_hand()], None))


if __name__ == "__main__":
    unittest.main()
