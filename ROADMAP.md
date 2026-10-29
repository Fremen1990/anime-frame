# Anime Frame roadmap

Anime Frame puts anime-style animations on your real camera. You stay on your Mac, a pose or a key starts a short original animation, and Teams can take the picture through OBS Virtual Camera.

The effect name is the name in this file. The “inspired by” column is only a reminder of the fantasy. It is not a title, a file name, or a sound to go find.

| Effect name | What you see | Inspired by |
| --- | --- | --- |
| Slip | Two fingers on the forehead, light collapses inward, you are gone, the same pose brings you back | A blink-step out of the room |
| Ascend | Hands up beside the head, a gold-white aura locks on and stays until you pose again | A powered transformation |
| Lance | Hands cupped at the chest, a charge, then a beam across the frame while you stay | An energy wave |

## Phase 0 — One command

- [ ] Project layout from `AGENT.md`
- [ ] `./run` creates the virtualenv, installs dependencies, downloads models, and opens the camera
- [ ] Built-in camera is chosen by name and remembered in `.anime-frame.json`
- [ ] Chooser window plus a clean preview titled `Anime Frame Preview`
- [ ] Clear effect: mirrored live video, no overlay
- [ ] Effect registry loads every module in `anime_frame/effects/`
- [ ] `./run teams` sends the clean preview to OBS Virtual Camera
- [ ] `./run test` passes without a camera or a window
- [ ] `.gitignore` excludes `.venv/`, `models/`, `.anime-frame.json`, `__pycache__/`, `build/`, and `dist/`

## Phase 1 — The three lights

Ship these before any later effect.

- [ ] **Slip.** Replaces the person. Index and middle fingers together on the forehead, ring and pinky folded, held until the pose window fills. About 0.4 seconds of vertical white and pale-cyan streaks inside the silhouette, a short flash at the forehead, and the body collapses into that point. The empty room remains. The same pose, or Escape, plays the reverse and restores live video. A spread V, one finger, or a temple point does not fire it.
- [ ] **Ascend.** Stays in frame. Both wrists above the shoulders and outside the head. About 0.7 seconds of rising sparks and a white-gold flash, then a sustained rim of light just outside the body that follows movement. A warmer tint on the person, light enough that the face stays recognizable. The same pose, or Escape, fades the aura in about 0.4 seconds.
- [ ] **Lance.** Stays in frame. Both wrists close together in front of the chest, fingers extended. A core grows between the hands for about 0.8 seconds. The beam then travels to the frame edge that is farther from the hands, in about 0.55 seconds, and fades. The core is white-cyan and the edge is pale gold. Hands separating during the charge resets it.
- [ ] A distinct synthesized sound for each of the three, generated on first use under `assets/`, each under half a second. No downloaded audio.
- [ ] Background capture runs only when a person-replacing effect is armed and no background is stored yet.
- [ ] Return fires the active effect without a pose. Escape cancels it.

## Phase 2 — Presence

These keep a call interesting while you remain seated. Build them only after Phase 1 is checked.

- [ ] **Echo.** One open hand sweeps across the chest. Fading copies of your silhouette trail the motion for about one second, then live video continues. You never leave.
- [ ] **Ash.** Thumb and index finger pinch in front of the chest. The silhouette lifts away as embers. The empty room remains. A second pinch, or Escape, brings the embers back down into the live picture.
- [ ] **Statue.** Both hands on the hips, elbows out. Your current silhouette freezes in the chair while the room stays live. Step aside and the still figure remains. The same pose, or Escape, clears it.

## Phase 3 — Other exits

Each one removes the person in a different direction from Slip. Build them only after Phase 2.

- [ ] **Gate.** Both palms toward the camera at shoulder width. A vertical slit of light opens down the torso, you slide into it, and the slit closes on the empty room. Repeat, or Escape, to come back.
- [ ] **Shatter.** A single clap. Cracks flash across the silhouette, shards drop off the bottom of the frame, and the empty room remains. Escape restores live video without playing the shatter backward.
- [ ] **Tide.** Arms crossed over the chest. A bright horizontal line climbs from the waist to above the head and leaves the empty room behind it. The same pose, or Escape, brings the line back down.
- [ ] **Crown.** One extended index finger on the top of the head, the other fingers folded. A ring expands from that point and wipes the silhouette outward. This is the outward partner to Slip’s inward collapse. The same pose, or Escape, reverses it.

## Phase 4 — This Mac, ready for a call

- [ ] `README.md` with `./run`, `./run teams`, the pose table, and the camera-permission step
- [ ] One-time OBS note: install OBS, allow the camera extension, start and stop Virtual Camera once, then quit OBS before `./run teams`
- [ ] Unsigned local `Anime Frame.app` built on this Mac, with a camera-usage description and no microphone key
- [ ] A test call checklist: disappearance, empty room, return, and confirmation that the aura and the beam show on a second device

## Later

- Reload effects when a file in `anime_frame/effects/` changes, without restarting the camera
- Optional local recording, off unless a flag is passed
- Linux camera and `v4l2loopback`, only after the Mac path is solid
- A way to turn a single effect off without leaving the app
- Per-effect strength, saved in `.anime-frame.json`

## Not in this project

- Docker, for the Mac camera or for Teams
- Uploading frames or using a microphone
- Character sprites, franchise names on screen, or copied sound from a show
- A dependency on any other webcam-effect repository
