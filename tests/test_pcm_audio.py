"""Audio continuity and lifetime checks without opening a hardware device."""
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from anime_frame import audio
from anime_frame.audio_prepare import CHARGE_LOOP_START, CROSSFADE, RELEASE_PLAY, decode_pcm, kamehameha_beds, prepare_cues
from anime_frame.pcm_audio import Cue, Engine, RATE, Voice, balanced, loop_cycle


def pcm(value, seconds):
    return np.full((round(seconds * RATE), 2), value, np.float32)


def cue():
    return Cue(pcm(0.2, 0.4), pcm(0.2, 0.25), pcm(-0.4, 0.3))


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.active = False
        self.closed = False

    def start(self): self.active = True
    def abort(self): self.active = False
    def close(self): self.active = False; self.closed = True


class PCMTests(unittest.TestCase):
    def render(self, voice, count):
        out = np.empty((count, 2), np.float32)
        voice.render(out)
        return out

    def test_chunk_sizes_do_not_change_pcm_or_loop_continuity(self):
        a, b = Voice(cue()), Voice(cue())
        whole = self.render(a, 100000)
        chunks = np.concatenate([self.render(b, n) for n in (19, 4000, 7, 32768, 63206)])
        np.testing.assert_array_equal(whole, chunks)
        self.assertLess(float(np.max(np.abs(np.diff(whole[:, 0])))), 0.001)
        np.testing.assert_allclose(whole[240:], 0.2)

    def test_release_crossfades_at_arbitrary_sample_positions_and_finishes_tail(self):
        for position in (500, 17001, 19300, 40123):
            voice = Voice(cue())
            self.render(voice, position)
            voice.release_requested = True
            out = self.render(voice, 20000)
            self.assertAlmostEqual(float(out[0, 0]), 0.2, places=5)
            self.assertAlmostEqual(float(out[3839, 0]), -0.4, places=5)
            self.assertLess(float(np.max(np.abs(np.diff(out[:3840, 0])))), 0.001)
            np.testing.assert_allclose(out[3840:14400], -0.4)
            np.testing.assert_array_equal(out[14400:], 0)
            self.assertTrue(voice.done)

    def test_stop_ramp_and_shortened_fade_are_continuous(self):
        voice = Voice(cue())
        self.render(voice, 1000)
        voice.stop_request = round(0.4 * RATE)
        first = self.render(voice, round(0.2 * RATE))
        voice.stop_request = round(0.02 * RATE)
        second = self.render(voice, 2000)
        self.assertLess(abs(float(first[-1, 0]-second[0, 0])), 0.001)
        self.assertLess(float(np.max(np.abs(np.diff(second[:, 0])))), 0.001)
        np.testing.assert_array_equal(second[960:], 0)

    def test_normalization_has_headroom_and_matched_levels(self):
        source = np.tile(np.sin(np.arange(48000) * 0.03)[:, None], (1, 2)).astype(np.float32)
        a, b = balanced(source * 0.1, -18), balanced(source * 0.8, -18)
        np.testing.assert_allclose(a, b, atol=1e-6)
        self.assertAlmostEqual(float(20*np.log10(np.sqrt(np.mean(a*a)))), -18, places=3)
        for db in (-18, -16):
            self.assertLessEqual(float(np.max(np.abs(balanced(source, db)))), 0.89)

    def test_prepared_loop_wraps_contiguously(self):
        source = np.tile((np.sin(np.arange(12000)*0.01)*0.2)[:, None], (1, 2)).astype(np.float32)
        result = loop_cycle(source, 1000)
        seam = abs(float(result[-1, 0]-result[0, 0]))
        expected = abs(float(source[999, 0]-source[1000, 0]))
        self.assertAlmostEqual(seam, expected)
        self.assertLess(float(np.max(np.abs(np.diff(result[:, 0])))), 0.003)

    def test_stale_handle_cannot_release_or_stop_replacement(self):
        engine = Engine({'test': cue()}, FakeStream)
        engine.open()
        old = engine.start('test')
        newest = engine.start('test')
        engine.release(old); engine.stop(old)
        voice = engine.current[1]
        self.assertFalse(voice.release_requested)
        self.assertIsNone(voice.stop_request)
        engine.release(newest)
        self.assertTrue(voice.release_requested)
        engine.close()

    def test_output_only_stream_and_device_clock_snapshot(self):
        engine = Engine({'test': cue()}, FakeStream)
        engine.open()
        self.assertEqual(engine.stream.kwargs['channels'], 2)
        self.assertEqual(engine.stream.kwargs['blocksize'], 0)
        self.assertEqual(engine.stream.kwargs['latency'], 'low')
        handle = engine.start('test')
        output = np.empty((480, 2), np.float32)
        timing = SimpleNamespace(outputBufferDacTime=10.03, currentTime=10.0)
        with patch('anime_frame.pcm_audio.time.monotonic', return_value=20.0):
            engine.callback(output, 480, timing, False)
            self.assertEqual(engine.snapshot(handle).elapsed, 0)
        engine.release(handle)
        with patch('anime_frame.pcm_audio.time.monotonic', return_value=20.01):
            engine.callback(output, 480, timing, False)
        with patch('anime_frame.pcm_audio.time.monotonic', return_value=20.045):
            snap = engine.snapshot(handle)
            self.assertEqual(snap.section, 'release')
            self.assertAlmostEqual(snap.release_elapsed, 0.005)
        stream = engine.stream
        engine.close()
        self.assertTrue(stream.closed)

    def test_replacement_crossfade_never_clips(self):
        loud = Cue(pcm(0.89, 0.3), pcm(0.89, 0.3))
        engine = Engine({'test': loud}, FakeStream); engine.open()
        first = engine.start('test')
        timing = SimpleNamespace(outputBufferDacTime=0, currentTime=0)
        out = np.empty((3000, 2), np.float32)
        engine.callback(out, len(out), timing, False)
        engine.stop(first, 0.4)
        engine.callback(out, len(out), timing, False)
        engine.start('test')
        engine.callback(out, len(out), timing, False)
        self.assertLessEqual(float(np.abs(out).max()), 0.890001)
        engine.close()

    def test_device_failure_does_not_fall_back_to_afplay(self):
        engine = Engine({'test': cue()}, stream_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('no output')))
        engine.open()
        self.assertIn('no output', engine.error)
        self.assertIsNone(engine.start('test'))
        with patch.object(audio, '_engine', engine), patch('anime_frame.audio.play') as play:
            self.assertIsNone(audio.start_cue('test'))
            self.assertIn('Audio unavailable', audio.warning('kamehameha'))
            play.assert_not_called()
        engine.close()

    def test_native_decode_cache_is_content_keyed_and_fixed_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'chosen.mp3'
            source.write_bytes(b'first recording')
            def convert(argv, **kwargs):
                self.assertEqual(argv[0], '/usr/bin/afconvert')
                self.assertEqual(argv[3:], ['-f', 'WAVE', '-d', 'LEI16@48000', '-c', '2'])
                self.assertNotIn('shell', kwargs)
                with wave.open(argv[2], 'wb') as file:
                    file.setnchannels(2); file.setsampwidth(2); file.setframerate(RATE)
                    file.writeframes(np.zeros((1000, 2), '<i2').tobytes())
            with patch('anime_frame.audio_prepare.subprocess.run', side_effect=convert) as run:
                decode_pcm(source); decode_pcm(source)
                self.assertEqual(run.call_count, 1)
                source.write_bytes(b'changed recording')
                decode_pcm(source)
                self.assertEqual(run.call_count, 2)

    def test_missing_assets_report_each_effect_without_synthesis(self):
        with tempfile.TemporaryDirectory() as directory:
            cues, errors = prepare_cues(Path(directory))
            self.assertEqual(cues, {})
            self.assertEqual(set(errors), {'kamehameha', 'super_saiyan'})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_kamehameha_is_charge_then_release_without_a_third_clip(self):
        rate = RATE
        charge = np.tile(np.sin(np.arange(rate * 6) * 0.01)[:, None], (1, 2)).astype(np.float32) * 0.2
        release = np.tile(np.sin(np.arange(rate * 6) * 0.02)[:, None], (1, 2)).astype(np.float32) * 0.3
        opening, sustain, fired = kamehameha_beds(charge, release, rate)
        cut = round((CHARGE_LOOP_START + CROSSFADE) * rate)
        np.testing.assert_array_equal(opening, charge[:cut])
        np.testing.assert_array_equal(sustain[0], charge[cut])
        self.assertEqual(len(fired), round(RELEASE_PLAY * rate))
        self.assertLess(len(fired), len(release))
        self.assertLess(abs(float(fired[-1, 0])), 1e-6)
        self.assertLess(abs(float(sustain[-1, 0] - sustain[0, 0])), 0.01)

    def test_saiyan_opening_plays_once_in_persistent_stream(self):
        voice = Voice(Cue(pcm(0.8, 0.4), pcm(0.1, 0.3)))
        out = self.render(voice, RATE*4)
        np.testing.assert_allclose(out[round(RATE*0.4):], 0.1)
