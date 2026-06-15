# CastPolish

A local, open-source alternative to Auphonic for podcast and audio post-production.  
Runs entirely on your machine — no cloud, no subscription, no audio ever leaves your device.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![macOS](https://img.shields.io/badge/macOS-full_support-brightgreen)
![Linux](https://img.shields.io/badge/Linux-supported-green)
![Windows](https://img.shields.io/badge/Windows-supported-green)

![Process Audio UI](screenshots/process-audio.png)
![Settings & Dependencies](screenshots/settings.png)

---

## Platform support

| Feature | macOS | Linux | Windows |
|---|:---:|:---:|:---:|
| Web UI (`castpolish.py serve`) | ✅ | ✅ | ✅ |
| Audio processing & loudness normalization | ✅ | ✅ | ✅ |
| Whisper transcription | ✅ | ✅ | ✅ |
| Tiered noise reduction (afftdn / noisereduce / DeepFilterNet) | ✅ \* | ✅ | ✅ |
| AI shownotes via Ollama | ✅ | ✅ | ✅ |
| Embedded MP3/M4A chapter markers | ✅ | ✅ | ✅ |
| PDF & Word (`.docx`) document export | ✅ | ✅ | ✅ |
| Speaker diarization (pyannote.audio) | ✅ | ✅ | ✅ |
| In-app install / update buttons | ✅ | ✅ | ✅ |
| Processing log file | ✅ | ✅ | ✅ |
| `install.command` one-click installer | ✅ | — | — |
| `create_macos_app.py` native `.app` launcher | ✅ | — | — |

Linux and Windows users run `python3 castpolish.py serve` directly and open `http://localhost:8765` — no `.app` needed. All audio processing, transcription, and AI features are fully cross-platform.

\* **Intel Macs:** DeepFilterNet works, but requires Python 3.11 — PyTorch dropped Intel-Mac support after torch 2.2.2, and DeepFilterNet's prebuilt Intel wheels stop at Python 3.11. Both `install.command` and the in-app Install button detect Intel CPUs and handle this automatically (installing `python@3.11` via Homebrew if needed). Apple Silicon Macs use the latest packages with no pins.

---

## What it does

- **Quality presets** — one click sets the right model and noise reduction: ⚡ *Quick draft* (fast review copy), 🎙️ *Production* (publication quality), 🎯 *High accuracy* (when exact wording matters — legal, theological, medical; pairs with vocabulary hints)
- **Vocabulary hints** — list names and domain terms (e.g. "Lutheran Church—Missouri Synod") and Whisper transcribes them dramatically more reliably
- **EBU R128 loudness normalization** — two-pass measurement and linear correction to a configurable target (default −16 LUFS, podcast standard)
- **Tiered noise reduction** — three levels, each only appears if its package is installed:
  - *Standard* — ffmpeg `afftdn` (always available, fast)
  - *Dynamic* — [noisereduce](https://github.com/timsainburg/noisereduce) spectral subtraction (adapts over time)
  - *AI Enhanced* — [DeepFilterNet3](https://github.com/Rikorose/DeepFilterNet) neural speech enhancement (highest quality, runs in an isolated venv)
- **Whisper transcription** — word-level timestamps via [faster-whisper](https://github.com/guillaumekientz/faster-whisper), exported as HTML, WebVTT, and Auphonic-compatible JSON
- **Confidence review** — the HTML transcript editor flags words Whisper was unsure about; pick a threshold (50–90 %) and step through flagged words with ‹ › to verify them against the audio. Pairs with the 🎯 High accuracy preset
- **Cancellable jobs** — a ✕ Cancel button on queued and running jobs stops the pipeline (kills a running ffmpeg/DeepFilterNet immediately) and cleans up partial outputs
- **AI shownotes** — chapter titles, long summary, brief summary, and tags via [Ollama](https://ollama.com) (local LLM, no API key)
- **Chapter markers** — detected chapters are embedded directly into the MP3/M4A (ID3 CHAP/CTOC or an ffmpeg remux) so podcast apps show jump points, titled by Ollama when available
- **PDF & Word documents** — every job also exports a reader-friendly `.pdf` and an editable `.docx`: a title page with the brief summary and tags, the long summary, and the full transcript organized into chapter sections and clean, sentence-split paragraphs. An optional **Enhanced documents** toggle runs a local-LLM grammar cleanup over each paragraph, with a ±15 % word-count guardrail that keeps the original wording if the model drifts
- **Speaker diarization** — who said what, via pyannote.audio (requires free HuggingFace token)
- **Processing log** — a `.log` file saved alongside every output detailing all settings, processing steps with timestamps, loudness measurements, and output file sizes
- **In-app install buttons** — install missing optional packages (noisereduce, pyannote.audio, DeepFilterNet) directly from the Dependencies panel without touching a terminal
- **macOS `.app` launcher** — native app with Dock icon and branded icon (macOS only)

---

## Quick start

### macOS (easiest — double-click installer)

1. Clone or download the repo
2. Double-click **`install.command`** in Finder
3. Follow the prompts — it installs Homebrew, ffmpeg, Python packages, and optionally builds the `.app`

### All platforms (manual)

```bash
# 1. Install ffmpeg (required)
#   macOS:   brew install ffmpeg
#   Ubuntu:  sudo apt install ffmpeg
#   Windows: https://ffmpeg.org/download.html

# 2. Clone and install
git clone https://github.com/abc3-Mac/castpolish.git
cd castpolish
pip install flask flask-cors pyloudnorm soundfile noisereduce numpy mutagen fpdf2 python-docx

# 3. Optional: Whisper transcription
pip install faster-whisper

# 4. Start
python3 castpolish.py serve
# Open http://localhost:8765
```

---

## install.command (macOS)

Double-click `install.command` in Finder for a guided setup. It is **idempotent** — safe to run on a fresh machine or to update an existing install.

Steps it handles:
1. Homebrew
2. ffmpeg
3. Python 3.10+
4. `git pull` (or fresh clone if not yet installed)
5. Core pip packages
6. Optional: faster-whisper, Ollama + llama3.2, pyannote.audio, DeepFilterNet venv
7. Build `CastPolish.app` and optionally copy to `/Applications`

---

## Optional packages

All optional packages can be installed from the **Dependencies panel** in the web UI (click **Install** next to any missing package), or manually:

| Package | Feature | Install |
|---|---|---|
| `faster-whisper` | Whisper transcription | `pip install faster-whisper` |
| `noisereduce` + `soundfile` | Dynamic noise reduction | `pip install noisereduce soundfile` |
| `pyannote.audio` | Speaker diarization | `pip install pyannote.audio` |
| DeepFilterNet | AI noise reduction | Install button in UI (builds isolated venv) |
| Ollama | AI shownotes | [ollama.com](https://ollama.com) → `ollama pull llama3.2` |

The web UI automatically shows only the noise reduction modes whose packages are installed — nothing breaks if a package is missing.

---

## DeepFilterNet (AI noise reduction)

DeepFilterNet runs in a dedicated virtual environment at `~/.castpolish/df_venv/` to avoid a numpy version conflict with pyannote.audio. This happens automatically — click **Install** in the Dependencies panel and CastPolish handles everything including the Rust compiler if needed.

- Native sample rate: 48 kHz (CastPolish pre-converts your file automatically)
- Runs on CPU — ~10–60× real-time on Apple Silicon
- Model (~80 MB) downloads to `~/.cache/DeepFilterNet/` on first use
- **Intel Macs:** the installer automatically uses Python 3.11 with `torch==2.2.2` (the last PyTorch release with Intel-Mac wheels). Expect slower processing than Apple Silicon, but it works. If the install fails, run `brew install python@3.11` and retry.

---

## Processing log

Every completed job writes a `{title}.log` file alongside the audio, VTT, JSON, and HTML outputs:

```
══════════════════════════════════════════════════════════════
  CastPolish v1.7.0  —  Processing Log
  Generated : 2026-06-07 15:09:41
══════════════════════════════════════════════════════════════

  INPUT
    File        :  My Episode.m4a
    Duration    :  13:44
    Size        :  12.7 MB

  SETTINGS
    Noise mode  :  AI Enhanced (DeepFilterNet3)
    Normalize   :  Yes  →  target -16.0 LUFS (EBU R128)
    Transcribe  :  Yes  (model: small, task: transcribe, language: auto-detect)
    Diarization :  No
    Output fmt  :  MP3

  PROCESSING STEPS
    [00:00]  Processing: My Episode.m4a
    [00:13]  DeepFilterNet enhancement complete.
    [00:23]  Applying loudness correction (pass 2/2, -32.3 → -16.0 LUFS)…
    ...

  Total processing time :  2:00
══════════════════════════════════════════════════════════════
```

A **Log** download link appears in the results table alongside Audio / HTML / PDF / DOCX / JSON / VTT.

---

## Output files

Each processed file produces a folder named after the audio:

```
~/CastPolish-output/
  My-Episode/
    My Episode.mp3     ← improved audio (−16 LUFS, embedded chapter markers)
    My Episode.html    ← interactive transcript editor with audio player
    My Episode.pdf     ← reader-friendly document (summary + chaptered transcript)
    My Episode.docx    ← editable Word version of the document
    My Episode.vtt     ← WebVTT captions (YouTube-compatible)
    My Episode.json    ← Auphonic-compatible word-level transcript
    My Episode.log     ← processing log (settings, steps, timings)
```

---

## Command-line usage

```bash
# Start the web server
python3 castpolish.py serve
python3 castpolish.py serve --port 9000
python3 castpolish.py serve --output-dir ~/Desktop/podcast-output

# Process a file directly (no browser needed)
python3 castpolish.py process "episode.mp3" \
  --model small \           # tiny | base | small | medium | large-v2 | large-v3 | large-v3-turbo
  --format mp3 \            # mp3 or mp4 (aac)
  --language en \
  --lufs -16 \
  --title "Episode Title" \
  --output-dir ~/my-output \
  --denoise                 # enable afftdn noise reduction

# Batch processing
for f in ~/Podcasts/*.mp3; do
    python3 castpolish.py process "$f" --model small
done
```

---

## Speaker diarization

Requires a free [HuggingFace](https://huggingface.co) account and accepting the pyannote model license:

```bash
pip install pyannote.audio
```

Enter your HuggingFace token in Settings → enable Diarization in the UI.  
Uses Apple Metal (MPS) on Apple Silicon automatically for faster processing.

---

## AI shownotes (Ollama)

```bash
# macOS
brew install ollama
ollama pull llama3.2

# Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
```

CastPolish generates chapter titles, a long summary, a brief summary, and suggested tags — all locally.

---

## Performance

| Hardware | `tiny` | `small` | `medium` |
|---|---|---|---|
| Apple Silicon (M-series) | ~0.1× realtime | ~0.3× realtime | ~0.8× realtime |
| Intel Mac / Linux x86 | ~0.5× realtime | ~1.5× realtime | ~4× realtime |

*"0.3× realtime" = a 60-min file takes ~18 min. Apple Silicon uses Core ML acceleration.*

**DeepFilterNet** (AI noise reduction): ~10–60× realtime on CPU (independent of Whisper model).

---

## Memory requirements

| Component | Peak RAM |
|---|---|
| Whisper tiny | ~150 MB |
| Whisper small (default) | ~450 MB |
| Whisper medium | ~1.2 GB |
| Whisper large-v2/v3 | ~2.5 GB |
| Ollama + llama3.2 | ~2 GB |
| pyannote.audio diarization | +1–1.5 GB during pass |
| DeepFilterNet (isolated venv) | +~500 MB during processing |

**Recommended minimums:** 8 GB RAM for `small` model; 16 GB for `medium` + Ollama simultaneously.

---

## Configuration

Settings saved to `~/.castpolish/config.json`. Configure via the web UI Settings tab:

- Output directory
- Target loudness (LUFS)
- Ollama host and model
- HuggingFace token (for diarization)

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

- [faster-whisper](https://github.com/guillaumekientz/faster-whisper) — OpenAI Whisper via CTranslate2
- [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) — AI speech enhancement
- [noisereduce](https://github.com/timsainburg/noisereduce) — non-stationary noise reduction
- [ffmpeg](https://ffmpeg.org) — audio processing
- [Ollama](https://ollama.com) — local LLM inference
- [Flask](https://flask.palletsprojects.com) — local web server
- Inspired by [Auphonic](https://auphonic.com)
