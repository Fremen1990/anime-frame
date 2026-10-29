"""Chooser rows. No camera and no window."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from anime_frame.app import (
    CHOOSER_HEIGHT,
    CHOOSER_WIDTH,
    LOAD_BACKGROUND,
    ROW_HEIGHT,
    ROW_TOP,
    WINDOW_MISS_LIMIT,
    App,
    render_chooser,
    row_at,
    window_fate,
    window_layout,
)
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

    def test_a_second_load_in_the_same_moment_does_not_restart(self) -> None:
        app = App()
        app._load_background(0.0)
        app._load_background(0.2)
        self.assertEqual(app.background.started_at, 0.0)
        self.assertEqual(app.background.seconds_left(0.2), 3)

    def test_only_the_click_release_selects_a_row(self) -> None:
        app = App()
        app.effects = load_effects()
        app._on_mouse(cv2.EVENT_LBUTTONDOWN, 40, ROW_TOP + 20, 0, None)
        self.assertIsNone(app.clicked_row)
        app._on_mouse(cv2.EVENT_LBUTTONUP, 40, ROW_TOP + 20, 0, None)
        self.assertEqual(app.clicked_row, 0)

    def test_preview_and_chooser_share_the_screen(self) -> None:
        for screen in ((1680, 1020), (1440, 900), (1920, 1080)):
            preview, chooser = window_layout(*screen)
            px, py, pw, ph = preview
            cx, cy = chooser
            self.assertGreaterEqual(pw, 320)
            self.assertLessEqual(px + pw, cx)
            self.assertLessEqual(cx + CHOOSER_WIDTH, screen[0])
            self.assertLessEqual(cy + CHOOSER_HEIGHT, screen[1])
            self.assertLessEqual(py + ph, screen[1])

    def test_a_missing_window_is_rebuilt_before_the_session_ends(self) -> None:
        self.assertEqual(window_fate(1, 4), ("keep", 0))
        self.assertEqual(window_fate(-1, 0), ("revive", 1))
        self.assertEqual(window_fate(0, 1), ("wait", 2))
        self.assertEqual(window_fate(0, WINDOW_MISS_LIMIT - 1), ("quit", WINDOW_MISS_LIMIT))

    def test_transmission_card_uses_the_goku_still(self) -> None:
        image = render_chooser(load_effects(), "instant_transmission", "")
        sample = image[160:280, 560:860]
        self.assertGreater(float(sample.std()), 15.0)
        self.assertEqual(LOAD_BACKGROUND, "Load background")


if __name__ == "__main__":
    unittest.main()
