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
| Return | Kamehameha: start → hold → fire, one press per stage. Kikōhō: fire once. Other effects: trigger |
| Escape | Cancel the active effect and return to the live picture |
| Space | Capture the empty room again |
| `[` `]` | Previous and next camera |
| `F` | Fullscreen the preview |
| `Q` | Quit and release the camera |

Click a row in the `Anime Frame` window, or press its number. The selected row shows how to invoke that effect. Goku Instant Transmission uses the local pose still. **Load background** starts a fresh 3-second capture and the countdown, even when a room is already stored. The meeting picture is the other window, `Anime Frame Preview`. That window has no text and no still on it.

On this Mac a Super Saiyan session held about 21 frames a second at 1280×720. Recheck this after effect changes. If sustained performance falls below 20 fps, use 960×540 capture in the camera settings constants.

## The poses

The chooser shows the gesture and the current attack stage. Instant Transmission, Super Saiyan, and Kamehameha's opening pose take about a second to confirm. Kikōhō uses a short confirmation of about 0.2 seconds and has no charge stage.

| Effect | Pose |
| --- | --- |
| Goku Instant Transmission | Index and middle fingers together on the forehead, ring and pinky folded. You leave. The same pose brings you back. |
| Super Saiyan | Both fists beside the shoulders. Gold hair, flames, and lightning stay after you lower your hands. The same pose, or Escape, turns it off. |
| Kamehameha | **Forward → side → forward.** Hold both hands together toward the camera to start. Pull them back and cup them beside either side of your torso to establish the charged hold. Push both hands toward the camera again to fire. |
| Kikōhō | Both hands together at chest height, aimed toward the camera. Fires once immediately after the short gesture confirmation. The selected sound and fading square blast last about four seconds. Lower your hands before another attack. |

A spread V, one finger, or a point at the temple does not fire Goku Instant Transmission. Kamehameha cannot start from the side pose or skip that stage. The side pose takes about 0.3 seconds to confirm; the final push needs two distinct forward observations. It stays charged without a duration limit while tracking remains available. Raising the hands, moving only one hand, or leaning your whole body forward does not release the blast. About 300 ms without usable depth tracking cancels a gesture-driven charge. Escape cancels immediately.

Return works without tracking: for Kamehameha, press once to start, again to enter the charged hold, and again to fire. Keyboard-started stages wait until you advance them; they never fire on a timer. You can also complete the physical stages after a keyboard start. For Kikōhō, one Return plays the whole attack; presses during playback do not restart it.

## Sounds

Super Saiyan, Kamehameha, and Kikōhō use selected local Dragon Ball recordings. Old synthesized WAVs are ignored. Instant Transmission keeps its supplied sound and generated fallback.

The selected clips and their preview links are listed in [assets/SOURCES.md](assets/SOURCES.md). Super Saiyan plays its transformation opening once, then repeats only a crossfaded steady section of that same recording. Kamehameha's forward start plays Charge; the side pose switches to Hold; the final forward push switches to Fire. Kikōhō plays the full Shin Kikōhō recording once with its attack. Escape, switching effects, and quitting stop playback.

The two prepared Saiyan WAVs are already installed locally. To rebuild them from `assets/super_saiyan_aura.mp3`, run `.venv/bin/python -m anime_frame.audio_prepare` with `ffmpeg` available. Preparation is separate from camera sessions. If the prepared files are absent, the original aura clip plays once, without looping its opening.

The audio files stay local and are gitignored. The app never downloads audio during a session.

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
