"""Prepared PCM cues and an output-only, persistent audio renderer.

The callback copies and mixes preloaded samples in bounded chunks. It never
opens files, decodes media, opens input devices, or waits on the camera thread.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

RATE = 48000
CHUNK = 2048


def balanced(samples: np.ndarray, db: float) -> np.ndarray:
    samples = np.asarray(samples, np.float32)
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(samples)))
    gain = min(10 ** (db / 20) / max(rms, 1e-8), 0.89 / max(peak, 1e-8))
    return np.ascontiguousarray(samples * gain, dtype=np.float32)


def loop_cycle(samples: np.ndarray, overlap: int) -> np.ndarray:
    if len(samples) <= overlap * 2:
        raise ValueError("Recording is too short for its loop crossfade")
    ramp = np.linspace(0, 1, overlap, dtype=np.float32)[:, None]
    seam = samples[-overlap:] * (1 - ramp) + samples[:overlap] * ramp
    return np.concatenate((samples[overlap:-overlap], seam))


def envelope(samples: np.ndarray) -> np.ndarray:
    size = RATE // 100
    padded = np.pad(samples, ((0, (-len(samples)) % size), (0, 0)))
    levels = np.sqrt(np.mean(padded.reshape(-1, size, 2) ** 2, axis=(1, 2)))
    # Offline smoothing: no envelope computation in the audio callback.
    levels = np.convolve(np.pad(levels, (4, 4), mode="edge"), np.ones(9) / 9, mode="valid")
    return np.clip(levels / max(float(levels.max()), 1e-6), 0, 1).astype(np.float32)


@dataclass
class Cue:
    opening: np.ndarray
    sustain: np.ndarray
    release: np.ndarray | None = None

    def __post_init__(self) -> None:
        for samples in (self.opening, self.sustain, self.release):
            if samples is not None and (samples.ndim != 2 or samples.shape[1] != 2 or not len(samples) or not np.isfinite(samples).all()):
                raise ValueError("Cue requires finite, nonempty stereo PCM")
        self.opening_env = envelope(self.opening)
        self.sustain_env = envelope(self.sustain)
        self.release_env = envelope(self.release) if self.release is not None else None
        self.peak_at = int(np.argmax(self.opening_env[:170])) / 100

    @property
    def release_seconds(self) -> float:
        return len(self.release) / RATE if self.release is not None else 0.0

    def level(self, elapsed: float, release_elapsed: float | None) -> float:
        if release_elapsed is not None and release_elapsed >= 0 and self.release_env is not None:
            values, index = self.release_env, int(release_elapsed * 100)
        elif elapsed * RATE < len(self.opening):
            values, index = self.opening_env, int(max(0, elapsed) * 100)
        else:
            seconds = ((elapsed * RATE - len(self.opening)) % len(self.sustain)) / RATE
            values, index = self.sustain_env, int(seconds * 100)
        return float(values[min(index, len(values) - 1)])


@dataclass(frozen=True)
class Handle:
    generation: int


@dataclass(frozen=True)
class Snapshot:
    section: str
    elapsed: float
    release_elapsed: float | None
    amplitude: float
    release_duration: float
    opening_peak: float


class Voice:
    """Single callback-owned playhead; request fields are published by control code."""
    def __init__(self, cue: Cue):
        self.cue = cue
        self.position = 0
        self.in_loop = False
        self.total = 0
        self.release_position: int | None = None
        self.release_requested = False
        self.stop_request: int | None = None
        self.stop_position = 0
        self.stop_length = 0
        self.stop_initial = 1.0
        self.applied_stop = None
        self.done = False
        self.base = np.empty((CHUNK, 2), np.float32)
        self.extra = np.empty((CHUNK, 2), np.float32)
        self.indices = np.arange(CHUNK, dtype=np.float32)
        self.gain = np.empty(CHUNK, np.float32)
        self.crossfade = np.linspace(0, 1, round(0.08 * RATE), dtype=np.float32)[:, None]
        self.reverse = 1 - self.crossfade

    def _base(self, out: np.ndarray) -> None:
        offset = 0
        while offset < len(out):
            source = self.cue.sustain if self.in_loop else self.cue.opening
            count = min(len(out) - offset, len(source) - self.position)
            out[offset:offset + count] = source[self.position:self.position + count]
            offset += count
            self.position += count
            if self.position == len(source):
                self.position = 0
                self.in_loop = True

    def apply_requests(self) -> None:
        request = self.stop_request
        if request is not None and request != self.applied_stop:
            if self.applied_stop is not None:
                self.stop_initial *= max(0.0, 1 - self.stop_position / max(1, self.stop_length))
            self.stop_length = request
            self.stop_position = 0
            self.applied_stop = request
        if self.release_requested and self.release_position is None and self.cue.release is not None:
            self.release_position = 0

    def render(self, out: np.ndarray, *, apply_requests=True) -> None:
        out.fill(0)
        if self.done:
            return
        if apply_requests:
            self.apply_requests()
        for offset in range(0, len(out), CHUNK):
            block = out[offset:offset + CHUNK]
            count = len(block)
            if self.done:
                break
            if self.release_position is None:
                self._base(block)
            else:
                pos = self.release_position
                source = self.cue.release
                available = min(count, max(0, len(source) - pos))
                block[:available] = source[pos:pos + available]
                cross = min(count, max(0, len(self.crossfade) - pos))
                if cross:
                    self._base(self.base[:cross])
                    np.multiply(block[:cross], self.crossfade[pos:pos + cross], out=block[:cross])
                    np.multiply(self.base[:cross], self.reverse[pos:pos + cross], out=self.extra[:cross])
                    np.add(block[:cross], self.extra[:cross], out=block[:cross])
                self.release_position += count
                if self.release_position >= len(source):
                    self.done = True
            # Five ms attack and cancellable stop ramps, with preallocated work.
            if self.total < 240:
                np.add(self.indices[:count], self.total, out=self.gain[:count])
                self.gain[:count] /= 240
                np.clip(self.gain[:count], 0, 1, out=self.gain[:count])
                np.multiply(block, self.gain[:count, None], out=block)
            if self.applied_stop is not None:
                np.add(self.indices[:count], self.stop_position, out=self.gain[:count])
                self.gain[:count] /= max(1, self.stop_length)
                np.subtract(1, self.gain[:count], out=self.gain[:count])
                np.clip(self.gain[:count], 0, 1, out=self.gain[:count])
                self.gain[:count] *= self.stop_initial
                np.multiply(block, self.gain[:count, None], out=block)
                self.stop_position += count
                if self.stop_position >= self.stop_length:
                    self.done = True
            self.total += count


class Engine:
    def __init__(self, cues: dict[str, Cue], stream_factory=None):
        self.cues = cues
        self.generation = 0
        self.current: tuple[Handle, Voice] | None = None
        self.rendering: tuple[Handle, Voice] | None = None
        self.previous: Voice | None = None
        self.scratch = np.empty((CHUNK, 2), np.float32)
        self.stream = None
        self.error = ""
        self.underflows = 0
        self.dac_end = 0.0
        self.release_at: float | None = None
        self.clock = None
        self.stream_factory = stream_factory

    def open(self) -> None:
        try:
            if self.stream_factory is None:
                from sounddevice import OutputStream
                self.stream_factory = OutputStream
            self.stream = self.stream_factory(samplerate=RATE, channels=2, dtype="float32", latency="low", blocksize=0, callback=self.callback)
            self.stream.start()
        except Exception as exc:
            self.error = str(exc)
            if self.stream is not None:
                self.stream.close()
            self.stream = None

    def start(self, name: str) -> Handle | None:
        if self.stream is None or name not in self.cues:
            return None
        self.generation += 1
        handle = Handle(self.generation)
        self.current = (handle, Voice(self.cues[name]))
        return handle

    def release(self, handle: Handle | None) -> None:
        if self.current is not None and self.current[0] == handle:
            voice = self.current[1]
            if voice.stop_request is None:
                voice.release_requested = True

    def stop(self, handle: Handle | None, seconds: float = 0.02) -> None:
        if self.current is not None and self.current[0] == handle:
            voice = self.current[1]
            # A repeated cancel cannot extend an already running fade.
            frames = max(1, round(seconds * RATE))
            voice.stop_request = frames if voice.stop_request is None else min(voice.stop_request, frames)

    def callback(self, out, frames, timing, status) -> None:
        out.fill(0)
        if status:
            self.underflows += 1
        requested = self.current
        if requested is not self.rendering:
            self.previous = self.rendering[1] if self.rendering is not None else None
            if self.previous is not None:
                self.previous.stop_request = round(0.02 * RATE)
            self.rendering = requested
            self.release_at = None
        if requested is None:
            return
        handle, voice = requested
        audible_at = time.monotonic() + float(timing.outputBufferDacTime - timing.currentTime)
        previous_release = voice.release_position
        voice.apply_requests()
        if previous_release is None and voice.release_position is not None:
            self.release_at = audible_at
        if self.previous is not None:
            self.previous.apply_requests()
        # Limit work-buffer sizes even when PortAudio supplies a large block.
        for offset in range(0, frames, CHUNK):
            block = out[offset:offset + CHUNK]
            voice.render(block, apply_requests=False)
            if self.previous is not None and not self.previous.done:
                self.previous.render(self.scratch[:len(block)], apply_requests=False)
                # Crossfade replacement voices without summing two full levels.
                np.subtract(1, self.previous.gain[:len(block), None], out=self.previous.extra[:len(block)])
                np.multiply(block, self.previous.extra[:len(block)], out=block)
                np.add(block, self.scratch[:len(block)], out=block)
        self.dac_end = audible_at + frames / RATE
        self.clock = (handle.generation, voice.total, self.dac_end, self.release_at)

    def snapshot(self, handle: Handle | None) -> Snapshot | None:
        if self.current is None or self.current[0] != handle or self.stream is None or not self.stream.active:
            return None
        voice = self.current[1]
        clock = self.clock
        if clock is None or clock[0] != handle.generation:
            return None
        now = time.monotonic()
        elapsed = max(0, clock[1] / RATE + now - clock[2])
        release_elapsed = now - clock[3] if clock[3] is not None else None
        section = "opening" if elapsed < len(voice.cue.opening) / RATE else "sustain"
        if release_elapsed is not None and release_elapsed >= 0:
            section = "release" if release_elapsed < voice.cue.release_seconds else "done"
        return Snapshot(section, elapsed, release_elapsed, voice.cue.level(elapsed, release_elapsed), voice.cue.release_seconds, voice.cue.peak_at)

    def close(self) -> None:
        self.current = None
        if self.stream is not None:
            self.stream.abort()
            self.stream.close()
            self.stream = None
        self.rendering = None
        self.previous = None
