"""Prepare sustain beds from the selected recording, never synthesize a substitute.

Run once with: .venv/bin/python -m anime_frame.audio_prepare
ffmpeg is needed only for this preparation, not for camera sessions.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from anime_frame.audio import default_assets

SUSTAIN_START = 1.7
SUSTAIN_END = 5.45
CROSSFADE = 0.18


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


def prepare(root: Path | None = None) -> None:
    folder = root or default_assets()
    decoder = shutil.which("ffmpeg")
    if decoder is None:
        raise RuntimeError("Preparing the selected aura recording requires ffmpeg")
    rate = 48000
    result = subprocess.run(
        [decoder, "-v", "error", "-i", str(folder / "super_saiyan_aura.mp3"),
         "-f", "f32le", "-ac", "2", "-ar", str(rate), "-"],
        check=True, capture_output=True,
    )
    samples = np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2)
    for name, bed in zip(("super_saiyan_start", "super_saiyan_sustain"), saiyan_beds(samples, rate)):
        destination = folder / f"{name}.wav"
        with wave.open(str(destination), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes((np.clip(bed, -1, 1) * 32767).astype("<i2").tobytes())
        print(f"Prepared {destination.name}: {len(bed) / rate:.2f} s")


if __name__ == "__main__":
    prepare()
