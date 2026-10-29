"""Original one-shot sounds, synthesized on first use and played with afplay."""

from __future__ import annotations

import math
import struct
import subprocess
import wave
from pathlib import Path

RATE = 22050
SOUND_RATES = {"instant_transmission": 44100}

def default_assets() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def sample_rate(name: str) -> int:
    return SOUND_RATES.get(name, RATE)


def _goku() -> list[float]:
    """Dry click plus a fast downward noise sweep. Under half a second."""
    rate = sample_rate("instant_transmission")
    duration = 0.38
    count = int(rate * duration)
    samples: list[float] = []
    noise_state = 7391
    filtered = 0.0
    phase = 0.0
    for index in range(count):
        time = index / rate
        progress = time / duration
        noise_state = (1664525 * noise_state + 1013904223) & 0xFFFFFFFF
        noise = noise_state / 0x7FFFFFFF - 1.0
        cutoff = 6000 * (1 - progress) ** 3 + 180
        mix = 1 - math.exp(-2 * math.pi * cutoff / rate)
        filtered += mix * (noise - filtered)
        phase += 2 * math.pi * (1800 * (1 - progress) ** 2 + 90) / rate
        envelope = min(1.0, time / 0.004) * (1 - progress) ** 2
        click = noise * math.exp(-time * 1200) * 0.45
        sample = click + envelope * (filtered * 0.6 + math.sin(phase) * 0.12)
        samples.append(max(-1.0, min(1.0, sample)) * (28000 / 32767))
    return samples


SOUNDS = {
    "instant_transmission": _goku,
}


def _write_wav(path: Path, samples: list[float], rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for sample in samples:
        clamped = max(-1.0, min(1.0, sample))
        frames += struct.pack("<h", int(clamped * 32767.0))
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


def ensure(name: str, root: Path | None = None) -> Path:
    folder = root or default_assets()
    destination = folder / f"{name}.wav"
    rate = sample_rate(name)
    samples = SOUNDS[name]()
    if destination.exists() and _wav_matches(destination, rate, len(samples)):
        return destination
    _write_wav(destination, samples, rate)
    return destination


def _wav_matches(path: Path, rate: int, frames: int) -> bool:
    try:
        with wave.open(str(path)) as handle:
            return handle.getframerate() == rate and handle.getnframes() == frames
    except (OSError, wave.Error):
        return False


def ensure_all(root: Path | None = None) -> None:
    for name in SOUNDS:
        ensure(name, root)


def sound_path(name: str, root: Path | None = None) -> Path:
    """A supplied mp3 wins. Otherwise the generated wav is used."""
    folder = root or default_assets()
    clip = folder / f"{name}.mp3"
    if clip.is_file():
        return clip
    return ensure(name, root)


def play(name: str, root: Path | None = None) -> None:
    """Play with /usr/bin/afplay. The argument list is fixed."""
    destination = sound_path(name, root)
    try:
        subprocess.Popen(["/usr/bin/afplay", str(destination)])
    except OSError as exc:
        print(f"Could not play sound: {exc}")
