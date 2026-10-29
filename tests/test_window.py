"""Shared pose window. No camera and no window."""

from __future__ import annotations

import unittest

from anime_frame.pose import PoseWindow


class PoseWindowTests(unittest.TestCase):
    def test_eight_of_ten_fires_once_and_three_failures_clear(self) -> None:
        window = PoseWindow()
        pattern = [False, True, False, True, True, True, True, True, True, True]
        fired_at = []
        for index, pose_ok in enumerate(pattern):
            window.update(pose_ok, index * 0.1)
            if window.fired:
                fired_at.append(index)
        self.assertEqual(fired_at, [9])

        window.update(True, 1.0)
        self.assertFalse(window.fired)

        window.update(False, 1.1)
        self.assertFalse(window.fired)
        self.assertEqual(window.true_count, 0)

        for index in range(4):
            window.update(True, 1.2 + index * 0.1)
        self.assertEqual(window.true_count, 4)
        self.assertFalse(window.fired)

        cleared = False
        for index in range(3):
            window.update(False, 1.6 + index * 0.1)
            cleared = cleared or window.cleared
        self.assertTrue(cleared)
        self.assertEqual(window.true_count, 0)
        self.assertFalse(window.fired)

    def test_eight_passes_in_a_row_fire_once(self) -> None:
        window = PoseWindow()
        fires = 0
        for index in range(8):
            window.update(True, index * 0.1)
            fires += int(window.fired)
        self.assertEqual(fires, 1)
        window.update(True, 0.8)
        self.assertFalse(window.fired)

    def test_samples_about_ten_times_a_second(self) -> None:
        window = PoseWindow()
        window.update(True, 0.0)
        window.update(True, 0.05)
        self.assertEqual(window.true_count, 1)
        window.update(True, 0.1)
        self.assertEqual(window.true_count, 2)


if __name__ == "__main__":
    unittest.main()
