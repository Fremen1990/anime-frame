"""Local recordings, prepared sustain beds, and cancellable afplay playback."""

from __future__ import annotations

import tempfile
import threading
import subprocess
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from anime_frame import audio
from anime_frame.audio_prepare import CROSSFADE, SUSTAIN_START, saiyan_beds


class AudioTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in list(audio._loops) + list(audio._oneshots):
            audio.stop(name)

    def test_each_sound_is_under_half_a_second(self) -> None:
        for name, synthesize in audio.SOUNDS.items():
            samples = synthesize()
            self.assertGreater(len(samples), 0, name)
            self.assertLess(len(samples) / audio.sample_rate(name), 0.5, name)

    def test_prepared_sustain_has_no_transformation_intro_and_continuous_joins(self) -> None:
        rate = 1000
        samples = np.full((5800, 2), 0.8, np.float32)
        # The intro is deliberately distinct from the steady waveform.
        start = round(SUSTAIN_START * rate)
        samples[start:] = np.sin(np.arange(5800 - start)[:, None] * 0.02) * 0.15
        opening, sustain = saiyan_beds(samples, rate)
        preserved = round((SUSTAIN_START + CROSSFADE) * rate)
        np.testing.assert_array_equal(opening[:preserved], samples[:preserved])
        self.assertLessEqual(float(np.abs(sustain).max()), 0.151)
        self.assertLessEqual(float(np.abs(opening[preserved:]).max()), 0.151)
        self.assertGreater(len(sustain) / rate, 25)
        self.assertLess(float(np.max(np.abs(np.diff(sustain, axis=0)))), 0.004)
        self.assertLess(float(np.max(np.abs(opening[-1] - sustain[0]))), 0.004)
        self.assertLess(float(np.max(np.abs(sustain[-1] - sustain[0]))), 0.004)

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

    def test_show_effects_stay_silent_without_an_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("super_saiyan", "kamehameha_charge", "kikoho_release"):
                (root / f"{name}.wav").write_bytes(b"old synthesized sound")
            with patch("anime_frame.audio.subprocess.Popen") as popen:
                audio.play("super_saiyan", root)
                audio.play("kamehameha_charge", root)
                audio.play("kamehameha_release", root)
                audio.play("kikoho_charge", root)
                audio.play("kikoho_release", root)
                audio.loop("super_saiyan_aura", root)
            popen.assert_not_called()
            self.assertFalse((root / "kamehameha_release.wav").exists())

    def test_aura_loop_plays_a_supplied_mp3_until_stop(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "super_saiyan_aura.mp3"
            clip.write_bytes(b"clip")
            proc = Mock()
            proc.poll.return_value = None
            with patch("anime_frame.audio.subprocess.Popen", return_value=proc) as popen:
                audio.loop("super_saiyan_aura", root)
                for _ in range(50):
                    if popen.call_args:
                        break
                    time.sleep(0.01)
                argv = popen.call_args.args[0]
                self.assertEqual(argv, ["/usr/bin/afplay", str(clip)])
                self.assertFalse(popen.call_args.kwargs.get("shell", False))
                audio.stop("super_saiyan_aura")
            proc.terminate.assert_called()

    def test_hold_waits_for_charge_and_cancel_prevents_late_playback(self) -> None:
        class FakeProcess:
            def __init__(self):
                self.done = threading.Event()
                self.terminated = False

            @property
            def returncode(self):
                return self.poll()

            def poll(self):
                return 0 if self.done.is_set() else None

            def terminate(self):
                self.terminated = True
                self.done.set()

            def wait(self, timeout=None):
                if not self.done.wait(timeout):
                    raise subprocess.TimeoutExpired("afplay", timeout)
                return 0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("kamehameha_charge", "kamehameha_hold"):
                (root / f"{name}.mp3").write_bytes(b"clip")
            charge, hold = FakeProcess(), FakeProcess()
            hold_started = threading.Event()

            def launch(argv):
                if argv[1].endswith("_charge.mp3"):
                    return charge
                hold_started.set()
                return hold

            with patch("anime_frame.audio.subprocess.Popen", side_effect=launch):
                audio.play("kamehameha_charge", root)
                audio.loop("kamehameha_hold", root, after="kamehameha_charge")
                self.assertFalse(hold_started.wait(0.05))
                charge.done.set()
                self.assertTrue(hold_started.wait(1.0))
                audio.stop("kamehameha_hold")
                self.assertTrue(hold.terminated)

                charge = FakeProcess()
                hold_started.clear()
                audio.play("kamehameha_charge", root)
                audio.loop("kamehameha_hold", root, after="kamehameha_charge")
                audio.stop("kamehameha_hold")
                audio.stop("kamehameha_charge")
                self.assertTrue(charge.terminated)
                self.assertFalse(hold_started.wait(0.05))


if __name__ == "__main__":
    unittest.main()
