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

## The two keys

| Key | Effect |
| --- | --- |
| `0` | Clear |
| `1` | Goku Instant Transmission |

| Key | Action |
| --- | --- |
| Return | Fire the active effect without the pose |
| Escape | Cancel the active effect and return to the live picture |
| Space | Capture the empty room again |
| `[` `]` | Previous and next camera |
| `F` | Fullscreen the preview |
| `Q` | Quit and release the camera |

Click a row in the `Anime Frame` window, or press its number. Goku Instant Transmission shows the pose still and the steps. **Load background** starts a fresh 3-second capture and the countdown, even when a room is already stored. The meeting picture is the other window, `Anime Frame Preview`. That window has no text and no still on it.

## The pose

Hold it until it fires. That takes about a second. The chooser draws the pose next to the selected effect.

| Effect | Pose |
| --- | --- |
| Goku Instant Transmission | Index and middle fingers together on the forehead, ring and pinky folded. You leave. The same pose brings you back. |

A spread V, one finger, or a point at the temple does not fire Goku Instant Transmission.

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
