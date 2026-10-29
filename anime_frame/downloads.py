"""Download the MediaPipe task files on first run. No camera data is sent."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from pathlib import Path

MIN_BYTES = 100 * 1024

MODELS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    ),
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    "selfie_segmenter_landscape.tflite": (
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
        "selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite"
    ),
    "hair_segmenter.tflite": (
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
        "hair_segmenter/float32/1/hair_segmenter.tflite"
    ),
}


def ensure_models(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        destination = directory / name
        if destination.exists() and destination.stat().st_size > MIN_BYTES:
            continue
        print(f"Downloading {name}...")
        temporary = destination.with_suffix(destination.suffix + ".part")
        request = urllib.request.Request(url, headers={"User-Agent": "anime-frame"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except (OSError, urllib.error.URLError) as exc:
            temporary.unlink(missing_ok=True)
            print(f"Could not download {name} from {url}: {exc}")
            raise SystemExit(1) from exc
        if temporary.stat().st_size <= MIN_BYTES:
            temporary.unlink(missing_ok=True)
            print(f"Download of {name} from {url} was incomplete.")
            raise SystemExit(1)
        temporary.replace(destination)
        print(f"Saved {name}.")
