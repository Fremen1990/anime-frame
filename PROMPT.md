# Build prompt: Anime Frame

You are building **Anime Frame** in `~/projects/anime-frame`. This folder already contains `AGENT.md`, `ROADMAP.md`, and this prompt. Follow `AGENT.md`. Implement **Phase 0 and Phase 1** from `ROADMAP.md`. Do not implement Phase 2 or later. Do not overwrite this prompt.

Anime Frame is a new application. It puts anime-style animations on a real camera. It is not a rename of an existing webcam project.

## What to copy

Copy **no files**. Do not open `~/projects/vanish_webcam`. Do not copy or adapt any of these, even when a file looks useful:

- `vanish_cam.py`, `goku_effect.py`, `naruto_effect.py`, `teleport_sound.py`, `vanish_sound.py`, `run3.py`
- `test_goku_effect.py`, `test_vanish_cam.py`, `test_naruto_effect.py`, `test_vanish_sound.py`, `test_video_output.py`
- `assets/`, including any image, wav, or mp3
- `models/`, `hand_landmarker.task`, `face_landmarker.task`
- `VanishCam.spec`, `VanishCam.macos.spec`, `BUILD_MACOS.sh`, `BUILD_WINDOWS.bat`, `AVVIA_LOCALE.bat`, `AVVIA_VIRTUAL.bat`, `AVVIA_OBS.bat`
- `README.md`, `MANUAL.md`, `PROMPT_GOKU_TELEPORT.md`
- `.venv-macos/`, `build/`, `dist/`

Install libraries with pip. Download models from the Google URLs in `AGENT.md`. Write every module yourself from the behavior in this prompt.

## What this phase must do

One command, `./run`, opens the built-in camera on a clean mirrored preview. A second window, the chooser, lists **Clear**, **Slip**, **Ascend**, and **Lance**. The preview that can go to a meeting has no text on it.

The three effects:

1. **Slip** removes the person. Two straight fingers held together on the forehead. Light streaks, the body collapses into the forehead, the empty room stays, the same pose brings them back.
2. **Ascend** leaves the person in frame. Both hands beside the head. A gold-white aura charges, then stays stuck to the moving silhouette until the pose is repeated.
3. **Lance** leaves the person in frame. Hands cupped at the chest. A core charges, then a beam crosses the frame.

Return fires the active effect without a pose. Escape cancels it. Space recaptures the empty room, and only Slip asks for that room.

## Product rules

- Python 3.11, 3.12, or 3.13. Dependencies: `mediapipe`, `opencv-python`, `numpy`, `pyvirtualcam`. Pin sane current ranges in `requirements.txt`. Do not depend on `pygame` or `opencv-contrib-python`.
- Default picture size is 1280×720. If a full session cannot hold about 20 fps, lower the capture size to 960×540 in one constant and note that in the README.
- The preview title is `Anime Frame Preview`. The chooser title is `Anime Frame`.
- Mirror the camera before detection and before effects.
- Person mask: landscape selfie segmenter, person class, threshold 0.5, then a small close so the rim is continuous. Cache the mask’s bounding box.
- Pose window, shared by every gesture: sample about ten times a second, fire when eight of the last ten samples passed, clear the window after three failures in a row.
- Slip’s animation is about 0.40 seconds. Ascend’s entrance is about 0.70 seconds and its exit fade is about 0.40 seconds. Lance charges for about 0.80 seconds, the beam travels for about 0.55 seconds, then it fades for about 0.25 seconds.
- Background capture is about three seconds. Use the median of the frames from the last half-second. Terminal text tells the person to step out, then tells them they can return. The chooser may say “step out” as well. The preview stays free of that text.
- Sounds are original, synthesized with `wave`, `math`, and `struct`, written under `assets/` on first use, and played with `/usr/bin/afplay` and a fixed argument list. Slip is a short descending noise sweep. Ascend is a rising tone. Lance is a low tone at the start of the charge and a brighter burst when the beam fires. Each file is under half a second.
- `--debug` prints pose decisions to the terminal. It draws nothing on the video.
- Settings in `.anime-frame.json`: camera index, last effect id. Create the file when either value is first known.

## Suggested modules

You may split a file if it grows past a single responsibility. Keep these boundaries.

`anime_frame/camera.py` opens an index with `cv2.VideoCapture`, sets the size and a buffer of one frame, and lists a preferred index. On macOS, parse camera names and prefer `FaceTime` or `MacBook`. If names cannot be read, start at index 0 and let `[` `]` move. A permission failure raises a clear error and does not try another index.

`anime_frame/background.py` owns the empty-room image for the session.

`anime_frame/segment.py` wraps the selfie segmenter and returns a float mask the same size as the frame.

`anime_frame/pose.py` holds pure functions over NumPy points. Hand points are the 21-point MediaPipe hand. Face points are the face-landmarker mesh; the forehead reference is landmark 10. Body points are the 33-point pose landmarker. Functions return plain numbers and booleans. They do not touch the camera.

`anime_frame/audio.py` resolves a wav path, generates it when absent, and plays it.

`anime_frame/registry.py` imports every non-base module in `anime_frame/effects/` and returns effect instances sorted by menu order.

`anime_frame/effects/base.py` defines the effect type: `id`, `title`, `hint`, `order`, `replaces_person`, `reset()`, and `update(ctx) -> frame`.

`anime_frame/app.py` owns the two windows, the key map in `AGENT.md`, the session, and the virtual camera. The loop is: read, mirror, segment, detect landmarks, update the active effect, show, and optionally send. It does not contain Slip, Ascend, or Lance drawing code.

`run` is a bash script. It `cd`s to its own directory, creates `.venv` when missing, installs requirements when imports fail, and then dispatches:

- `./run` launches the app
- `./run teams` launches with the virtual camera required
- `./run test` launches unittest
- `./run --debug` and `./run teams --debug` pass the debug flag through

## Slip

`replaces_person` is true.

The pose is true only when all of these hold on the same hand, on the mirrored frame:

- Index and middle tips are farther from the wrist than their PIP joints, and each finger is reasonably straight.
- The distance between the index tip and the middle tip is under about half of the shorter of those two fingers.
- Ring and pinky tips are closer to the wrist than their PIP joints.
- The midpoint of the two tips lies near landmark 10, within about a fifth of the face height.
- The thumb is ignored.

While the effect is idle and the pose window fills, play the Slip sound, freeze the current person mask and the current person pixels, and play the leave animation. Ignore new poses until the animation finishes, then hold the stored background.

While the person is gone and the pose window fills again, play the sound and the return animation using that same frozen mask and those same pixels, then resume live video.

Leave, by time `t` from 0 to 1:

- First third: the person is fully visible. Thin vertical streaks move downward inside the mask only. They are white to pale cyan, a few pixels wide, unevenly spaced. A short horizontal flash sits at forehead height.
- Middle third: the mask fades from the forehead downward, so the background shows through from the head toward the feet. The streaks thin out.
- Last third: only fading streaks remain. Then the frame is the stored background.

Return is that timeline reversed, and the last frame is live video.

If the face is missing, the pose is false. Draw only inside the frozen mask’s bounds plus a small margin.

## Ascend

`replaces_person` is false. It never reads the background.

The pose is true when both pose-landmarker wrists are above their shoulders and outside the head width. One raised hand is not enough. Hands on the forehead are not this pose; if the Slip finger test would pass, Ascend does not.

On the first fill of the pose window, play the sound and run the entrance: sparks rise around the silhouette and a white-gold flash peaks before 0.7 seconds. After that, every frame draws a rim just outside the current mask, a few pixels wide, gold at the outer edge and white at the body, plus a few rising sparks. Tint pixels inside the mask slightly warmer. The face must stay recognizable.

The next completed pose, or Escape, fades the rim and the tint over about 0.4 seconds and returns to untreated live video.

The rim follows the live mask every frame. Do not freeze the person.

## Lance

`replaces_person` is false.

The pose is true when both wrists are in front of the torso, between shoulder and hip height, and the wrist-to-wrist distance is under about one shoulder width. At least one hand must show extended fingers. Wrists above the shoulders belong to Ascend, not Lance.

While the window is filling, draw a growing soft core at the midpoint of the wrists. If the pose breaks, drop the charge and clear the core.

When the window fills, play the release sound and fire. The beam starts at the core and reaches the left or right frame edge, whichever is farther from the core, over about 0.55 seconds. It is widest at the hands and narrower at the tip. The center is white-cyan and the fringe is pale gold. It is additive over the live frame. The person stays fully visible. Then fade the beam and return to idle.

## Tests

Add unittest modules that build landmarks in memory.

- Slip fingers together, folded ring and pinky, tips on the forehead: pose accepted.
- The same hand rotated, mirrored, and scaled: still accepted.
- A spread V, a single index finger, an open palm, and tips down at the chest: rejected.
- Ascend with both wrists high and wide: accepted. One wrist high: rejected. Wrists at the chest: rejected.
- Lance with both wrists together at the chest: accepted. Wrists beside the head: rejected. Wrists far apart: rejected.
- The shared pose window fires once when eight of ten samples pass, and three failures clear it.
- Slip’s Escape path returns a gone state to live. Return can start Slip without a pose.
- Registry returns Clear, Slip, Ascend, and Lance in menu order.

Run `./run test`. Do not open the camera in tests.

## After the code runs

Update `ROADMAP.md` checkboxes for the items you actually finished. Write `README.md` with install-free daily use: `./run`, `./run teams`, the four keys, the three poses, the step-out line for Slip, and the macOS camera permission pane. Mention that Teams audio does not carry the effect sounds, because the virtual camera is video only.

Do not build the `.app` in this phase. Do not add Echo, Ash, Statue, Gate, Shatter, Tide, or Crown yet. Their behavior is already specified in `ROADMAP.md` for a later pass.
