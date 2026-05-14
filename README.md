# audiowmark-desktop

A PyQt6 desktop GUI for [audiowmark](https://github.com/swesterfeld/audiowmark) — the robust audio watermarking tool by Stefan Westerfeld.

Embeds invisible, cryptographically secured watermarks into audio files. The watermark survives MP3/OGG re-encoding at 128 kbit/s or higher and can be detected from a copy without the original file.

## Features

- **Add Watermark** — embed a watermark into WAV, MP3, or FLAC files with configurable strength
- **Get Watermark** — decode and verify watermarks; all keys in your key directory are tried automatically
- **Key Management** — generate and manage audiowmark keys and HMAC secrets
- **Cryptographic payload** — metadata (copyright, artist, title, purpose) is never stored directly in the audio; only its HMAC-SHA256 hash is embedded, making it one-way and unforgeable
- **Database** — maps payload hashes back to metadata for verified decoding
- **MP3 support** — automatic ffmpeg pipe routing to work around libmpg123 frame-count limitations
- **Key rotation** — multiple keys supported; all are tried automatically on decode

## Security model

| Property | This tool |
|---|---|
| Payload readable without key | No — private audiowmark key required |
| Payload forgeable | No — HMAC secret required |
| Watermark removable losslessly | No — private audiowmark key required |
| Metadata recoverable from payload alone | No — one-way HMAC |
| Multiple key rotation | Yes |

## Installation

### Via .deb package (Linux, recommended)

Download the latest `.deb` for your architecture from the [Releases](../../releases) page:

```bash
sudo apt install ./audiowmark-desktop_<version>_amd64.deb
# or for ARM:
sudo apt install ./audiowmark-desktop_<version>_arm64.deb
```

The package bundles a compiled `audiowmark` binary — no separate installation needed.

**Optional:** install `ffmpeg` for MP3 input support:

```bash
sudo apt install ffmpeg
```

### From source

**Requirements:**

- Python 3.8+
- PyQt6 (`pip install pyqt6`)
- [audiowmark](https://github.com/swesterfeld/audiowmark) in `$PATH`
- ffmpeg (optional, for MP3 input)

```bash
git clone https://github.com/huddx01/audiowmark-desktop.git
cd audiowmark-desktop
pip install pyqt6
python3 src/audiowmark_gui.py
```

## Usage

1. Go to **Key Management**, choose a keys directory, and generate at least one audiowmark key and one HMAC secret.
2. In **Add Watermark**, select your input file, fill in the metadata fields (Copyright is mandatory), choose a key and secret, and click *Add Watermark*.
3. In **Get Watermark**, select a watermarked file — all keys are tried automatically and the matching metadata is displayed.

### Watermark strength reference

| Strength | Use case |
|---|---|
| 10.0 (default) | Survives MP3/OGG at 128 kbit/s+ — good balance |
| 13.0 – 15.0 | Multiple conversions, low bitrate (64 kbit/s) |
| 15.0 – 20.0 | Maximum robustness; slight audibility possible |

## Building the .deb locally

```bash
sudo apt-get install autoconf automake libtool pkg-config \
  libsndfile1-dev libmpg123-dev libzita-resampler-dev \
  libfftw3-dev libgcrypt20-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswresample-dev \
  zstd fakeroot

bash packaging/build_deb.sh 1.0.0
# output: dist/audiowmark-desktop_1.0.0_amd64.deb
```

## License

Copyright (C) 2026 huddx01, Sojuzstudio

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See [LICENSE](LICENSE) for the full text.

audiowmark itself is © Stefan Westerfeld, licensed under the LGPL v2.1+.
