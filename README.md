# Image ↔ Audio RGB Converter

Convert an RGB image into three independent mono WAV tracks (`R`, `G`, `B`), process them in a DAW, and reconstruct the image from the edited audio. The project uses Pillow for RGB channel split/merge and Python's `wave` module for uncompressed WAV I/O, which makes the format simple, inspectable, and easy to script.

This repository contains two frontends over the same core idea:
- `im_au.py` — command-line interface for encoding and decoding.
- `im_au_gui.py` — Tkinter desktop GUI with file dialogs, mode selection, and a log panel.

## Table of contents

- [Preview](#preview)
- [Overview](#overview)
- [Architecture](#architecture)
- [Data model](#data-model)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [CLI usage](#cli-usage)
- [GUI usage](#gui-usage)
- [Format specification](#format-specification)
- [Signal mapping](#signal-mapping)
- [DAW workflow](#daw-workflow)
- [Failure modes](#failure-modes)
- [Development notes](#development-notes)
- [Roadmap](#roadmap)
- [License](#license)

## Preview

The following examples show the same source image (`output/test.png`) reconstructed after applying different audio effects independently to the R, G, and B WAV tracks in a DAW.

### Clean decode (no effects)

Baseline reconstruction with no audio processing applied. Output is visually identical to the original.

![Clean decode](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek.png)

### Chorus — single pass

Chorus effect applied to one or more channels. The phase smearing and mild pitch modulation introduced by chorus produces soft color banding and subtle hue drift across the image.

![Chorus single pass](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek_chorus.png)

### Chorus — second pass

Second chorus pass on the same tracks. Each additional chorus pass compounds the phase shift, intensifying the color drift and adding a layered smear effect.

![Chorus second pass](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek_chorus2.png)

### Chorus — third pass

Third chorus pass. At this stage the phase accumulation is strong enough to cause visible spatial displacement of color information across scan lines.

![Chorus third pass](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek_chorus3.png)

### Distortion

Hard distortion applied to one channel. Distortion clips sample amplitudes, which maps to posterization and hard color quantization in the output image.

![Distortion](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek_dist.png)

### Rectifier

Rectifier effect applied to one channel. A rectifier folds negative sample values to positive, which effectively doubles the apparent frequency of the signal and maps to a characteristic brightness inversion pattern in the decoded image.

![Rectifier](https://raw.githubusercontent.com/cryptonhd2004/Image-audio-decoder-encoder/main/output/rek_rectifier.png)

## Overview

The encoder loads an image in RGB mode, splits it into three single-band images, and writes each band as a separate mono 16-bit PCM WAV file. The decoder reads the three WAV files back, converts the samples into byte streams, reconstructs three grayscale bands, and merges them into a final RGB image.

Unlike the original header-in-audio approach, this version stores image metadata in a sidecar JSON file instead of embedding it into the audio payload. That design is more tolerant of typical DAW-side changes such as slight frame count drift, leading/trailing silence, or editor-specific export behavior.

## Architecture

The project is intentionally minimal and is built around four responsibilities:

1. **Image band extraction** — `Pillow.Image.split()` converts an RGB image into `R`, `G`, and `B` bands.
2. **Byte ↔ PCM conversion** — each 8-bit pixel value is mapped into a 16-bit signed PCM sample for WAV storage.
3. **Metadata persistence** — image dimensions and file references are written to `meta.json` using Python's JSON support.
4. **Band reconstruction** — `Pillow.Image.merge()` reassembles three single-band images into one RGB image.

This separation keeps the audio payload stateless and moves structural metadata into a format that is easier to validate and recover from.

## Data model

An encoded image produces four files:

```text
<prefix>_R.wav
<prefix>_G.wav
<prefix>_B.wav
<prefix>_meta.json
```

The three WAV files carry only channel payload. The JSON sidecar carries dimensions, sample rate, format identifier, and expected channel file names.

## Repository layout

```text
.
├── im_au.py
├── im_au_gui.py
├── README.md
├── output/
│   ├── test.png              ← source image used for examples
│   ├── test_R.wav
│   ├── test_G.wav
│   ├── test_B.wav
│   ├── test_meta.json
│   ├── rek.png               ← clean decode (no effects)
│   ├── rek_chorus.png        ← chorus single pass
│   ├── rek_chorus2.png       ← chorus second pass
│   ├── rek_chorus3.png       ← chorus third pass
│   ├── rek_dist.png          ← distortion
│   └── rek_rectifier.png     ← rectifier
└── .venv/
```

## Requirements

- Python 3.x
- Pillow
- Tkinter — typically included in standard Python distributions on desktop platforms.

The implementation relies on the standard `wave` module for uncompressed WAV handling and on Pillow's `split`/`merge` image operations.

## Installation

Create and activate a virtual environment, then install Pillow:

```bash
py -m venv .venv
.venv\Scripts\activate
python -m pip install Pillow
```

If VS Code or Pylance reports `Import "PIL" could not be resolved`, the usual cause is either a missing Pillow install in the active environment or a mismatched Python interpreter in the editor.

## CLI usage

### Encode

```bash
python im_au.py encode input.png test
```

Outputs:

```text
test_R.wav
test_G.wav
test_B.wav
test_meta.json
```

Set a custom sample rate if needed:

```bash
python im_au.py encode input.png test --sample-rate 48000
```

### Decode

```bash
python im_au.py decode .\test_R_ed.wav .\test_G.wav .\test_B.wav .\test_meta.json reconstructed.png --fit truncate
```

### `--fit` modes

The decoder expects each channel payload length to match `width * height`. The `--fit` option defines how length mismatches are handled.

| Mode | Behavior |
|---|---|
| `strict` | Fail on any mismatch. |
| `truncate` | Trim longer payloads to the expected length. |
| `pad` | Zero-pad shorter payloads to the expected length. |

`truncate` is usually the most practical default for DAW workflows because some editors preserve apparent duration while still modifying the exact frame count or adding a small amount of extra data at export time.

## GUI usage

Launch the GUI with:

```bash
python im_au_gui.py
```

The GUI is built with Tkinter and uses standard file dialogs, form controls, and a scrollable text log.

### GUI features

- Mode switch between **Encode** and **Decode**.
- File selection dialogs for all inputs and outputs.
- Editable sample rate for encoding.
- `fit mode` selection for decoding via combobox.
- Runtime log output in a scrollable text widget.

## Format specification

### WAV constraints

Each color band is stored as:

- mono WAV,
- 16-bit sample width,
- uncompressed PCM,
- identical sample rate across all three channels.

### Metadata sidecar

The sidecar file is JSON and contains the structural information required to reconstruct the image without relying on audio-embedded headers.

Example:

```json
{
  "format": "I2A_RGB_SPLIT_V1",
  "width": 512,
  "height": 512,
  "channels": ["R", "G", "B"],
  "sample_rate": 48000,
  "files": {
    "R": "test_R.wav",
    "G": "test_G.wav",
    "B": "test_B.wav"
  }
}
```

### Validation contract

At decode time, the implementation validates:

- JSON format identifier,
- presence of `width`, `height`, and `files`,
- WAV channel count,
- WAV sample width,
- payload length relative to `width * height`.

## Signal mapping

The conversion is deliberately simple.

For each pixel byte `b` in the range `0..255`, the encoder computes a signed 16-bit sample using:

```text
s = (b - 128) << 8
```

At decode time, the inverse mapping is:

```text
b = clamp((s >> 8) + 128, 0, 255)
```

One pixel byte maps to one PCM sample. The mapping is deterministic and lossless as long as the audio samples are not altered by processing, resampling, normalization, format conversion, or time-domain edits.

## DAW workflow

Recommended workflow:

1. Encode an input image into `R/G/B.wav + meta.json`.
2. Import the three WAVs into a DAW as separate mono tracks.
3. Apply processing independently to each band.
4. Export each track as mono 16-bit PCM WAV at the same sample rate.
5. Decode using the original `meta.json`.

Because `R`, `G`, and `B` are independent tracks, channel-specific processing produces channel-specific visual artifacts. See the [Preview](#preview) section for concrete examples.

### Effect reference

| Effect | Visual result |
|---|---|
| Chorus | Soft color banding, hue drift, spatial smear |
| Distortion / clipping | Posterization, hard color quantization |
| Rectifier | Brightness inversion bands, frequency doubling pattern |
| Delay / echo | Repeated image content offset horizontally |
| Reverb | Diffuse color bleed, soft trailing smear |
| EQ / filtering | Gradual brightness shift, smoothing or sharpening |
| Time-stretch / pitch shift | Severe corruption or unrecoverable data loss |

## Failure modes

### Sample count drift

A DAW can preserve apparent clip duration while still changing the exact number of PCM frames through padding, trimming, render offsets, or export settings. Since `wave` reads the actual frame count from the file header, these changes directly affect the decoded payload length. Use `--fit truncate` to handle small drift.

### Format mismatch

If a track is exported as stereo, floating-point WAV, compressed audio, or a different sample width, decoding will fail or produce invalid output because the implementation expects mono 16-bit PCM WAV input.

### Aggressive processing

Effects that alter timing or buffer structure — time-stretching, pitch shifting with resynthesis, silence trimming, sample-rate conversion — may produce strong corruption or unrecoverable payload divergence. This behavior can be creatively useful but should be treated as intentional data destruction rather than transparent processing.

## Development notes

### Why JSON sidecar instead of an in-band header

Embedding width and height into the first bytes of the audio payload is fragile because the beginning of a rendered audio file is exactly where DAWs often introduce silence, offsets, fades, or render-specific changes. A JSON sidecar makes the decode path easier to validate and much more resilient to typical editing workflows.

### Why separate mono files instead of one multi-channel WAV

Separate mono files are easier to route, process, inspect, mute, reorder, and export in most DAWs. They also align naturally with RGB as three independently editable data streams.

### Why Tkinter for GUI

Tkinter provides standard dialogs and basic desktop controls directly from Python's standard library, which keeps the GUI lightweight and easy to distribute for a utility project.

## Roadmap

- RGBA support (alpha channel as fourth WAV track)
- 16-bit source image support
- Batch encoding via glob patterns
- Preview thumbnails in the GUI log panel
- Optional lossless FLAC export

## License

MIT