# Anime Frame agent guide

Anime Frame is a new local webcam-effects app. It puts anime-style animations on your real camera. Video stays on this Mac. The preview and the virtual camera show the picture and the effect only.

Read `PROMPT.md` and `ROADMAP.md` before writing code. Implement the current unchecked phase in `ROADMAP.md`, then stop. Check a box only after that item runs and its tests pass. `PROMPT.md` still names Ascend and Lance. Those two were removed. Do not put them back.

## Hard rules

- Build everything in this folder. Do not open, copy, rename, or adapt files from `~/projects/vanish_webcam` or any VanishCam checkout.
- Do not add character art, anime frames, or scanned sprites. Instant Transmission plays the local `assets/instant_transmission.mp3`. Do not add other downloaded audio. Draw effects with OpenCV and NumPy. Synthesize a fallback sound with the Python standard library when that file is missing.
- The product name on screen is Anime Frame. Effect names are the names in `ROADMAP.md`. The forehead effect is titled **Goku Instant Transmission**. Do not add a show logo or character art.
- Do not record video, upload frames, or open a microphone. Do not add `NSMicrophoneUsageDescription`.
- Play audio only through `/usr/bin/afplay` with a fixed argument list. Never use `shell=True`.
- Outgoing video has no text, countdown, menu, or debug overlay. Diagnostics go to the terminal.
- Docker is out of scope. The camera and the OBS virtual camera are macOS devices, and a Linux container cannot use them.

## Layout

Effects are plugins. The camera loop does not mention a specific effect by name.

```text
anime-frame/
  run
  requirements.txt
  README.md
  anime_frame/
    app.py            # windows, keys, session
    camera.py         # device choice and capture
    background.py     # empty-room capture
    segment.py        # person mask
    pose.py           # shared landmark math
    audio.py
    registry.py       # loads anime_frame/effects/*.py
    effects/
      base.py
      clear.py
      instant_transmission.py
  tests/
  models/             # downloaded, gitignored
```

A new animation is a new file in `anime_frame/effects/`. It subclasses the effect base, and the registry picks it up on the next launch. Effects do not import each other.

Shared pose math lives in `anime_frame/pose.py`. An effect keeps its own state. The app passes a frame context in and gets a frame out.

## Frame context

Each `update` call receives:

- the mirrored BGR frame
- the person mask, or `None` when segmentation has not produced one yet
- the stored background, or `None` when this session has no empty room yet
- monotonic time in seconds
- hand landmarks, face landmarks, and pose landmarks for this frame
- the set of keys pressed since the previous frame

`update` returns the BGR frame to show and to send. It must not open windows, cameras, or files.

## Gestures

Sample a pose about ten times a second. Fire when at least eight of the last ten samples passed. Any run of three failures clears the window. Effects that remove the person also need a stored background; if it is missing, the app runs background capture before the effect can arm.

These poses must not overlap:

| Effect | Pose |
| --- | --- |
| Goku Instant Transmission | Index and middle fingers extended and adjacent, ring and pinky folded, tips held on the forehead |
| Clear | No pose |

A spread V, a single pointing finger, and a finger at the temple do not fire Goku Instant Transmission.

## Keys

The chooser window receives these keys. The preview window receives the same set after it has focus.

| Key | Action |
| --- | --- |
| `0` | Clear |
| `1` | Goku Instant Transmission |
| Return | Fire the active effect without the pose |
| Escape | Cancel the active effect and return to the live picture |
| Space | Capture the background again. The Load background row does the same and always restarts the countdown |
| `[` `]` | Previous and next camera, then remember it |
| `F` | Fullscreen the preview |
| `Q` | Quit and release the camera |

## Run

Daily use is one command from this folder:

```bash
./run
```

That creates `.venv` on first use, installs `requirements.txt`, downloads the models, and opens the last-used camera and effect. The first launch uses the built-in camera and Clear.

```bash
./run teams
```

Same path, and the frames also go to OBS Virtual Camera. If that driver is missing, print the one-time OBS steps and exit. Do not fall back to a preview-only session in `teams` mode.

```bash
./run test
```

Runs `python -m unittest discover -s tests` with the virtualenv interpreter. Tests use synthetic landmarks and images. They do not open a camera or a window.

## Models

Download these Google MediaPipe files into `models/` on first run. Skip a file that already exists and is larger than 100 KB. Send no camera data with the download.

- Hand landmarker: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
- Face landmarker: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
- Pose landmarker lite: `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`
- Selfie segmenter, landscape: `https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite`

If a URL fails, stop and report it. Do not substitute a file from another project.

Use the CPU delegate. Create the tasks once per session and close them on exit.

## Camera

Prefer a device whose name contains `FaceTime` or `MacBook`. Remember the working index in `.anime-frame.json`. `[` and `]` change it.

If macOS denies the camera, say so in the terminal and name the app that needs permission under **System Settings → Privacy & Security → Camera**. That is Terminal when `./run` was started from Terminal, and Cursor when it was started from Cursor. Do not cycle to a random index after a permission failure.

The picture is mirrored in the preview and on the virtual camera. Detection runs on that mirrored picture.

## When an effect needs the empty room

Clear starts immediately. Goku Instant Transmission, and any later effect marked “replaces the person”, waits for a background.

Capture lasts 3 seconds. The chooser counts down 3, 2, 1, and the terminal prints the same second as it changes. The preview and the virtual camera stay free of that text. Keep a median of the frames from the last half-second. Then tell them they can sit down. The Load background row and Space both repeat this, including when a room is already stored. A missing background never blocks an effect that only draws on top of the live person.

The Instant Transmission card may show `assets/instant_transmission_guide.png`. That still stays on this Mac, is gitignored, and is never drawn on the preview.

## Adding an effect

1. Add a file in `anime_frame/effects/` with a unique `id`, a short `title`, a one-line `hint`, and `replaces_person`.
2. Keep pose tests and timing tests in `tests/` with synthetic points. No camera.
3. Add the row to `ROADMAP.md` if it is not there yet.
4. Give it the next digit key only when the menu still has room; past nine, the mouse and the on-screen chooser are enough.
5. Draw inside the person bounds plus a small margin when the effect composites a mask. Use the full frame only when a light has to reach the frame edge.

## Done

A phase is done when `./run test` passes, `./run` opens the preview on the built-in camera, and the new effect can be selected from the chooser. For a person-replacing effect, also confirm an empty background and a return to the live picture.
