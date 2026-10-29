"""Empty-room capture. No camera and no window."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

import numpy as np

from anime_frame.background import COME_BACK, STEP_OUT, Background


class BackgroundTests(unittest.TestCase):
    def test_median_uses_the_last_half_second(self) -> None:
        background = Background()
        red = np.zeros((4, 4, 3), np.uint8)
        red[:] = (0, 0, 255)
        green = np.zeros((4, 4, 3), np.uint8)
        green[:] = (0, 255, 0)
        messages = io.StringIO()
        with redirect_stdout(messages):
            background.start(0.0)
            background.update(red, 0.1)
            background.update(red, 2.4)
            background.update(green, 2.6)
            background.update(green, 2.9)
            self.assertIsNone(background.image)
            background.update(green, 3.0)
        self.assertFalse(background.capturing)
        self.assertEqual(int(background.image[0, 0, 1]), 255)
        self.assertEqual(int(background.image[0, 0, 2]), 0)
        text = messages.getvalue()
        self.assertIn(STEP_OUT, text)
        self.assertIn(COME_BACK, text)

    def test_cancel_does_not_store_a_room(self) -> None:
        background = Background()
        frame = np.zeros((2, 2, 3), np.uint8)
        messages = io.StringIO()
        with redirect_stdout(messages):
            background.start(0.0)
            background.cancel()
            background.update(frame, 3.0)
        self.assertIsNone(background.image)
        self.assertNotIn(COME_BACK, messages.getvalue())

    def test_countdown_is_three_seconds(self) -> None:
        background = Background()
        background.start(0.0)
        self.assertEqual(background.seconds_left(0.0), 3)
        self.assertEqual(background.seconds_left(1.1), 2)
        self.assertEqual(background.seconds_left(2.5), 1)
        self.assertEqual(background.seconds_left(3.0), 0)
        self.assertEqual(background.seconds_left(4.0), 0)


if __name__ == "__main__":
    unittest.main()
