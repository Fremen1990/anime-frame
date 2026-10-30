# Selected local audio

Selected by the user on 2026-10-29. The MP3 files are local, gitignored assets. The app does not download them at runtime.

| Local filename | Selection / preview | Duration | Playback |
| --- | --- | --- | --- |
| `super_saiyan_aura.mp3` | [S1 — Super Saiyan Aura](https://www.myinstants.com/en/instant/super-saiyan-aura/) | 5.784 s | Opening once, then a steady region looped in the PCM stream |
| `kamehameha_charge.mp3` | [K1 — Charge](https://www.myinstants.com/en/instant/kamehameha-charge-98464/) | 6.200 s | Plays after the cupped side gesture. The fading tail is skipped; a later slice of this same file loops until the push |
| `kamehameha_hold.mp3` | [K1 — Hold](https://www.myinstants.com/en/instant/kamehameha-hold-8778/) | 3.228 s | Kept on disk. Not played |
| `kamehameha_release.mp3` | [K1 — Fire](https://www.myinstants.com/en/instant/kamehameha-fire-67210/) | 5.702 s | Plays on release, trimmed to 4.2 s |
| `kikoho_release.mp3` | [T1 — Shin Kikōhō](https://www.myinstants.com/en/instant/shin-kikoho-2366/) | 4.023 s | Plays once with a direct attack, with no charge stage |

Instant Transmission continues to use its previously supplied local MP3. Kikōhō has no charging or holding stage.

All five new files were validated with `ffprobe` as MP3 audio. Original download sources and SHA-256 digests:

| Local filename | Download source | SHA-256 |
| --- | --- | --- |
| `super_saiyan_aura.mp3` | [saiyan.mp3](https://www.myinstants.com/media/sounds/saiyan.mp3) | `1b58ad0b5b5e685b782c6f660c44b0325b4d7681597e7af3ddc710c526e6b431` |
| `kamehameha_charge.mp3` | [kame_charge.mp3](https://www.myinstants.com/media/sounds/kame_charge.mp3) | `542789f0fe02b3ffe939f524f24d7278718c0eb086aee09da33a4913f80c3198` |
| `kamehameha_hold.mp3` | [beamhead.mp3](https://www.myinstants.com/media/sounds/beamhead.mp3) | `da0dbccca965a3f3a6b66e2341d7cc3cece4a46f8958bb0814d935992e39e934` |
| `kamehameha_release.mp3` | [basicbeam_fire.mp3](https://www.myinstants.com/media/sounds/basicbeam_fire.mp3) | `93e7955387daa5df5d7cf5e71c984576debcd92cadd0a5c846a39b9db95924d7` |
| `kikoho_release.mp3` | [shin-kikoho_dZH4mUt.mp3](https://www.myinstants.com/media/sounds/shin-kikoho_dZH4mUt.mp3) | `b3d3ad9d69ffac0d99a19cc0a4f6ff08f15600ddea787d991959734e6057369e` |

## Continuous playback preparation

The original MP3s remain unchanged. Native macOS `afconvert` decodes them to 48 kHz stereo PCM before camera processing; cache entries live in ignored `assets/.pcm-cache/` and are keyed by source SHA-256 plus preparation version. Run `.venv/bin/python -m anime_frame.audio_prepare` to prepare or validate them. No ffmpeg is required.

Kamehameha Charge targets -18 dBFS RMS and Fire -16 dBFS, with gain capped for peak headroom. Playback uses Charge through 5.0 s, then loops 3.8–5.0 s of that same Charge with a 180 ms crossfade. Fire is the first 4.2 s, with an 80 ms crossfade from the gesture and a short fade at the trim. The Hold file is not part of the cue.

Super Saiyan retains the source opening and uses only 1.70–5.45 seconds for its sustain, with a 180 ms tail-to-head crossfade. A persistent output stream repeats that cycle without process restart gaps. The source's dynamics are preserved with peak headroom. The prior `super_saiyan_start.wav` and `super_saiyan_sustain.wav` are preserved as legacy derived files and are no longer used by the effect.

These are edits of the user's selected recordings, not synthesized replacements. Listening acceptance and live audiovisual alignment remain pending until tested with the user's gestures and output devices.
