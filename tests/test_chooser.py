"""Chooser rows. No camera and no window."""

from __future__ import annotations

import unittest

import numpy as np

from anime_frame.app import LOAD_BACKGROUND, ROW_HEIGHT, ROW_TOP, App, render_chooser, row_at
from anime_frame.registry import load_effects


class ChooserTests(unittest.TestCase):
    def test_load_background_is_the_row_after_the_effects(self) -> None:
        count = 3
        y = ROW_TOP + 2 * ROW_HEIGHT + 20
        self.assertEqual(row_at(40, y, count), 2)
        self.assertIsNone(row_at(40, y + ROW_HEIGHT, count))

    def test_load_background_restarts_the_countdown(self) -> None:
        app = App()
        app.background.image = np.zeros((2, 2, 3), np.uint8)
        messages_started = app.background.capturing
        self.assertFalse(messages_started)
        app._load_background(0.0)
        self.assertTrue(app.background.capturing)
        self.assertEqual(app.background.seconds_left(0.0), 3)
        self.assertIsNotNone(app.background.image)
        app._load_background(1.2)
        self.assertEqual(app.background.seconds_left(1.2), 3)

    def test_transmission_card_uses_the_goku_still(self) -> None:
        image = render_chooser(load_effects(), "instant_transmission", "")
        sample = image[160:280, 560:860]
        self.assertGreater(float(sample.std()), 15.0)
        self.assertEqual(LOAD_BACKGROUND, "Load background")


if __name__ == "__main__":
    unittest.main()
