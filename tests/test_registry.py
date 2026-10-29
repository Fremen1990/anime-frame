"""Effect menu order. No camera and no window."""

from __future__ import annotations

import unittest

from anime_frame.registry import load_effects


class RegistryTests(unittest.TestCase):
    def test_menu_order(self) -> None:
        effects = load_effects()
        self.assertEqual(
            [effect.title for effect in effects],
            ["Clear", "Goku Instant Transmission", "Super Saiyan", "Kamehameha", "Kikōhō"],
        )
        self.assertEqual([effect.order for effect in effects], [0, 1, 2, 3, 4])
        self.assertEqual(
            [effect.id for effect in effects],
            ["clear", "instant_transmission", "super_saiyan", "kamehameha", "kikoho"],
        )
        self.assertEqual([effect.replaces_person for effect in effects], [False, True, False, False, False])


if __name__ == "__main__":
    unittest.main()
