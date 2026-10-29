"""Effect menu order. No camera and no window."""

from __future__ import annotations

import unittest

from anime_frame.registry import load_effects


class RegistryTests(unittest.TestCase):
    def test_menu_order(self) -> None:
        effects = load_effects()
        self.assertEqual(
            [effect.title for effect in effects],
            ["Clear", "Goku Instant Transmission"],
        )
        self.assertEqual([effect.order for effect in effects], [0, 1])
        self.assertEqual(
            [effect.id for effect in effects],
            ["clear", "instant_transmission"],
        )
        self.assertEqual([effect.replaces_person for effect in effects], [False, True])


if __name__ == "__main__":
    unittest.main()
