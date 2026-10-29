# Selected local audio

Selected by the user on 2026-10-29. The MP3 files are local, gitignored assets. The app does not download them at runtime.

| Local filename | Selection / preview | Duration | Playback |
| --- | --- | --- | --- |
| `super_saiyan_aura.mp3` | [S1 — Super Saiyan Aura](https://www.myinstants.com/en/instant/super-saiyan-aura/) | 5.784 s | Source for opening-once and steady-tail WAVs |
| `kamehameha_charge.mp3` | [K1 — Charge](https://www.myinstants.com/en/instant/kamehameha-charge-98464/) | 6.200 s | Begins at the forward starting gesture; stops when hands move to the side |
| `kamehameha_hold.mp3` | [K1 — Hold](https://www.myinstants.com/en/instant/kamehameha-hold-8778/) | 3.228 s | Loops when the side pose is confirmed, until the final forward push or cancellation |
| `kamehameha_release.mp3` | [K1 — Fire](https://www.myinstants.com/en/instant/kamehameha-fire-67210/) | 5.702 s | Plays on release |
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

## Prepared Super Saiyan playback

`super_saiyan_start.wav` (30.44 s) preserves the beginning of S1 once, then continues with its steady aura. `super_saiyan_sustain.wav` (28.56 s) contains only the steady portion and is the only file looped. Both are 48 kHz stereo PCM, local and gitignored; the original MP3 is preserved.

Recipe: take 1.70–5.45 seconds of the source, join the tail to the head with a 180 ms crossfade, and repeat that cycle eight times per bed. The opening preserves source audio through 1.88 seconds before continuing into those cycles. Long beds reduce afplay restart gaps; they do not guarantee sample-accurate gapless playback between processes. Run `.venv/bin/python -m anime_frame.audio_prepare` to reproduce them (ffmpeg required for preparation only). These are edits of the chosen recording, not synthesized replacements. The cut is based on waveform analysis; listening acceptance is pending.
