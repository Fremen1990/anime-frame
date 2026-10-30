"""Prepare sustain beds from the selected recording, never synthesize a substitute.

Run once with: .venv/bin/python -m anime_frame.audio_prepare
Native macOS afconvert decodes the selected files; playback uses cached PCM.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from anime_frame.audio import default_assets

SUSTAIN_START = 1.7
SUSTAIN_END = 5.45
CROSSFADE = 0.18
# Charge plays through its steady body. The fading tail is what used to collide
# with a different hold recording. The loop is a later slice of the same charge.
CHARGE_LOOP_START = 3.8
CHARGE_LOOP_END = 5.0
RELEASE_PLAY = 4.2


def saiyan_beds(samples: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Keep the opening once, then crossfade only the steady 1.7–5.45 s tail."""
    start, end, overlap = (round(value * rate) for value in (SUSTAIN_START, SUSTAIN_END, CROSSFADE))
    if rate <= 0 or samples.ndim != 2 or len(samples) < end or overlap < 2:
        raise ValueError("Expected the complete selected aura recording as stereo PCM")
    segment = samples[start:end]
    blend = np.linspace(0.0, 1.0, overlap, dtype=np.float32)[:, None]
    seam = segment[-overlap:] * (1.0 - blend) + segment[:overlap] * blend
    cycle = np.concatenate((segment[overlap:-overlap], seam))
    # Long beds keep afplay process boundaries infrequent. Every internal join
    # and the handoff to the sustain bed has the same contiguous PCM boundary.
    sustain = np.tile(cycle, (8, 1))
    opening = np.concatenate((samples[:start + overlap], sustain))
    return opening, sustain


# Native decoding and in-memory cue construction for continuous playback.
PCM_VERSION = 'v3-48k-stereo'


def decode_pcm(source: Path) -> np.ndarray:
    import hashlib
    import os
    import tempfile

    from anime_frame.pcm_audio import RATE
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = source.parent / '.pcm-cache'
    folder.mkdir(exist_ok=True)
    cached = folder / f'{PCM_VERSION}-{digest}.wav'

    def read(path):
        with wave.open(str(path), 'rb') as handle:
            if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (RATE, 2, 2):
                raise ValueError('Invalid cached PCM format')
            data = handle.readframes(handle.getnframes())
        if not data:
            raise ValueError('Empty audio recording')
        return np.frombuffer(data, '<i2').reshape(-1, 2).astype(np.float32) / 32768

    if cached.exists():
        try:
            return read(cached)
        except (ValueError, wave.Error, EOFError):
            cached.unlink()
    descriptor, temporary = tempfile.mkstemp(suffix='.wav', dir=folder)
    os.close(descriptor)
    try:
        subprocess.run(['/usr/bin/afconvert', str(source), temporary, '-f', 'WAVE', '-d', 'LEI16@48000', '-c', '2'], check=True, capture_output=True, timeout=30)
        samples = read(Path(temporary))
        os.replace(temporary, cached)
        return samples
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def kamehameha_beds(charge: np.ndarray, release: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Charge, then the same charge continued. The blast is the release only."""
    from anime_frame.pcm_audio import loop_cycle
    overlap = round(CROSSFADE * rate)
    loop_start, loop_end = round(CHARGE_LOOP_START * rate), round(CHARGE_LOOP_END * rate)
    release_end = round(RELEASE_PLAY * rate)
    if rate <= 0 or charge.ndim != 2 or len(charge) < loop_end or len(release) <= overlap or overlap < 2:
        raise ValueError('Charge or release recording is too short')
    segment = charge[loop_start:loop_end]
    sustain = loop_cycle(segment, overlap)
    opening = np.ascontiguousarray(charge[:loop_start + overlap])
    fired = np.array(release[:release_end], dtype=np.float32, copy=True)
    fade = np.linspace(1.0, 0.0, overlap, dtype=np.float32)[:, None]
    fired[-overlap:] *= fade
    return opening, sustain, fired


def prepare_cues(root: Path) -> tuple[dict, dict[str, str]]:
    from anime_frame.pcm_audio import Cue, RATE, balanced, loop_cycle
    cues, errors = {}, {}
    overlap = round(CROSSFADE * RATE)
    for name in ('kamehameha', 'super_saiyan'):
        try:
            if name == 'kamehameha':
                charge = balanced(decode_pcm(root / 'kamehameha_charge.mp3'), -18)
                release = balanced(decode_pcm(root / 'kamehameha_release.mp3'), -16)
                opening, sustain, fired = kamehameha_beds(charge, release, RATE)
                cues[name] = Cue(opening, sustain, fired)
            else:
                source = decode_pcm(root / 'super_saiyan_aura.mp3')
                # Preserve dynamics, with enough peak headroom for transitions.
                source *= min(1.0, 0.89 / max(float(np.abs(source).max()), 1e-8))
                start, end = round(SUSTAIN_START * RATE), round(SUSTAIN_END * RATE)
                if len(source) < end:
                    raise ValueError('Aura recording is shorter than its selected sustain region')
                cues[name] = Cue(source[:start + overlap].copy(), loop_cycle(source[start:end], overlap))
        except (OSError, ValueError, wave.Error, EOFError, subprocess.SubprocessError) as exc:
            errors[name] = str(exc)
    return cues, errors


def prepare(root: Path | None = None) -> None:
    cues, errors = prepare_cues(root or default_assets())
    for name, cue in cues.items():
        print(f"Prepared {name}: opening {len(cue.opening)/48000:.3f}s, sustain {len(cue.sustain)/48000:.3f}s, release {cue.release_seconds:.3f}s")
    if errors:
        raise RuntimeError(str(errors))


if __name__ == "__main__":
    prepare()
