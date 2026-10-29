"""Effect timing without a camera or a window."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from anime_frame.effects.base import FrameContext
from anime_frame.effects.instant_transmission import DURATION, InstantTransmission, render_transmission


def _context(frame, mask, background, now, keys=None, hands=None, face=None, body=None) -> FrameContext:
    return FrameContext(
        frame=frame,
        mask=mask,
        background=background,
        time=now,
        hands=hands or [],
        face=face,
        pose_landmarks=body,
        keys=set(keys or []),
    )


class InstantTransmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.play = patch("anime_frame.audio.play")
        self.play.start()
        self.addCleanup(self.play.stop)

    def test_escape_returns_a_gone_state_to_live_and_return_starts_without_a_pose(self) -> None:
        effect = InstantTransmission()
        person = np.full((80, 80, 3), (20, 30, 40), np.uint8)
        background = np.full((80, 80, 3), (200, 10, 10), np.uint8)
        live = np.full((80, 80, 3), (1, 2, 3), np.uint8)
        mask = np.zeros((80, 80), np.float32)
        mask[20:70, 15:50] = 1.0

        started = effect.update(_context(person, mask, background, 0.0, keys={"return"}))
        self.assertEqual(effect.phase, "leaving")
        self.assertLess(float(np.median(started[40, 15:50, 0])), 80.0)

        gone = effect.update(_context(person, mask, background, DURATION))
        self.assertEqual(effect.phase, "gone")
        np.testing.assert_array_equal(gone, background)

        effect.update(_context(person, mask, background, DURATION, keys={"escape"}))
        self.assertEqual(effect.phase, "returning")

        restored = effect.update(_context(live, mask, background, DURATION * 2))
        self.assertEqual(effect.phase, "idle")
        np.testing.assert_array_equal(restored, live)

    def test_leave_fades_from_the_forehead_downward(self) -> None:
        person = np.full((90, 80, 3), (20, 30, 40), np.uint8)
        background = np.full((90, 80, 3), (200, 10, 10), np.uint8)
        mask = np.zeros((90, 80), np.float32)
        mask[20:70, 15:50] = 1.0
        out = render_transmission(background, person, mask, 0.50, forehead_x=32, forehead_y=22)
        self.assertGreater(float(np.median(out[30, 15:50, 0])), 150.0)
        self.assertLess(float(np.median(out[60, 15:50, 0])), 80.0)


if __name__ == "__main__":
    unittest.main()
