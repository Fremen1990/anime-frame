"""Local one-shot afplay and continuous output-only PCM playback.

Instant Transmission falls back to a short generated wav. Every other effect
uses selected local recordings. Continuous effects use prepared PCM in an output-only stream. Files are
never downloaded by the app.
"""

from __future__ import annotations

import math
import struct
import subprocess
import threading
import wave
from pathlib import Path

RATE = 22050
SOUND_RATES = {"instant_transmission": 44100}
PREPARED_RECORDINGS = {"super_saiyan_start", "super_saiyan_sustain"}

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


class _Loop:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.proc: subprocess.Popen[bytes] | None = None


_loops: dict[str, _Loop] = {}
_oneshots: dict[str, subprocess.Popen[bytes]] = {}
_loop_lock = threading.Lock()


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


def sound_path(name: str, root: Path | None = None) -> Path | None:
    """A supplied mp3 wins. Only Instant Transmission has a generated fallback."""
    folder = root or default_assets()
    clip = folder / f"{name}.mp3"
    if clip.is_file():
        return clip
    prepared = folder / f"{name}.wav"
    if name in PREPARED_RECORDINGS and prepared.is_file():
        return prepared
    if name not in SOUNDS:
        return None
    return ensure(name, root)


def _afplay(destination: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(["/usr/bin/afplay", str(destination)])


def play(name: str, root: Path | None = None) -> None:
    """Play once with /usr/bin/afplay. The argument list is fixed."""
    stop(name)
    destination = sound_path(name, root)
    if destination is None:
        return
    try:
        proc = _afplay(destination)
        with _loop_lock:
            _oneshots[name] = proc
    except OSError as exc:
        print(f"Could not play sound: {exc}")


def _terminate(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=0.3)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=0.3)


def loop(name: str, root: Path | None = None, *, after: str | None = None) -> None:
    """Loop until stop(), optionally waiting for a named one-shot to finish."""
    stop(name)
    destination = sound_path(name, root)
    if destination is None:
        return
    state = _Loop()
    with _loop_lock:
        predecessor = _oneshots.get(after) if after is not None else None

    def run() -> None:
        try:
            while predecessor is not None and predecessor.poll() is None:
                if state.stop.wait(0.02):
                    return
            while not state.stop.is_set():
                try:
                    proc = _afplay(destination)
                except OSError as exc:
                    print(f"Could not play sound: {exc}")
                    return
                with _loop_lock:
                    state.proc = proc
                while proc.poll() is None:
                    if state.stop.wait(0.02):
                        _terminate(proc)
                        return
                if proc.returncode != 0:
                    return
        finally:
            with _loop_lock:
                if _loops.get(name) is state:
                    _loops.pop(name, None)

    state.thread = threading.Thread(target=run, name=f"afplay-{name}", daemon=True)
    with _loop_lock:
        _loops[name] = state
    state.thread.start()


def stop(name: str) -> None:
    """Stop and reap a named one-shot or loop, including a queued hold clip."""
    with _loop_lock:
        state = _loops.pop(name, None)
        proc = _oneshots.pop(name, None)
    _terminate(proc)
    if state is None:
        return
    state.stop.set()
    thread = state.thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=0.6)


_engine = None
_cue_errors: dict[str, str] = {}


def initialize(root: Path | None = None, stream_factory=None) -> None:
    """Prepare and open once before camera processing; failure leaves video usable."""
    global _engine, _cue_errors
    shutdown()
    from anime_frame.audio_prepare import prepare_cues
    from anime_frame.pcm_audio import Engine
    cues, _cue_errors = prepare_cues(root or default_assets())
    _engine = Engine(cues, stream_factory)
    if cues:
        _engine.open()
    for name, error in _cue_errors.items():
        print(f"Audio unavailable for {name}: {error}")
    if _engine.error:
        print(f"Continuous audio unavailable: {_engine.error}")


def start_cue(name: str):
    return _engine.start(name) if _engine is not None else None


def release_cue(handle) -> None:
    if _engine is not None:
        _engine.release(handle)


def fade_stop(handle, seconds: float = 0.02) -> None:
    if _engine is not None:
        _engine.stop(handle, seconds)


def playback_snapshot(handle):
    return _engine.snapshot(handle) if _engine is not None else None


def release_duration(name: str, fallback: float) -> float:
    if _engine is not None and name in _engine.cues:
        return _engine.cues[name].release_seconds or fallback
    return fallback


def warning(name: str) -> str:
    if name not in ('kamehameha', 'super_saiyan'):
        return ''
    if name in _cue_errors or _engine is None or _engine.stream is None or not _engine.stream.active:
        return 'Audio unavailable; visuals continue'
    return ''


def shutdown() -> None:
    global _engine
    if _engine is not None:
        _engine.close()
        _engine = None
    for name in list(_loops) + list(_oneshots):
        stop(name)
