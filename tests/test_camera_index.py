"""Camera index choice. These tests do not open a camera."""

from __future__ import annotations

import unittest

from anime_frame.camera import ordered_names, permission_message, preferred_index, resolve_index


class CameraIndexTests(unittest.TestCase):
    def test_opencv_sorts_devices_by_unique_id(self) -> None:
        devices = [
            ("Kamera HD FaceTime", "EAB7A68F-EC2B-4487-AADF-D8A91C1CB782"),
            ("OBS Virtual Camera", "7626645E-4425-469E-9D8B-97E0FA59AC75"),
        ]
        names = ordered_names(devices)
        self.assertEqual(names, ["OBS Virtual Camera", "Kamera HD FaceTime"])
        self.assertEqual(preferred_index(names), 1)

    def test_prefers_facetime_or_macbook(self) -> None:
        self.assertEqual(preferred_index(["OBS Virtual Camera", "FaceTime HD Camera"]), 1)
        self.assertEqual(preferred_index(["USB Cam", "MacBook Pro Camera", "FaceTime"]), 1)
        self.assertEqual(preferred_index(["Kamera HD FaceTime"]), 0)
        self.assertEqual(preferred_index(None), 0)
        self.assertEqual(preferred_index([]), 0)

    def test_remembered_index_wins_when_it_still_exists(self) -> None:
        names = ["OBS Virtual Camera", "FaceTime HD Camera"]
        self.assertEqual(resolve_index(0, names), 0)
        self.assertEqual(resolve_index(None, names), 1)
        self.assertEqual(resolve_index(5, names), 1)
        self.assertEqual(resolve_index(None, None), 0)
        self.assertEqual(resolve_index(2, None), 2)

    def test_remembered_name_follows_a_reordered_list(self) -> None:
        flipped = ["FaceTime HD Camera", "OBS Virtual Camera"]
        self.assertEqual(resolve_index(1, flipped, "FaceTime HD Camera"), 0)
        self.assertEqual(resolve_index(0, flipped, "OBS Virtual Camera"), 1)

    def test_permission_message_names_the_settings_pane(self) -> None:
        message = permission_message()
        self.assertIn("System Settings → Privacy & Security → Camera", message)
        self.assertTrue("Terminal" in message or "Cursor" in message)


if __name__ == "__main__":
    unittest.main()
