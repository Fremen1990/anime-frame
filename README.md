# Anime Frame

Anime Frame puts short original animations on your real camera. The picture stays on this Mac. The preview, and Teams when you ask for it, show the camera and the effect only.

## Daily use

From this folder:

```bash
./run
```

The first launch creates `.venv`, installs the dependencies, downloads the models, and opens the built-in camera on Clear. Later launches reuse the last camera and the last effect.

```bash
./run teams
```

The same picture is also sent to OBS Virtual Camera. If that driver is missing, Anime Frame prints the one-time OBS steps and exits.

Install OBS, allow its camera extension, start Virtual Camera, stop it, quit OBS, then run `./run teams` again.

Teams does not carry the effect sounds. The virtual camera is video only. The sounds play on this Mac.

## The keys

| Key | Effect |
| --- | --- |
| `0` | Clear |
| `1` | Goku Instant Transmission |
| `2` | Super Saiyan |
| `3` | Kamehameha |
| `4` | Kikōhō |

| Key | Action |
| --- | --- |
| Return | Kamehameha: start charging, then press again when ready to fire. Kikōhō: fire once. Other effects: trigger |
| Escape | Cancel the active effect and return to the live picture |
| Space | Capture the empty room again |
| `[` `]` | Previous and next camera |
| `F` | Fullscreen the preview |
| `Q` | Quit and release the camera |

Click a row in the `Anime Frame` window, or press its number. The selected row shows how to invoke that effect. Goku Instant Transmission uses the local pose still. **Load background** starts a fresh 3-second capture and the countdown, even when a room is already stored. The meeting picture is the other window, `Anime Frame Preview`. That window has no text and no still on it.

Capture is 960×540. On this Mac, Super Saiyan with the hair mask, flames, and both windows held about 15 frames a second at 1280×720 and about 28 at 960×540.

## The poses

The chooser shows the gesture and current attack stage. Instant Transmission and Super Saiyan confirm their gesture in about a second. Kamehameha confirms cupped hands in about 0.3 seconds, then grows its orb for 0.7 seconds. Kikōhō has a short 0.2-second confirmation and no charge stage.

| Effect | Pose |
| --- | --- |
| Goku Instant Transmission | Index and middle fingers together on the forehead, ring and pinky folded. You leave. The same pose brings you back. |
| Super Saiyan | Both fists beside the shoulders. The selected sound accompanies a 1.7-second transformation: your own hair turns gold, flames flow upward, and sparks rise around the silhouette. Lower your hands and it stays active. Repeat the pose or press Escape to fade it out. |
| Kamehameha | **Cup at your side → push forward.** Cup both hands beside either side of the torso and keep them there while the orb grows. Once ready, push both hands toward the camera. The orb follows your hands into the blast and fades with its sound. |
| Kikōhō | Hands together at chest height, aimed toward the camera. One gesture triggers the complete four-second square blast. Lower your hands before another attack. |

Kamehameha waits indefinitely once charged, while tracking stays valid. An early push during buildup cancels instead of firing later. Raising your hands, leaning forward or moving only one hand does not release it. About 300 ms without usable tracking cancels a gesture charge. Escape restores live video immediately. The chooser shows the current instructions; the preview and virtual camera stay free of text.

Return works without tracking: press once to charge Kamehameha, wait for the orb to grow, then press again to fire. It never fires on a timer. Kikōhō needs one Return; presses during playback do not restart it.

## Sounds

The selected Dragon Ball recordings remain local and gitignored. Their links and provenance are in [assets/SOURCES.md](assets/SOURCES.md). No audio is downloaded during sessions.

Kamehameha and Super Saiyan now use a persistent, **output-only** audio stream. Kamehameha plays Charge and then continues that same charge; the separate Hold clip is not used. A push crossfades into a shortened Fire. Super Saiyan plays its opening once and loops only the steady aura section without restarting an audio process. Its visual entrance follows the audio envelope. Deactivation fades audio with the effect.

The app uses macOS `afconvert` to prepare a hash-keyed PCM cache before opening the camera. To prepare or validate it separately, run `.venv/bin/python -m anime_frame.audio_prepare`. There is no ffmpeg requirement. Original MP3s and older prepared WAVs are preserved; the older Saiyan WAV beds are no longer used for playback.

Missing recordings or an unavailable output device leave visuals usable and show a chooser warning. Instant Transmission and Kikōhō keep their one-shot playback. Instant Transmission alone retains its synthesized fallback. The app never opens a microphone, and OBS Virtual Camera carries video only.

## Step out

Goku Instant Transmission needs a picture of the empty room. The capture is 3 seconds. The stored picture is the median of the last half-second. The `Anime Frame` window counts down 3, 2, 1 while that happens. The terminal says:

```text
Step out of the chair.
Step out of the chair. 3
```

Then, when the room is stored:

```text
You can return.
```

The preview and the virtual camera stay free of that text. **Load background** and Space both capture the room again. Clear does not ask you to step out.

## Camera permission

If macOS denies the camera, allow the app that launched `./run` under **System Settings → Privacy & Security → Camera**. That is Terminal when you started it from Terminal, and Cursor when you started it from Cursor. Anime Frame does not switch to another camera after a permission failure.

## Debug

```bash
./run --debug
./run teams --debug
```

Pose decisions print in the terminal. Nothing is drawn on the video.
