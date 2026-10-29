"""Synthesized sounds stay under half a second and play through afplay."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from anime_frame import audio


class AudioTests(unittest.TestCase):
    def test_each_sound_is_under_half_a_second(self) -> None:
        for name, synthesize in audio.SOUNDS.items():
            samples = synthesize()
            self.assertGreater(len(samples), 0, name)
            self.assertLess(len(samples) / audio.sample_rate(name), 0.5, name)

    def test_play_uses_afplay_with_a_fixed_argument_list(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("anime_frame.audio.subprocess.Popen") as popen:
                audio.play("instant_transmission", root)
            argv = popen.call_args.args[0]
            self.assertEqual(argv, ["/usr/bin/afplay", str(root / "instant_transmission.wav")])
            self.assertFalse(popen.call_args.kwargs.get("shell", False))
            with wave.open(str(root / "instant_transmission.wav")) as handle:
                self.assertLess(handle.getnframes() / handle.getframerate(), 0.5)

    def test_supplied_mp3_is_played_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "instant_transmission.mp3"
            clip.write_bytes(b"clip")
            with patch("anime_frame.audio.subprocess.Popen") as popen:
                audio.play("instant_transmission", root)
            argv = popen.call_args.args[0]
            self.assertEqual(argv, ["/usr/bin/afplay", str(clip)])
            self.assertFalse((root / "instant_transmission.wav").exists())


if __name__ == "__main__":
    unittest.main()
