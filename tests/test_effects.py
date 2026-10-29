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

    def test_leave_wipes_down_from_the_forehead_at_full_size(self) -> None:
        person = np.full((90, 80, 3), (20, 30, 40), np.uint8)
        background = np.full((90, 80, 3), (200, 10, 10), np.uint8)
        mask = np.zeros((90, 80), np.float32)
        mask[20:70, 15:50] = 1.0
        early = render_transmission(background, person, mask, 0.15, forehead_x=32, forehead_y=22)
        self.assertLess(float(np.median(early[30, 18:48, 0])), 80.0)
        self.assertLess(float(np.median(early[62, 18:48, 0])), 80.0)
        out = render_transmission(background, person, mask, 0.62, forehead_x=32, forehead_y=22)
        self.assertGreater(float(np.median(out[30, 18:48, 0])), 150.0)
        self.assertLess(float(np.median(out[68, 18:48, 0])), 80.0)
        remaining = np.count_nonzero(out[68, 15:50, 0] < 80)
        self.assertGreater(remaining, 20)

    def test_return_uses_current_person_and_position(self) -> None:
        effect = InstantTransmission()
        background = np.full((90, 90, 3), (180, 10, 10), np.uint8)
        first = np.full((90, 90, 3), (20, 30, 40), np.uint8)
        moved = np.full((90, 90, 3), (10, 180, 35), np.uint8)
        old_mask = np.zeros((90, 90), np.float32)
        old_mask[20:70, 8:35] = 1
        new_mask = np.zeros_like(old_mask)
        new_mask[20:70, 55:82] = 1
        effect.update(_context(first, old_mask, background, 0, keys={"return"}))
        effect.update(_context(first, old_mask, background, DURATION))
        effect.update(_context(moved, new_mask, background, DURATION, keys={"return"}))
        returning = effect.update(_context(moved, new_mask, background, DURATION * 1.8))
        self.assertEqual(effect.phase, "returning")
        self.assertGreater(int(returning[35, 67, 1]), 100)
        self.assertLess(int(returning[35, 20, 1]), 30)

    def test_escape_without_mask_restores_live_video(self) -> None:
        effect = InstantTransmission()
        background = np.full((80, 80, 3), 180, np.uint8)
        person = np.full((80, 80, 3), 20, np.uint8)
        mask = np.ones((80, 80), np.float32)
        effect.update(_context(person, mask, background, 0, keys={"return"}))
        effect.update(_context(person, mask, background, DURATION))
        live = np.full_like(person, 55)
        returned = effect.update(_context(live, None, background, DURATION + 0.1, keys={"escape"}))
        np.testing.assert_array_equal(returned, live)
        self.assertEqual(effect.phase, "idle")


if __name__ == "__main__":
    unittest.main()
