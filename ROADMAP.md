# Anime Frame roadmap

Anime Frame puts anime-style animations on your real camera. You stay on your Mac, a pose or a key starts a short original animation, and Teams can take the picture through OBS Virtual Camera.

The effect name is the name in this file. The “inspired by” column is only a reminder of the fantasy. It is not a title, a file name, or a sound to go find.

| Effect name | What you see | Inspired by |
| --- | --- | --- |
| Goku Instant Transmission | Two fingers on the forehead, light collapses inward, you are gone, the same pose brings you back | Dragon Ball |
| Super Saiyan | A gold aura locks on, the hair lifts and turns gold, and you stay in the chair | Dragon Ball |
| Kamehameha | Hands cupped together at the side, a blue-white core charges, then a beam crosses the frame | Dragon Ball |
| Kikōhō | Hands stacked in front of the chest, fingers forming a triangle, then a large square beam | Tien Shinhan’s Tri-Beam |

## Phase 0 — One command

- [x] Project layout from `AGENT.md`
- [x] `./run` creates the virtualenv, installs dependencies, downloads models, and opens the camera
- [x] Built-in camera is chosen by name and remembered in `.anime-frame.json`
- [x] Chooser window plus a clean preview titled `Anime Frame Preview`
- [x] Clear effect: mirrored live video, no overlay
- [x] Effect registry loads every module in `anime_frame/effects/`
- [x] `./run teams` sends the clean preview to OBS Virtual Camera
- [x] `./run test` passes without a camera or a window
- [x] `.gitignore` excludes `.venv/`, `models/`, `.anime-frame.json`, `__pycache__/`, `build/`, and `dist/`

## Phase 1 — Instant Transmission

Ship this before any later effect. Other lights can wait.

- [x] **Goku Instant Transmission.** Replaces the person. Index and middle fingers together on the forehead, ring and pinky folded, held until the pose window fills. About 0.45 seconds of vertical white and pale-cyan streaks inside the silhouette, a short flash at the forehead, and the body collapses into that point. The empty room remains. The same pose, or Escape, restores live video from the forehead downward. A spread V, one finger, or a temple point does not fire it. The chooser title is exactly `Goku Instant Transmission`.
- [x] Instant Transmission plays the supplied teleport sound, `assets/instant_transmission.mp3`, with `/usr/bin/afplay`. The file stays on this Mac and is gitignored.
- [x] Background capture lasts 3 seconds when a person-replacing effect is armed and no room is stored yet. The chooser counts down 3, 2, 1. The stored image is the median of the last half-second. The preview and the virtual camera stay free of that text.
- [x] The chooser has a **Load background** row. Choosing it starts a fresh 3-second capture and the countdown, even when a room is already stored. Space does the same.
- [x] The Instant Transmission card shows the local Goku still, `assets/instant_transmission_guide.png`. The file is gitignored. The preview and the virtual camera never draw it.
- [x] Return fires the active effect without a pose. Escape cancels it.

## Phase 2 — Signature moves

Build these after Instant Transmission. Each one leaves you in the chair. The pose for Super Saiyan is still open.

- [ ] **Super Saiyan.** Stays in frame. A gold aura locks onto the silhouette and the hair lifts and turns gold. The face stays recognizable.
- [ ] **Kamehameha.** Stays in frame. Both hands cupped together at the side. A blue-white core charges, then a beam crosses the frame.
- [ ] **Kikōhō.** Stays in frame. Both hands stacked in front of the chest, fingers forming a triangle, as in the Tri-Beam. A large square beam fires from that shape. This is Tien Shinhan’s attack.

## Phase 3 — Presence

These keep a call interesting while you remain seated. Build them only after the signature moves.

- [ ] **Echo.** One open hand sweeps across the chest. Fading copies of your silhouette trail the motion for about one second, then live video continues. You never leave.
- [ ] **Ash.** Thumb and index finger pinch in front of the chest. The silhouette lifts away as embers. The empty room remains. A second pinch, or Escape, brings the embers back down into the live picture.
- [ ] **Statue.** Both hands on the hips, elbows out. Your current silhouette freezes in the chair while the room stays live. Step aside and the still figure remains. The same pose, or Escape, clears it.

## Phase 4 — Other exits

Each one removes the person in a different direction from Goku Instant Transmission. Build them only after Presence.

- [ ] **Gate.** Both palms toward the camera at shoulder width. A vertical slit of light opens down the torso, you slide into it, and the slit closes on the empty room. Repeat, or Escape, to come back.
- [ ] **Shatter.** A single clap. Cracks flash across the silhouette, shards drop off the bottom of the frame, and the empty room remains. Escape restores live video without playing the shatter backward.
- [ ] **Tide.** Arms crossed over the chest. A bright horizontal line climbs from the waist to above the head and leaves the empty room behind it. The same pose, or Escape, brings the line back down.
- [ ] **Crown.** One extended index finger on the top of the head, the other fingers folded. A ring expands from that point and wipes the silhouette outward. This is the outward partner to Goku Instant Transmission’s inward collapse. The same pose, or Escape, reverses it.

## Phase 5 — This Mac, ready for a call

- [ ] `README.md` with `./run`, `./run teams`, the pose table, and the camera-permission step
- [ ] One-time OBS note: install OBS, allow the camera extension, start and stop Virtual Camera once, then quit OBS before `./run teams`
- [ ] Unsigned local `Anime Frame.app` built on this Mac, with a camera-usage description and no microphone key
- [ ] A test call checklist: disappearance, empty room, return, and confirmation that Instant Transmission shows on a second device

## Later

- Reload effects when a file in `anime_frame/effects/` changes, without restarting the camera
- Optional local recording, off unless a flag is passed
- Linux camera and `v4l2loopback`, only after the Mac path is solid
- A way to turn a single effect off without leaving the app
- Per-effect strength, saved in `.anime-frame.json`

## Not in this project

- Docker, for the Mac camera or for Teams
- Uploading frames or using a microphone
- Character sprites or franchise names on the preview. The Instant Transmission sound and the chooser still are local files and are not published.
- A dependency on any other webcam-effect repository
