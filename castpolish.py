#!/usr/bin/env python3
"""
CastPolish — Open-source audio processing & transcription.
A local alternative to Auphonic (auphonic.com).

Quick start:
  pip install -r requirements.txt   # also: brew install ffmpeg
  python castpolish.py serve      # web UI at http://localhost:8765
  python castpolish.py process audio.mp3 --model small
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class _SafeEncoder(json.JSONEncoder):
    """Converts numpy scalars to native Python types before JSON serialization."""
    def default(self, obj):
        try:
            import numpy as _np
            if isinstance(obj, _np.integer):  return int(obj)
            if isinstance(obj, _np.floating): return float(obj)
            if isinstance(obj, _np.bool_):    return bool(obj)
            if isinstance(obj, _np.ndarray):  return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)

# ─── Config file (~/.auphonic-oss/config.json) ───────────────────────────────

CONFIG_DIR      = Path.home() / ".castpolish"
CONFIG_FILE     = CONFIG_DIR / "config.json"
_DF_VENV_DIR    = CONFIG_DIR / "df_venv"
_DF_VENV_PYTHON = _DF_VENV_DIR / "bin" / "python"

__version__ = "1.3.0"

# Patched df/io.py — replaces torchaudio I/O (removed in torchaudio 2.2+) with soundfile.
# Applied automatically after every deepfilternet venv install/upgrade.
_DF_IO_PATCH = '''\
# df/io.py — patched by CastPolish for torchaudio 2.2+ compatibility
# (torchaudio removed torchaudio.info/load/save in 2.2+; soundfile is used instead)
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import soundfile as _sf
import torch
from loguru import logger
from numpy import ndarray
from torch import Tensor
from torchaudio.functional import resample as ta_resample

from df.logger import warn_once
from df.utils import download_file, get_cache_dir, get_git_root


@dataclass
class AudioMetaData:
    sample_rate: int
    num_frames: int
    num_channels: int
    bits_per_sample: int = 16
    encoding: str = "PCM_S"


def load_audio(
    file: str, sr: Optional[int] = None, verbose=True, **kwargs
) -> Tuple[Tensor, AudioMetaData]:
    data, orig_sr = _sf.read(file, always_2d=True, dtype="float32")
    audio = torch.from_numpy(data.T).contiguous()
    meta = AudioMetaData(sample_rate=orig_sr, num_frames=audio.shape[-1],
                         num_channels=audio.shape[0])
    if sr is not None and orig_sr != sr:
        if verbose:
            warn_once(f"Resampling {orig_sr} -> {sr} Hz")
        audio = resample(audio, orig_sr, sr)
    return audio.contiguous(), meta


def save_audio(
    file: str,
    audio: Union[Tensor, ndarray],
    sr: int,
    output_dir: Optional[str] = None,
    suffix: Optional[str] = None,
    log: bool = False,
    dtype=torch.int16,
):
    outpath = file
    if suffix is not None:
        fn, ext = os.path.splitext(file)
        outpath = fn + f"_{suffix}" + ext
    if output_dir is not None:
        outpath = os.path.join(output_dir, os.path.basename(outpath))
    if log:
        logger.info(f"Saving audio file \\'{outpath}\\'")
    audio = torch.as_tensor(audio)
    if audio.ndim == 1:
        audio = audio.unsqueeze(0)
    arr = audio.cpu().numpy().T.astype(np.float32)
    _sf.write(outpath, arr, sr, subtype="FLOAT")


def get_resample_params(method: str) -> Dict[str, Any]:
    params = {
        "sinc_fast":  {"resampling_method": "sinc_interpolation", "lowpass_filter_width": 16},
        "sinc_best":  {"resampling_method": "sinc_interpolation", "lowpass_filter_width": 64},
        "kaiser_fast": {"resampling_method": "kaiser_window", "lowpass_filter_width": 16,
                        "rolloff": 0.85, "beta": 8.555504641634386},
        "kaiser_best": {"resampling_method": "kaiser_window", "lowpass_filter_width": 16,
                        "rolloff": 0.9475937167399596, "beta": 14.769656459379492},
    }
    assert method in params, f"method must be one of {list(params)}"
    return params[method]


def resample(audio: Tensor, orig_sr: int, new_sr: int, method="sinc_fast"):
    return ta_resample(audio, orig_sr, new_sr, **get_resample_params(method))


def get_test_sample(sr: int = 48000) -> Tensor:
    d = get_git_root()
    fp = os.path.join("assets", "clean_freesound_33711.wav")
    if d is None:
        path = download_file(
            "https://github.com/Rikorose/DeepFilterNet/raw/main/" + fp,
            get_cache_dir())
    else:
        path = os.path.join(d, fp)
    sample, _ = load_audio(path, sr=sr)
    return sample
'''


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Merge with existing so we never clobber unrelated keys
    cfg = load_config()
    cfg.update(data)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ─── Optional dependency detection ──────────────────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

try:
    import pyloudnorm as pyln
    HAS_PYLOUDNORM = True
except ImportError:
    HAS_PYLOUDNORM = False

try:
    import noisereduce as nr
    HAS_NOISEREDUCE = True
except ImportError:
    HAS_NOISEREDUCE = False

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

try:
    import whisper as openai_whisper  # fallback if faster-whisper not installed
    HAS_OPENAI_WHISPER = True
except ImportError:
    HAS_OPENAI_WHISPER = False

try:
    from pyannote.audio import Pipeline as PyannotePipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False

# DeepFilterNet runs in an isolated venv (~/.castpolish/df_venv/) to avoid
# numpy version conflicts with pyannote.audio.
HAS_DEEPFILTERNET = _DF_VENV_PYTHON.exists()

# ─── Audio processing ─────────────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    """Return the ffmpeg executable path, searching common install locations."""
    import shutil as _shutil
    if found := _shutil.which("ffmpeg"):
        return found
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(p):
            return p
    return "ffmpeg"  # let it fail with a clear error


_FFMPEG_BIN = _find_ffmpeg()


# ─── PyPI version cache ───────────────────────────────────────────────────────

_pypi_cache: dict = {}  # {pkg: (version_str, timestamp)}
_pypi_cache_lock = threading.Lock()


def _pypi_latest(pkg: str) -> str | None:
    """Return the latest PyPI version of *pkg*, cached for 24 h.
    Returns None on network error or if the cache entry is stale and the
    background refresh hasn't completed yet."""
    with _pypi_cache_lock:
        entry = _pypi_cache.get(pkg)
        if entry and time.time() - entry[1] < 86400:
            return entry[0]
        # Mark as fetching so we don't spawn duplicate threads
        if _pypi_cache.get(f"__fetching_{pkg}"):
            return entry[0] if entry else None
        _pypi_cache[f"__fetching_{pkg}"] = True

    def _fetch():
        try:
            req = urllib.request.Request(
                f"https://pypi.org/pypi/{pkg}/json",
                headers={"User-Agent": f"CastPolish/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            ver = data["info"]["version"]
            with _pypi_cache_lock:
                _pypi_cache[pkg] = (ver, time.time())
        except Exception:
            pass
        finally:
            with _pypi_cache_lock:
                _pypi_cache.pop(f"__fetching_{pkg}", None)

    threading.Thread(target=_fetch, daemon=True).start()
    return entry[0] if entry else None


# ─── Package install helpers ──────────────────────────────────────────────────

def _pip_install(packages: list, log=None, upgrade: bool = False) -> None:
    """Install or upgrade *packages* using this interpreter's pip.
    Streams output lines to *log* callback."""
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        line = line.rstrip()
        if line and log:
            log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed (exit {proc.returncode})")


def _install_deepfilternet_venv(log=None) -> None:
    """Create an isolated venv at ~/.castpolish/df_venv/ and install deepfilternet.
    Uses Rust/cargo if available (required for first-time install)."""
    import venv as _venv

    venv_dir = _DF_VENV_DIR
    if log:
        log(f"Creating virtual environment at {venv_dir} …")
    _venv.create(str(venv_dir), with_pip=True, clear=True)

    pip_bin = str(venv_dir / "bin" / "pip")

    if log:
        log("Upgrading pip in venv…")
    subprocess.run([pip_bin, "install", "--upgrade", "pip"],
                   capture_output=True, check=False)

    if log:
        log("Installing deepfilternet (requires Rust — may take 5–15 min on first run)…")
    cargo_env = Path.home() / ".cargo" / "env"
    if cargo_env.exists():
        cmd = f'source "{cargo_env}" && "{pip_bin}" install deepfilternet'
        proc = subprocess.Popen(["bash", "-c", cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    else:
        proc = subprocess.Popen([pip_bin, "install", "deepfilternet"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    for line in proc.stdout:
        line = line.rstrip()
        if line and log:
            log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"deepfilternet install failed (exit {proc.returncode})")
    # soundfile is needed by our torchaudio compatibility patch
    if log:
        log("Installing soundfile into venv…")
    subprocess.run([pip_bin, "install", "soundfile"],
                   capture_output=True, check=False)
    _apply_df_io_patch(log)
    if log:
        log("✓ DeepFilterNet installed in isolated venv.")


def _apply_df_io_patch(log=None) -> None:
    """Write the soundfile-based df/io.py patch into the venv.
    Called after every install/upgrade to handle torchaudio 2.2+ API removal."""
    try:
        result = subprocess.run(
            [str(_DF_VENV_PYTHON), "-c",
             "import df, os; print(os.path.dirname(df.__file__))"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            if log:
                log("Warning: could not locate df package to apply patch.")
            return
        df_dir = result.stdout.strip()
        io_path = os.path.join(df_dir, "io.py")
        with open(io_path, "w") as fh:
            fh.write(_DF_IO_PATCH)
        if log:
            log("Applied torchaudio 2.2+ compatibility patch to df/io.py.")
    except Exception as exc:
        if log:
            log(f"Warning: patch failed ({exc}) — deepfilternet may not work.")


def _upgrade_deepfilternet_venv(log=None) -> None:
    """Upgrade deepfilternet in the existing isolated venv."""
    pip_bin = str(_DF_VENV_DIR / "bin" / "pip")
    cargo_env = Path.home() / ".cargo" / "env"
    if cargo_env.exists():
        cmd = f'source "{cargo_env}" && "{pip_bin}" install --upgrade deepfilternet'
        proc = subprocess.Popen(["bash", "-c", cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    else:
        proc = subprocess.Popen([pip_bin, "install", "--upgrade", "deepfilternet"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    for line in proc.stdout:
        line = line.rstrip()
        if line and log:
            log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"deepfilternet upgrade failed (exit {proc.returncode})")
    _apply_df_io_patch(log)
    if log:
        log("✓ DeepFilterNet upgraded.")


def _ffmpeg(*args, check=True):
    cmd = [_FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error"] + list(args)
    result = subprocess.run(cmd, capture_output=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")
    return result.returncode == 0


def convert_to_wav(input_path: str, out_wav: str, sample_rate: int = 16000):
    """Convert any audio/video to 16kHz mono WAV for Whisper."""
    _ffmpeg("-i", input_path, "-ac", "1", "-ar", str(sample_rate), "-f", "wav", out_wav)


def get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        for s in json.loads(result.stdout).get("streams", []):
            if s.get("codec_type") == "audio":
                return float(s.get("duration", 0))
    return 0.0


def _denoise_noisereduce(in_wav: str, out_wav: str, log=None):
    """Non-stationary spectral noise reduction via noisereduce library.
    Preserves original sample rate and channel count. Falls back to copy."""
    if HAS_NOISEREDUCE and HAS_SOUNDFILE and HAS_NUMPY:
        try:
            data, rate = sf.read(in_wav)
            if log:
                log("Applying dynamic noise reduction (noisereduce)…")
            # Use first 0.5 s as rough noise profile; stationary=False adapts over time
            noise_clip = data[:max(1, rate // 2)] if len(data) > rate // 2 else data
            reduced = nr.reduce_noise(
                y=data, sr=rate, y_noise=noise_clip,
                stationary=False, n_jobs=-1
            )
            sf.write(out_wav, reduced.astype("float32"), rate)
            return
        except Exception as exc:
            if log:
                log(f"noisereduce error ({exc}), falling back to copy")
    shutil.copy(in_wav, out_wav)


def _denoise_deepfilternet(in_wav: str, out_wav: str, log=None):
    """AI speech enhancement via DeepFilterNet, running in its isolated venv.
    Calls the venv Python as a subprocess to avoid numpy version conflicts.
    Model (~80 MB) auto-downloads to ~/.cache/DeepFilterNet3/ on first use."""
    if not HAS_DEEPFILTERNET:
        shutil.copy(in_wav, out_wav)
        return
    _script = (
        "import sys\n"
        "in_wav, out_wav = sys.argv[1], sys.argv[2]\n"
        "from df.enhance import enhance, init_df, load_audio, save_audio\n"
        "# DeepFilterNet uses numpy internally so MPS is not supported; CPU is fast\n"
        "model, df_state, _ = init_df()\n"
        "print(f'DeepFilterNet3 running on CPU (48 kHz, model sr={df_state.sr()})')\n"
        "audio, _ = load_audio(in_wav, sr=df_state.sr())\n"
        "enhanced = enhance(model, df_state, audio)\n"
        "save_audio(out_wav, enhanced, df_state.sr())\n"
        "print('DeepFilterNet enhancement complete.')\n"
    )
    try:
        if log:
            log("Starting DeepFilterNet3 (loading model…)")
        proc = subprocess.run(
            [str(_DF_VENV_PYTHON), "-c", _script, in_wav, out_wav],
            capture_output=True, text=True, timeout=600,
        )
        # Forward subprocess stdout lines to the job log
        if log:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    log(f"  [DF] {line}")
        if proc.returncode != 0:
            err = (proc.stderr.strip() or proc.stdout.strip() or
                   f"exit {proc.returncode}")
            raise RuntimeError(err)
    except Exception as exc:
        if log:
            log(f"DeepFilterNet error: {exc} — falling back to copy")
        shutil.copy(in_wav, out_wav)


def process_audio(input_path: str, output_audio: str,
                  fmt: str = "mp3",
                  normalize: bool = True, noise_mode: str = "none",
                  target_lufs: float = -16.0,
                  log=None) -> str:
    """
    Full audio improvement pipeline — runs at original quality, then exports.
    Returns path to 16kHz mono WAV for Whisper transcription.

    noise_mode values:
      "none"          — no noise reduction
      "afftdn"        — ffmpeg FFT noise filter (fast, always available)
      "noisereduce"   — Python non-stationary spectral subtraction (requires noisereduce)
      "deepfilternet" — AI speech enhancement via DeepFilterNet (~80 MB model)

    Processing chain (Auphonic-equivalent):
      1. Noise reduction (optional)
      2. High-pass filter at 80 Hz  — removes mic rumble / HVAC noise
      3. Adaptive leveling          — multiband-style compressor evens speech
      4. EBU R128 loudness norm     — broadcast-standard target level
    """
    tmp = tempfile.mkdtemp(prefix="cp_")

    def info(msg):
        if log:
            log(msg)

    src = input_path

    # ── Python-based pre-processing noise reduction (noisereduce / deepfilternet) ─
    # These operate on a WAV file before the ffmpeg filter chain.
    if noise_mode in ("noisereduce", "deepfilternet"):
        pre_wav = os.path.join(tmp, "pre_denoise.wav")
        if noise_mode == "noisereduce":
            # 22050 Hz mono — 4× fewer FFT samples, sufficient for voice NR
            _ffmpeg("-i", src, "-c:a", "pcm_s16le", "-ar", "22050", "-ac", "1", pre_wav)
        else:
            # DeepFilterNet's native sample rate is 48 kHz — best quality input
            _ffmpeg("-i", src, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", pre_wav)
        denoised_wav = os.path.join(tmp, "denoised.wav")
        if noise_mode == "noisereduce":
            _denoise_noisereduce(pre_wav, denoised_wav, log=log)
        else:
            _denoise_deepfilternet(pre_wav, denoised_wav, log=log)
        src = denoised_wav

    # ── Build filter chain ───────────────────────────────────────────────────
    #
    #  highpass    80 Hz low-cut — removes mic rumble / HVAC
    #  afftdn      FFT-based noise reduction (inline, fast, always available)
    #              nf=-25 targets a -25 dB noise floor
    #  acompressor gentle speech leveling — 2:1, slow attack/release keeps
    #              transients intact and avoids audible pumping
    #  alimiter    true-peak safety ceiling at -1 dBTP before encode

    filters = ["highpass=f=80"]
    if noise_mode == "afftdn":
        info("Noise reduction enabled (afftdn)…")
        filters.append("afftdn=nf=-25")
    # noisereduce / deepfilternet already applied above as pre-processing
    filters += [
        "acompressor=threshold=-18dB:ratio=2:attack=20:release=200:makeup=1dB:knee=6dB",
        "alimiter=limit=0.891:attack=5:release=50:level=false",
    ]
    pre_filters = ",".join(filters)

    # ── Two-pass EBU R128 loudness normalization ─────────────────────────────
    # Pass 1 measures actual integrated loudness of the whole file.
    # Pass 2 applies a single linear gain — no dynamic pumping artifacts.
    loudnorm_filter = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"  # single-pass fallback

    if normalize:
        import re as _re
        info("Measuring loudness (pass 1/2)…")
        meas = subprocess.run(
            [_FFMPEG_BIN, "-y", "-i", src,
             "-af", f"{pre_filters},loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "-"],
            capture_output=True,
        )
        stderr = meas.stderr.decode("utf-8", errors="replace")
        m = _re.search(r'\{\s*"input_i".*?\}', stderr, _re.DOTALL)
        if m:
            try:
                stats = json.loads(m.group())
                loudnorm_filter = (
                    f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
                    f":measured_I={stats['input_i']}"
                    f":measured_TP={stats['input_tp']}"
                    f":measured_LRA={stats['input_lra']}"
                    f":measured_thresh={stats['input_thresh']}"
                    f":linear=true:offset=0"
                )
                info(f"Applying loudness correction (pass 2/2, {float(stats['input_i']):.1f} → {target_lufs} LUFS)…")
            except Exception:
                info("Loudness measurement parse failed — using single-pass.")
        else:
            info("Applying audio improvements (single-pass fallback)…")

    filter_str = f"{pre_filters},{loudnorm_filter}" if normalize else pre_filters

    # ── Export improved audio at original quality ────────────────────────────
    if fmt == "mp4":
        _ffmpeg("-i", src, "-filter:a", filter_str,
                "-codec:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", output_audio)
    else:
        _ffmpeg("-i", src, "-filter:a", filter_str,
                "-codec:a", "libmp3lame", "-q:a", "2", output_audio)

    # ── Derive 16 kHz mono WAV for Whisper ───────────────────────────────────
    info("Preparing audio for transcription…")
    whisper_wav = os.path.join(tmp, "whisper.wav")
    _ffmpeg("-i", output_audio, "-ac", "1", "-ar", "16000", "-f", "wav", whisper_wav)

    return whisper_wav


# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe(wav_path: str, model_size: str = "small",
               language: str | None = None, task: str = "transcribe",
               log=None) -> tuple[list, str]:
    """
    Returns (segments, detected_language).
    Each segment: {start, end, text, words:[{word,start,end,probability}],
                   avg_logprob, no_speech_prob}
    """
    def info(msg):
        if log:
            log(msg)

    if not HAS_FASTER_WHISPER and not HAS_OPENAI_WHISPER:
        raise RuntimeError(
            "No transcription backend found.\n"
            "Install faster-whisper:  pip install faster-whisper\n"
            "  or  openai-whisper:    pip install openai-whisper"
        )

    if HAS_FASTER_WHISPER:
        info(f"Loading Whisper model '{model_size}' (faster-whisper)…")
        model = WhisperModel(model_size, device="auto", compute_type="auto")
        info("Transcribing…")
        gen, info_obj = model.transcribe(
            wav_path,
            language=language,
            task=task,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
        detected = info_obj.language
        segs = []
        for seg in gen:
            words = []
            for w in (seg.words or []):
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 4),
                })
            segs.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "words": words,
                "avg_logprob": round(seg.avg_logprob, 4),
                "no_speech_prob": round(seg.no_speech_prob, 4),
            })
        return segs, detected

    # Fallback: openai-whisper
    info(f"Loading Whisper model '{model_size}' (openai-whisper)…")
    model = openai_whisper.load_model(model_size)
    info("Transcribing…")
    result = model.transcribe(wav_path, language=language, task=task, word_timestamps=True)
    detected = result.get("language", "en")
    segs = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "probability": round(w.get("probability", 1.0), 4),
            })
        segs.append({
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"].strip(),
            "words": words,
            "avg_logprob": round(seg.get("avg_logprob", 0), 4),
            "no_speech_prob": round(seg.get("no_speech_prob", 0), 4),
        })
    return segs, detected


def diarize(wav_path: str, hf_token: str, num_speakers: int | None = None,
            log=None) -> dict:
    """Returns {speaker_id: [(start, end), ...]}. Requires pyannote.audio."""
    if not HAS_PYANNOTE:
        raise RuntimeError("pyannote.audio not installed: pip install pyannote.audio")
    import torch as _torch
    if _torch.backends.mps.is_available():
        device = _torch.device("mps")
    elif _torch.cuda.is_available():
        device = _torch.device("cuda")
    else:
        device = _torch.device("cpu")
    if log:
        log(f"Running speaker diarization on {device}…")
    pipeline = PyannotePipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", token=hf_token
    )
    pipeline.to(device)
    params = {"num_speakers": num_speakers} if num_speakers else {}
    result = pipeline(wav_path, **params)
    # pyannote v4 wraps the Annotation in a DiarizeOutput dataclass
    annotation = getattr(result, "speaker_diarization", result)
    out: dict[str, list] = {}
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        out.setdefault(speaker, []).append((turn.start, turn.end))
    return out


def assign_speakers(segments: list, diarization: dict) -> list:
    if not diarization:
        return segments
    # Map raw pyannote IDs (SPEAKER_00, SPEAKER_01…) to friendly names (Speaker 1, Speaker 2…)
    sorted_ids = sorted(diarization.keys())
    label_map  = {raw: f"Speaker {i+1}" for i, raw in enumerate(sorted_ids)}
    intervals = sorted(
        [(s, e, label_map[spk]) for spk, turns in diarization.items() for s, e in turns],
        key=lambda x: x[0]
    )
    for seg in segments:
        best, best_ov = None, 0.0
        for s, e, spk in intervals:
            if s > seg["end"]:
                break
            ov = max(0, min(e, seg["end"]) - max(s, seg["start"]))
            if ov > best_ov:
                best_ov, best = ov, spk
        seg["speaker"] = best
    return segments


# ─── Paragraph & chapter detection ───────────────────────────────────────────

def mark_paragraphs(segments: list, silence_threshold: float = 1.2) -> list:
    """Set newpara=True on segments that start after a long silence or speaker change."""
    for i, seg in enumerate(segments):
        if i == 0:
            seg["newpara"] = True
            continue
        prev = segments[i - 1]
        gap = seg["start"] - prev["end"]
        spk_change = seg.get("speaker") != prev.get("speaker")
        seg["newpara"] = bool(gap >= silence_threshold or spk_change)
    return segments


def detect_chapters(segments: list, duration: float,
                    min_gap: float = 2.5,
                    min_chapter_secs: float = 90.0) -> list:
    """
    Returns [[start_seconds, "Title"], ...] matching Auphonic's format.
    Boundaries are long silences; titles come from the first sentence.
    """
    if not segments:
        return []

    chapters: list[list] = []
    chapter_start = segments[0]["start"]
    chapter_segs: list[dict] = [segments[0]]

    def commit(end_seg_idx: int):
        title = _chapter_title(chapter_segs)
        chapters.append([chapter_start, title])

    for i in range(1, len(segments)):
        prev, curr = segments[i - 1], segments[i]
        gap = curr["start"] - prev["end"]
        elapsed = prev["end"] - chapter_start
        if gap >= min_gap and elapsed >= min_chapter_secs:
            commit(i - 1)
            chapter_start = curr["start"]
            chapter_segs = []
        chapter_segs.append(curr)

    # Final chapter
    if chapter_segs:
        chapters.append([chapter_start, _chapter_title(chapter_segs)])

    return chapters


def _chapter_title_fallback(segs: list, max_words: int = 7) -> str:
    """Fallback: first N words of the first sentence."""
    if not segs:
        return "Chapter"
    text = segs[0].get("text", "").strip()
    sentence = re.split(r"[.!?]", text)[0].strip()
    words = sentence.split()[:max_words]
    title = " ".join(words)
    return (title + "…") if len(sentence.split()) > max_words else (title or "Chapter")


# ─── Ollama integration (local LLM for chapter titles) ───────────────────────

def ollama_available(host: str = "http://localhost:11434") -> str | None:
    """
    Returns the name of a suitable chat model if Ollama is running, else None.
    Prefers smaller/faster models for this summarisation task.
    """
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        if not models:
            return None
        # Prefer smaller models for speed; fall back to whatever is available
        preference = [
            "llama3.2", "llama3.2:3b", "llama3.1", "llama3.1:8b",
            "mistral", "mistral:7b", "gemma2", "gemma2:2b",
            "phi3", "phi3.5", "qwen2.5", "qwen2.5:3b",
        ]
        for pref in preference:
            for m in models:
                if m.startswith(pref):
                    return m
        return models[0]  # take whatever is available
    except Exception:
        return None


def ollama_generate(prompt: str, model: str,
                    host: str = "http://localhost:11434",
                    num_predict: int = 20,
                    timeout: int = 120) -> str:
    """Send a single-turn prompt to Ollama and return the response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    return result.get("response", "").strip()


def generate_shownotes(segments: list, title: str,
                       model: str, host: str, log=None) -> dict:
    """
    Generate long summary, brief summary, and tags using Ollama.
    Returns {"long": str, "brief": str, "tags": [str, ...]} or empty dict on failure.
    """
    def info(m):
        if log: log(m)

    # Build plain-text transcript (cap at ~3000 words to fit context)
    words = []
    for seg in segments:
        words.append(seg.get("text", "").strip())
    transcript = " ".join(words)
    # Truncate to ~12000 chars (~3000 words)
    if len(transcript) > 12000:
        transcript = transcript[:12000] + "…"

    try:
        info("Generating long summary…")
        long_prompt = (
            f"You are summarizing an audio transcript titled \"{title}\".\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            "Write a detailed summary in 5-8 paragraphs. Each paragraph should cover a distinct "
            "theme or section. Write in third person, present tense. Plain text only, no headers or bullets."
        )
        long = ollama_generate(long_prompt, model, host, num_predict=700, timeout=180)

        info("Generating brief summary…")
        brief_prompt = (
            f"You are summarizing an audio transcript titled \"{title}\".\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            "Write a brief summary in 2-3 paragraphs covering the main points. "
            "Plain text only, no headers or bullets."
        )
        brief = ollama_generate(brief_prompt, model, host, num_predict=300, timeout=120)

        info("Generating tags…")
        tags_prompt = (
            f"List exactly 10 short keyword tags for this audio titled \"{title}\".\n\n"
            f"TRANSCRIPT EXCERPT:\n{transcript[:3000]}\n\n"
            "Reply with only a comma-separated list of 10 keywords. No numbering, no extra text."
        )
        tags_raw = ollama_generate(tags_prompt, model, host, num_predict=80, timeout=60)
        tags = [t.strip().strip('"').strip("'") for t in tags_raw.split(",") if t.strip()][:10]

        return {"long": long, "brief": brief, "tags": tags}
    except Exception as e:
        info(f"Shownotes generation failed: {e}")
        return {}


def generate_chapter_titles_ollama(chapters_segs: list[tuple],
                                   model: str,
                                   host: str = "http://localhost:11434",
                                   log=None) -> list[str]:
    """
    chapters_segs: list of (start_sec, [segment_dicts])
    Returns list of title strings in the same order.
    Calls Ollama once per chapter — batching is avoided to keep prompts small.
    """
    titles = []
    for idx, (start, segs) in enumerate(chapters_segs):
        # Build a ~300 word excerpt from the chapter
        words, excerpt = 0, []
        for seg in segs:
            excerpt.append(seg["text"])
            words += len(seg["text"].split())
            if words >= 300:
                break
        text = " ".join(excerpt)

        prompt = (
            "You are creating chapter markers for a podcast or video transcript.\n"
            "Write a SHORT chapter title (3 to 6 words, title case, no punctuation) "
            "that captures the main topic of this excerpt.\n\n"
            f"Excerpt:\n{text}\n\n"
            "Chapter title:"
        )
        try:
            raw = ollama_generate(prompt, model, host)
            # Strip quotes, leading/trailing whitespace, trailing punctuation
            title = raw.strip().strip('"\'').rstrip(".,:;!?")
            # If the model returned multiple lines, take the first
            title = title.splitlines()[0].strip()
            if log:
                log(f"  Chapter {idx + 1}: {title}")
            titles.append(title or _chapter_title_fallback(segs))
        except Exception as exc:
            if log:
                log(f"  Ollama error on chapter {idx + 1}: {exc}")
            titles.append(_chapter_title_fallback(segs))
    return titles


def detect_chapters_with_titles(segments: list, duration: float,
                                 min_gap: float = 2.5,
                                 min_chapter_secs: float = 90.0,
                                 ollama_host: str = "http://localhost:11434",
                                 log=None) -> list:
    """
    Detect chapter boundaries then title them.
    Uses Ollama (local LLM) if available, otherwise falls back to first-words heuristic.
    Returns [[start_seconds, "Title"], ...]
    """
    if not segments:
        return []

    # ── Find boundaries ──────────────────────────────────────────────────────
    boundary_starts = [segments[0]["start"]]
    current_start = segments[0]["start"]

    for i in range(1, len(segments)):
        prev, curr = segments[i - 1], segments[i]
        gap = curr["start"] - prev["end"]
        elapsed = prev["end"] - current_start
        if gap >= min_gap and elapsed >= min_chapter_secs:
            boundary_starts.append(curr["start"])
            current_start = curr["start"]

    # ── Group segments per chapter ────────────────────────────────────────────
    chapters_segs: list[tuple] = []
    for ci, start in enumerate(boundary_starts):
        end = boundary_starts[ci + 1] if ci + 1 < len(boundary_starts) else float("inf")
        ch_segs = [s for s in segments if start <= s["start"] < end]
        chapters_segs.append((start, ch_segs))

    # ── Title generation ──────────────────────────────────────────────────────
    model = ollama_available(ollama_host)
    if model:
        if log:
            log(f"Generating chapter titles with Ollama ({model})…")
        titles = generate_chapter_titles_ollama(chapters_segs, model, ollama_host, log)
    else:
        if log:
            log("Ollama not available — using first-words chapter titles.")
        titles = [_chapter_title_fallback(segs) for _, segs in chapters_segs]

    return [[start, title] for (start, _), title in zip(chapters_segs, titles)]


# ─── Output format generators ─────────────────────────────────────────────────

def to_auphonic_json(segments: list) -> list:
    """Produce Auphonic-compatible JSON: list of segment dicts."""
    out = []
    for seg in segments:
        conf = max(0.0, min(1.0, 1.0 + seg.get("avg_logprob", 0.0)))
        item: dict = {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "confidence": round(conf, 4),
            "newpara": seg.get("newpara", False),
            "timestamps": [
                [w["word"], w["start"], w["end"], w["probability"]]
                for w in seg.get("words", [])
            ],
        }
        if seg.get("speaker"):
            item["speaker"] = seg["speaker"]
        out.append(item)
    return out


def to_vtt(segments: list) -> str:
    """WebVTT suitable for YouTube upload — cue IDs, max 42 chars/line."""
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        text = _wrap_vtt(seg["text"], width=42)
        lines += [
            str(i),
            f"{_vtt_ts(seg['start'])} --> {_vtt_ts(seg['end'])}",
            text,
            "",
        ]
    return "\n".join(lines)


def _wrap_vtt(text: str, width: int = 42) -> str:
    """Split long lines for YouTube's caption renderer (max 2 lines)."""
    words = text.split()
    if not words:
        return text
    lines, cur = [], []
    cur_len = 0
    for w in words:
        if cur_len + len(w) + (1 if cur else 0) > width and cur:
            lines.append(" ".join(cur))
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += len(w) + (1 if cur_len else 0)
    if cur:
        lines.append(" ".join(cur))
    # YouTube shows max 2 lines; merge any extras into line 2
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


def to_srt(segments: list) -> str:
    parts = []
    for i, seg in enumerate(segments, 1):
        parts.append(f"{i}\n{_srt_ts(seg['start'])} --> {_srt_ts(seg['end'])}\n{seg['text']}\n")
    return "\n".join(parts)


def to_txt(segments: list) -> str:
    lines, last_spk = [], None
    for seg in segments:
        spk = seg.get("speaker")
        if spk and spk != last_spk:
            lines.append(f"\n[{spk}]")
            last_spk = spk
        if seg.get("newpara") and lines:
            lines.append("")
        lines.append(seg["text"])
    return "\n".join(lines).strip()


def _vtt_ts(s: float) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"


def _srt_ts(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


# ─── HTML output template (transcript editor) ─────────────────────────────────

_TRANSCRIPT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f0f1a;--surface:#18182a;--surface2:#22223a;--border:#30304a;
  --accent:#7c6af7;--accent2:#a593ff;--text:#ddddf0;--muted:#7878a0;
  --word-hover:rgba(255,255,255,.07);--playing:#f5c518;--low-conf:#e05c5c;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif
}
[data-theme="light"]{
  --bg:#f2f2f7;--surface:#ffffff;--surface2:#e8e8f0;--border:#d0d0e0;
  --text:#1a1a2e;--muted:#6060a0;--word-hover:rgba(0,0,0,.06)
}
@media(prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#f2f2f7;--surface:#ffffff;--surface2:#e8e8f0;--border:#d0d0e0;
    --text:#1a1a2e;--muted:#6060a0;--word-hover:rgba(0,0,0,.06)
  }
}
body{font-family:var(--font);background:var(--bg);color:var(--text);
  height:100vh;display:flex;flex-direction:column;overflow:hidden;font-size:15px}
/* Header */
.hdr{display:flex;align-items:center;gap:.75rem;padding:.6rem 1.25rem;
  background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0;min-height:52px}
.logo{font-weight:800;font-size:1rem;color:var(--accent);letter-spacing:-.01em;white-space:nowrap}
.hdr h1{flex:1;font-size:.9rem;font-weight:500;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xbtns{display:flex;gap:.35rem}
.xbtn{padding:.25rem .6rem;border-radius:5px;border:1px solid var(--border);
  background:var(--surface2);color:var(--text);cursor:pointer;font-size:.75rem;
  font-family:var(--font);transition:border-color .15s,background .15s}
.xbtn:hover{border-color:var(--accent);background:rgba(124,106,247,.15)}
/* Layout */
.layout{display:flex;flex:1;overflow:hidden}
/* Sidebar */
.sidebar{width:230px;background:var(--surface);border-right:1px solid var(--border);
  overflow-y:auto;flex-shrink:0}
.sidebar-hdr{padding:.75rem 1rem .4rem;font-size:.65rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.ch-item{padding:.55rem 1rem;cursor:pointer;border-left:3px solid transparent;
  transition:all .15s;font-size:.82rem;line-height:1.3}
.ch-item:hover{background:var(--surface2)}
.ch-item.active{border-left-color:var(--accent);background:var(--surface2);color:var(--accent2)}
.ch-time{font-size:.68rem;color:var(--muted);margin-top:.15rem}
/* Transcript */
.tx-area{flex:1;overflow-y:auto;padding:1.75rem 2rem}
.meta{font-size:.75rem;color:var(--muted);display:flex;gap:1.25rem;margin-bottom:1.5rem;flex-wrap:wrap}
.ch-section{margin-bottom:2.5rem}
.ch-label{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
  color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:.35rem;margin-bottom:.75rem}
p.para{margin-bottom:.5rem;line-height:1.85}
.w{cursor:pointer;border-radius:2px;padding:0 1px;transition:background .1s}
.w:hover{background:var(--word-hover)}
.w.now{background:var(--playing);color:#111;border-radius:3px}
.w.lc{color:var(--low-conf)}
.spk{display:inline-block;font-size:.65rem;font-weight:700;color:var(--accent2);
  background:rgba(124,106,247,.18);border-radius:3px;padding:0 .35rem;
  margin-right:.3rem;text-transform:uppercase;letter-spacing:.04em}
/* Player */
.player{background:var(--surface);border-top:1px solid var(--border);
  padding:.65rem 1.25rem;flex-shrink:0;display:flex;align-items:center;gap:.75rem}
.play-btn{width:34px;height:34px;border-radius:50%;background:var(--accent);border:none;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  color:#fff;flex-shrink:0;transition:background .15s}
.play-btn:hover{background:var(--accent2)}
.spd{font-size:.72rem;padding:.18rem .45rem;background:var(--surface2);
  border:1px solid var(--border);border-radius:4px;color:var(--text);
  cursor:pointer;font-family:var(--font);transition:border-color .15s;white-space:nowrap}
.spd:hover{border-color:var(--accent)}
.tdisp{font-size:.75rem;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap;min-width:100px}
.seek{flex:1;height:5px;background:var(--surface2);border-radius:3px;
  cursor:pointer;position:relative}
.seek-fill{height:100%;background:var(--accent);border-radius:3px;width:0%;pointer-events:none}
/* Shownotes */
.shownotes{margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:2px solid var(--border)}
.shownotes h2{font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
  color:var(--muted);margin-bottom:1.25rem}
.shownotes h3{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--accent2);margin:1.25rem 0 .5rem}
.shownotes p{line-height:1.8;color:var(--text);font-size:.9rem;margin-bottom:.65rem}
.ch-table{width:100%;border-collapse:collapse;font-size:.85rem;margin-bottom:.5rem}
.ch-table tr{border-bottom:1px solid var(--border)}
.ch-table td{padding:.35rem .5rem;vertical-align:top}
.ch-table td:first-child{color:var(--accent);font-variant-numeric:tabular-nums;
  white-space:nowrap;width:3.5rem;cursor:pointer}
.ch-table td:first-child:hover{color:var(--accent2)}
.tags{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.4rem}
.tag{background:rgba(124,106,247,.18);color:var(--accent2);border-radius:999px;
  padding:.2rem .65rem;font-size:.75rem;border:1px solid rgba(124,106,247,.3)}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--muted)}
</style>
</head>
<body>
<header class="hdr">
  <span class="logo">⟁ CastPolish</span>
  <h1 id="ttl">__TITLE__</h1>
  <div class="xbtns">
    <button class="xbtn" onclick="dl('json')">JSON</button>
    <button class="xbtn" onclick="dl('vtt')">VTT</button>
    <button class="xbtn" onclick="dl('srt')">SRT</button>
    <button class="xbtn" onclick="dl('txt')">TXT</button>
    <button class="xbtn" id="theme-btn" onclick="toggleTheme()" title="Toggle light/dark">🌙</button>
  </div>
</header>
<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-hdr">Chapters</div>
    <div id="ch-nav"></div>
  </aside>
  <main class="tx-area" id="tx">
    <div class="meta" id="meta"></div>
    <div id="content"></div>
  </main>
</div>
<div class="player">
  <button class="play-btn" id="pbtn" onclick="togglePlay()">
    <svg id="psvg" viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
      <polygon id="pico" points="5,3 19,12 5,21"/>
    </svg>
  </button>
  <span class="spd" id="spdbtn" onclick="cycleSpd()">1×</span>
  <span class="tdisp" id="tdisp">0:00 / 0:00</span>
  <div class="seek" id="seek" onclick="seekClick(event)">
    <div class="seek-fill" id="sfill"></div>
  </div>
  <audio id="aud" preload="metadata"></audio>
</div>
<script>
const D=__DATA_JSON__;
const aud=document.getElementById('aud');
aud.src=D.audio_file||'';
const SPEEDS=[.5,.75,1,1.25,1.5,2];let si=2,curW=null;
const segs=D.segments||[];
const chs=D.chapters||[];

/* ── Meta ── */
const metaEl=document.getElementById('meta');
const dParts=[];
if(D.language)dParts.push('Language: '+D.language.toUpperCase());
if(D.duration)dParts.push('Duration: '+fmtDur(D.duration));
const wc=segs.reduce((n,s)=>n+(s.timestamps?.length||0),0);
if(wc)dParts.push(wc.toLocaleString()+' words');
metaEl.innerHTML=dParts.map(p=>`<span>${p}</span>`).join('');

/* ── Shownotes (chapters table + summaries + tags) ── */
const sn=D.shownotes||{};
const snEl=document.createElement('div');
snEl.className='shownotes';
let snHTML='<h2>Shownotes</h2>';
// Chapters table
if(chs.length){
  snHTML+='<h3>Chapters</h3><table class="ch-table"><tbody>';
  chs.forEach(([s,t])=>{
    snHTML+=`<tr><td onclick="seekTo(${s})">${fmt(s)}</td><td>${esc(t)}</td></tr>`;
  });
  snHTML+='</tbody></table>';
}
// Long summary
if(sn.long){snHTML+=`<h3>Summary</h3><p>${esc(sn.long).replace(/\n\n/g,'</p><p>').replace(/\n/g,' ')}</p>`;}
// Brief summary
if(sn.brief){snHTML+=`<h3>Brief Summary</h3><p>${esc(sn.brief).replace(/\n\n/g,'</p><p>').replace(/\n/g,' ')}</p>`;}
// Tags
if(sn.tags&&sn.tags.length){
  snHTML+='<h3>Tags</h3><div class="tags">';
  sn.tags.forEach(t=>{snHTML+=`<span class="tag">${esc(t)}</span>`;});
  snHTML+='</div>';
}
if(chs.length||sn.long||sn.brief||(sn.tags&&sn.tags.length)){
  snEl.innerHTML=snHTML;
  document.getElementById('content').appendChild(snEl);
}

/* ── Build transcript ── */
const content=document.getElementById('content');
const chNav=document.getElementById('ch-nav');

if(chs.length===0){
  const sec=document.createElement('div');sec.className='ch-section';
  renderSegs(segs,sec);content.appendChild(sec);
}else{
  chs.forEach(([chStart,chTitle],ci)=>{
    const nav=document.createElement('div');
    nav.className='ch-item';nav.dataset.start=chStart;
    nav.innerHTML=`${esc(chTitle)}<div class="ch-time">${fmt(chStart)}</div>`;
    nav.onclick=()=>{aud.currentTime=chStart;aud.play()};
    chNav.appendChild(nav);
    const chEnd=ci+1<chs.length?chs[ci+1][0]:Infinity;
    const sec=document.createElement('div');sec.className='ch-section';sec.dataset.ch=ci;
    const lbl=document.createElement('div');lbl.className='ch-label';lbl.textContent=chTitle;
    sec.appendChild(lbl);
    renderSegs(segs.filter(s=>s.start>=chStart&&s.start<chEnd),sec);
    content.appendChild(sec);
  });
}

function renderSegs(ss,container){
  let para=null, lastSpk=null;
  ss.forEach(seg=>{
    if(seg.newpara||!para){
      para=document.createElement('p');para.className='para';container.appendChild(para);
      if(seg.speaker){const t=document.createElement('span');t.className='spk';t.textContent=seg.speaker;para.appendChild(t);lastSpk=seg.speaker;}
    } else if(seg.speaker && seg.speaker!==lastSpk){
      const t=document.createElement('span');t.className='spk';t.textContent=seg.speaker;para.appendChild(t);lastSpk=seg.speaker;
    }
    const words=seg.timestamps||[];
    if(!words.length){
      const sp=mkWord(seg.text+' ',seg.start,seg.end,1);para.appendChild(sp);return;
    }
    words.forEach(([word,ws,we,conf])=>{
      para.appendChild(mkWord(word+' ',ws,we,conf));
    });
  });
}

function mkWord(txt,ws,we,conf){
  const sp=document.createElement('span');
  sp.className='w'+(conf<0.6?' lc':'');
  sp.dataset.s=ws;sp.dataset.e=we;
  sp.textContent=txt;
  sp.title=`${fmt(ws)}  conf:${(conf*100).toFixed(0)}%`;
  sp.onclick=()=>{aud.currentTime=ws;if(aud.paused)aud.play()};
  return sp;
}

/* ── Playback sync ── */
const allW=()=>document.querySelectorAll('.w[data-s]');

aud.ontimeupdate=()=>{
  const t=aud.currentTime;
  if(aud.duration)document.getElementById('sfill').style.width=(t/aud.duration*100)+'%';
  document.getElementById('tdisp').textContent=fmt(t)+' / '+fmt(aud.duration||0);
  let found=null;
  for(const w of allW()){
    const ws=+w.dataset.s,we=+w.dataset.e;
    if(ws<=t&&t<we){found=w;break}
    if(ws>t+1)break;
  }
  if(found!==curW){
    if(curW)curW.classList.remove('now');
    if(found){found.classList.add('now');found.scrollIntoView({block:'nearest',behavior:'smooth'});updCh(+found.dataset.s);}
    curW=found;
  }
};

aud.onplay=()=>document.getElementById('pico').setAttribute('points','6,19 10,19 10,5 6,5 M14,5 18,5 18,19 14,19');
aud.onpause=aud.onended=()=>document.getElementById('pico').setAttribute('points','5,3 19,12 5,21');

function togglePlay(){aud.paused?aud.play():aud.pause()}
function seekClick(e){
  const r=document.getElementById('seek').getBoundingClientRect();
  if(aud.duration)aud.currentTime=((e.clientX-r.left)/r.width)*aud.duration;
}
function cycleSpd(){si=(si+1)%SPEEDS.length;aud.playbackRate=SPEEDS[si];document.getElementById('spdbtn').textContent=SPEEDS[si]+'×';}

function updCh(t){
  const items=document.querySelectorAll('.ch-item');
  let ai=0;
  chs.forEach(([s],i)=>{if(s<=t)ai=i});
  items.forEach((it,i)=>it.classList.toggle('active',i===ai));
}

/* ── Export ── */
function dl(fmt){
  let content,mime,ext;
  if(fmt==='json'){content=JSON.stringify(segs,null,2);mime='application/json';ext='json';}
  else if(fmt==='vtt'){content=toVTT();mime='text/vtt';ext='vtt';}
  else if(fmt==='srt'){content=toSRT();mime='text/plain';ext='srt';}
  else{content=toTXT();mime='text/plain';ext='txt';}
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([content],{type:mime}));
  a.download=(D.title||'transcript')+'.'+ext;a.click();
}
function toVTT(){
  let o='WEBVTT\n\n';
  segs.forEach(s=>{o+=`${vttTs(s.start)} --> ${vttTs(s.end)}\n${s.text}\n\n`;});return o;
}
function toSRT(){
  return segs.map((s,i)=>`${i+1}\n${srtTs(s.start)} --> ${srtTs(s.end)}\n${s.text}\n`).join('\n');
}
function toTXT(){
  let o='',ls=null;
  segs.forEach(s=>{
    if(s.speaker&&s.speaker!==ls){o+=(o?'\n':'')+`[${s.speaker}]\n`;ls=s.speaker;}
    if(s.newpara&&o)o+='\n';
    o+=s.text+' ';
  });return o.trim();
}

/* ── Utils ── */
function seekTo(s){aud.currentTime=s;aud.play();}
function fmt(s){
  if(!s||isNaN(s))return'0:00';
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=Math.floor(s%60);
  return h?`${h}:${p(m)}:${p(sec)}`:`${m}:${p(sec)}`;
}
function fmtDur(s){
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=Math.floor(s%60);
  if(h)return`${h}h ${m}m`;if(m)return`${m}m ${sec}s`;return`${sec}s`;
}
function vttTs(s){const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=(s%60).toFixed(3).padStart(6,'0');return`${p(h)}:${p(m)}:${sec}`;}
function srtTs(s){const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=Math.floor(s%60),ms=Math.floor((s%1)*1000);return`${p(h)}:${p(m)}:${p(sec)},${String(ms).padStart(3,'0')}`;}
function p(n){return String(n).padStart(2,'0')}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function applyTheme(t){document.documentElement.setAttribute('data-theme',t);const b=document.getElementById('theme-btn');if(b)b.textContent=t==='light'?'☀️':'🌙';}
function toggleTheme(){const cur=document.documentElement.getAttribute('data-theme')||(window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');const next=cur==='light'?'dark':'light';applyTheme(next);localStorage.setItem('cp-theme',next);}
(function(){const s=localStorage.getItem('cp-theme')||( window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');applyTheme(s);})();
</script>
</body>
</html>
"""


def build_output_html(title: str, audio_file: str, segments: list,
                      chapters: list, language: str, duration: float,
                      shownotes: dict | None = None) -> str:
    data = {
        "title": title,
        "language": language,
        "duration": round(duration, 2),
        "audio_file": audio_file,
        "chapters": chapters,
        "segments": to_auphonic_json(segments),
        "shownotes": shownotes or {},
    }
    html = _TRANSCRIPT_HTML
    html = html.replace("__TITLE__", title)
    html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, cls=_SafeEncoder))
    html = html.replace("__AUDIO_FILE__", audio_file)
    return html


# ─── Web engine UI ────────────────────────────────────────────────────────────

_ENGINE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CastPolish</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f0f1a;--surface:#18182a;--surface2:#22223a;--border:#30304a;
  --accent:#7c6af7;--accent2:#a593ff;--text:#ddddf0;--muted:#7878a0;
  --success:#4caf7d;--warn:#f5c518;--error:#e05c5c;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif
}
[data-theme="light"]{
  --bg:#f2f2f7;--surface:#ffffff;--surface2:#e8e8f0;--border:#d0d0e0;
  --text:#1a1a2e;--muted:#6060a0
}
@media(prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#f2f2f7;--surface:#ffffff;--surface2:#e8e8f0;--border:#d0d0e0;
    --text:#1a1a2e;--muted:#6060a0
  }
}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh}
nav{background:var(--surface);border-bottom:1px solid var(--border);
  padding:.75rem 2rem;display:flex;align-items:center;gap:1rem}
.logo{font-weight:800;font-size:1.1rem;color:var(--accent);text-decoration:none}
.nav-sub{font-size:.8rem;color:var(--muted)}
main{max-width:900px;margin:2rem auto;padding:0 1.5rem}
h2{font-size:1.05rem;font-weight:600;margin-bottom:1rem;color:var(--text)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}
/* Upload zone */
.drop-zone{border:2px dashed var(--border);border-radius:8px;padding:2.5rem;
  text-align:center;cursor:pointer;transition:all .2s;background:var(--surface2)}
.drop-zone:hover,.drop-zone.over{border-color:var(--accent);background:rgba(124,106,247,.08)}
.drop-zone p{color:var(--muted);font-size:.875rem;margin-top:.5rem}
.drop-zone .icon{font-size:2rem;display:block;margin-bottom:.5rem}
.file-name{font-size:.8rem;color:var(--accent2);margin-top:.5rem;font-weight:500}
/* Form */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1rem}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
label{display:block;font-size:.75rem;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:.35rem}
select,input[type=text],input[type=number]{width:100%;padding:.45rem .65rem;
  border-radius:6px;border:1px solid var(--border);background:var(--surface2);
  color:var(--text);font-size:.85rem;font-family:var(--font);outline:none;transition:border-color .15s}
select:focus,input:focus{border-color:var(--accent)}
.toggle-row{display:flex;align-items:center;gap:.6rem;padding:.4rem 0}
.toggle-row span{font-size:.85rem}
input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}
.hint{font-size:.72rem;color:var(--muted);margin-top:.2rem}
/* Submit */
.submit-btn{margin-top:1.25rem;width:100%;padding:.7rem;border-radius:8px;
  background:var(--accent);border:none;color:#fff;font-size:.9rem;font-weight:600;
  cursor:pointer;font-family:var(--font);transition:background .15s}
.submit-btn:hover{background:var(--accent2)}
.submit-btn:disabled{opacity:.5;cursor:default}
/* Jobs */
.jobs-table{width:100%;border-collapse:collapse;font-size:.83rem}
.jobs-table th{text-align:left;padding:.5rem .75rem;border-bottom:1px solid var(--border);
  font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600}
.jobs-table td{padding:.6rem .75rem;border-bottom:1px solid var(--border)}
.jobs-table tr:last-child td{border-bottom:none}
.status-badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.7rem;font-weight:600}
.s-queued{background:rgba(120,120,160,.2);color:var(--muted)}
.s-processing{background:rgba(124,106,247,.2);color:var(--accent2);animation:pulse 1.5s infinite}
.s-done{background:rgba(76,175,125,.2);color:var(--success)}
.s-error{background:rgba(224,92,92,.2);color:var(--error)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
.job-link{color:var(--accent2);text-decoration:none;font-weight:500}
.job-link:hover{text-decoration:underline}
.progress-log{font-size:.72rem;color:var(--muted);margin-top:.3rem;font-style:italic}
.empty-jobs{text-align:center;color:var(--muted);padding:2rem;font-size:.875rem}
a{color:var(--accent2)}
.feat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.75rem;margin-top:.75rem}
.feat{background:var(--surface2);border-radius:6px;padding:.75rem;font-size:.78rem}
.feat strong{display:block;margin-bottom:.25rem;color:var(--text)}
.feat span{color:var(--muted)}
.mini-btn{font-size:.68rem;padding:.12rem .45rem;border-radius:4px;border:1px solid var(--border);
  background:var(--surface);color:var(--accent);cursor:pointer;margin-left:.35rem;
  transition:background .15s,color .15s;vertical-align:middle}
.mini-btn:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.mini-btn.install-btn{color:var(--warn);border-color:var(--warn)}
.mini-btn.install-btn:hover{background:var(--warn);color:#111}
.install-panel{background:var(--surface2);border:1px solid var(--border);border-radius:8px;
  padding:.9rem 1rem;margin-top:.85rem}
.install-panel .panel-head{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:.6rem;font-size:.82rem;font-weight:600}
#install-log{font-size:.72rem;max-height:220px;overflow-y:auto;white-space:pre-wrap;
  word-break:break-all;background:var(--bg);border:1px solid var(--border);border-radius:5px;
  padding:.5rem .6rem;line-height:1.5}
</style>
</head>
<body>
<nav>
  <a class="logo" href="/">⟁ CastPolish</a>
  <span class="nav-sub">Open-source audio processing &amp; transcription</span>
  <button id="theme-btn" onclick="toggleTheme()" title="Toggle light/dark mode"
    style="margin-left:auto;background:none;border:1px solid var(--border);border-radius:6px;
           padding:.25rem .5rem;cursor:pointer;font-size:1rem;color:var(--text);line-height:1">🌙</button>
</nav>
<main>

<div class="card">
  <h2>Process Audio</h2>
  <div class="drop-zone" id="dropzone" onclick="document.getElementById('fileinput').click()"
       ondragover="ev(event,'over')" ondragleave="ev(event,'leave')" ondrop="ev(event,'drop')">
    <span class="icon">🎵</span>
    <strong>Click to select or drag &amp; drop audio</strong>
    <p>MP3, WAV, M4A, FLAC, OGG, MP4, MOV, MKV…</p>
    <div class="file-name" id="fname"></div>
  </div>
  <input type="file" id="fileinput" accept="audio/*,video/*" style="display:none" onchange="fileChosen(this)">

  <div class="grid">
    <div>
      <label>Whisper Model</label>
      <select id="model">
        <option value="tiny">tiny — fastest, lowest accuracy</option>
        <option value="base">base</option>
        <option value="small" selected>small — good balance ✓</option>
        <option value="medium">medium</option>
        <option value="large-v2">large-v2</option>
        <option value="large-v3">large-v3 — best accuracy</option>
      </select>
      <div class="hint">First run downloads the model weights.</div>
    </div>
    <div>
      <label>Language</label>
      <input type="text" id="language" placeholder="auto-detect (leave blank)" maxlength="10">
      <div class="hint">ISO code, e.g. <code>en</code>, <code>de</code>, <code>es</code></div>
    </div>
    <div>
      <label>Task</label>
      <select id="task">
        <option value="transcribe">Transcribe (keep original language)</option>
        <option value="translate">Translate to English</option>
      </select>
    </div>
    <div>
      <label>Loudness target</label>
      <input type="number" id="lufs" value="-16" min="-30" max="-5" step="1">
      <div class="hint">LUFS (EBU R128). Auphonic default: −16</div>
    </div>
    <div>
      <label>Output format</label>
      <select id="outfmt">
        <option value="mp3">MP3 (recommended)</option>
        <option value="mp4">MP4 / AAC</option>
      </select>
      <div class="hint">Audio file format. VTT, JSON &amp; HTML are always produced.</div>
    </div>
  </div>

  <div style="margin-top:1rem">
    <div class="toggle-row" style="padding-bottom:.5rem;margin-bottom:.5rem;border-bottom:1px solid var(--border)">
      <input type="checkbox" id="transcribe_only" onchange="updateTranscribeOnly()">
      <span><strong>Transcribe &amp; summarize only</strong> <span style="color:var(--muted);font-size:.75rem">(skip audio processing — faster)</span></span>
    </div>
    <div id="audio-opts" style="transition:opacity .2s">
      <div class="toggle-row">
        <input type="checkbox" id="normalize" checked>
        <span>Loudness normalisation + adaptive leveling</span>
      </div>
      <div style="display:flex;align-items:center;gap:.6rem;padding:.3rem 0">
        <label for="noise_mode" style="font-size:.85rem;color:var(--text);white-space:nowrap">Noise reduction</label>
        <select id="noise_mode" style="flex:1;padding:.3rem .5rem;border-radius:6px;
          border:1px solid var(--border);background:var(--surface2);color:var(--text);
          font-size:.82rem;font-family:var(--font)">
          <option value="none">None</option>
          <option value="afftdn">Standard (ffmpeg afftdn)</option>
        </select>
      </div>
    </div>
    <div class="toggle-row">
      <input type="checkbox" id="diarize">
      <span>Speaker diarization <span style="color:var(--muted);font-size:.75rem">(requires pyannote.audio + HF_TOKEN)</span></span>
    </div>
  </div>

  <button class="submit-btn" id="submitbtn" onclick="submitJob()" disabled>Submit</button>
</div>

<div class="card">
  <h2>Recent Jobs</h2>
  <div id="jobs-container"><div class="empty-jobs">No jobs yet.</div></div>
</div>

<div class="card">
  <h2>Settings</h2>

  <div style="margin-bottom:1.25rem">
    <label>Output Folder</label>
    <div style="display:flex;gap:.5rem;margin-top:.35rem">
      <input type="text" id="output_dir" placeholder="~/CastPolish-output" style="flex:1;font-family:monospace;font-size:.82rem">
    </div>
    <div class="hint" id="output_dir_status">Where processed files (MP3, VTT, JSON, HTML) are saved. Changes take effect immediately for new jobs.</div>
  </div>

  <div style="margin-bottom:1.25rem">
    <label>Ollama (local LLM for chapter titles)</label>
    <div style="display:flex;gap:.5rem;margin-top:.35rem">
      <input type="text" id="ollama_host" placeholder="http://localhost:11434" style="flex:1">
      <button class="xbtn" onclick="testOllama()" style="white-space:nowrap">Test</button>
    </div>
    <div class="hint" id="ollama_status" style="margin-top:.4rem">
      Ollama generates proper chapter titles (like Auphonic's AI chapters).
      Install from <a href="https://ollama.com" target="_blank">ollama.com</a> then run
      <code>ollama pull llama3.2</code>.
    </div>
  </div>

  <div style="margin-bottom:1.25rem">
    <label>HuggingFace Token <span style="font-weight:400;text-transform:none;color:var(--muted)">(only needed for speaker diarization)</span></label>
    <div style="display:flex;gap:.5rem;margin-top:.35rem">
      <input type="password" id="hf_token" placeholder="hf_…" style="flex:1">
      <button class="xbtn" onclick="window.open('https://huggingface.co/settings/tokens','_blank')" style="white-space:nowrap">Get token ↗</button>
    </div>
    <div class="hint" id="hf_status">
      Free account required. Also accept the license at
      <a href="https://huggingface.co/pyannote/speaker-diarization-3.1" target="_blank">pyannote/speaker-diarization-3.1</a>.
    </div>
  </div>

  <button class="submit-btn" style="width:auto;padding:.5rem 1.5rem" onclick="saveSettings()">Save Settings</button>
</div>

<div class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.75rem">
    <h2 style="margin:0">Dependencies</h2>
    <button class="mini-btn" style="font-size:.72rem;padding:.2rem .6rem"
            onclick="checkUpdates(this)">Check for updates</button>
  </div>
  <div class="feat-grid" id="deps"></div>
  <div id="install-panel" style="display:none" class="install-panel">
    <div class="panel-head">
      <span>📦 Install / Update</span>
      <button class="mini-btn" onclick="document.getElementById('install-panel').style.display='none'">✕ Close</button>
    </div>
    <pre id="install-log"></pre>
  </div>
</div>

</main>
<script>
let selectedFile=null;

function ev(e,action){
  e.preventDefault();e.stopPropagation();
  const dz=document.getElementById('dropzone');
  if(action==='over')dz.classList.add('over');
  else if(action==='leave')dz.classList.remove('over');
  else if(action==='drop'){
    dz.classList.remove('over');
    const f=e.dataTransfer.files[0];
    if(f)setFile(f);
  }
}

function fileChosen(input){if(input.files[0])setFile(input.files[0]);}
function setFile(f){
  selectedFile=f;
  document.getElementById('fname').textContent=f.name+' ('+fmtSize(f.size)+')';
  document.getElementById('submitbtn').disabled=false;
}
function fmtSize(b){
  if(b>1e6)return(b/1e6).toFixed(1)+' MB';
  if(b>1e3)return(b/1e3).toFixed(0)+' KB';
  return b+' B';
}

async function submitJob(){
  if(!selectedFile)return;
  const btn=document.getElementById('submitbtn');
  btn.disabled=true;btn.textContent='Uploading…';
  const fd=new FormData();
  fd.append('file',selectedFile);
  fd.append('model',document.getElementById('model').value);
  fd.append('language',document.getElementById('language').value);
  fd.append('task',document.getElementById('task').value);
  fd.append('lufs',document.getElementById('lufs').value);
  fd.append('outfmt',document.getElementById('outfmt').value);
  fd.append('transcribe_only',document.getElementById('transcribe_only').checked?'1':'0');
  fd.append('normalize',document.getElementById('normalize').checked?'1':'0');
  fd.append('noise_mode',document.getElementById('noise_mode').value);
  fd.append('diarize',document.getElementById('diarize').checked?'1':'0');
  try{
    const r=await fetch('/api/process',{method:'POST',body:fd});
    const d=await r.json();
    if(d.error){alert('Error: '+d.error);}
    else{selectedFile=null;document.getElementById('fname').textContent='';btn.textContent='Submit';}
  }catch(e){alert('Upload failed: '+e);}
  btn.disabled=false;btn.textContent='Submit';
  pollJobs();
}

async function pollJobs(){
  try{
    const r=await fetch('/api/jobs');
    const jobs=await r.json();
    renderJobs(jobs);
    const running=jobs.some(j=>j.status==='processing'||j.status==='queued');
    if(running)setTimeout(pollJobs,2000);
  }catch(e){}
}

function fmtDuration(secs){
  if(!secs||secs<1)return'—';
  const m=Math.floor(secs/60),s=Math.round(secs%60);
  return m>0?`${m}m ${s}s`:`${s}s`;
}

function renderJobs(jobs){
  const el=document.getElementById('jobs-container');
  if(!jobs.length){el.innerHTML='<div class="empty-jobs">No jobs yet.</div>';return;}
  let html='<table class="jobs-table"><thead><tr><th>Title</th><th>Status</th><th>Model</th><th>Started</th><th>Duration</th><th>Results</th></tr></thead><tbody>';
  jobs.forEach(j=>{
    const sc={'queued':'s-queued','processing':'s-processing','done':'s-done','error':'s-error'}[j.status]||'s-queued';
    const ts=j.started?new Date(j.started*1000).toLocaleTimeString():(j.created?new Date(j.created*1000).toLocaleTimeString():'—');
    const dur=j.finished&&j.started?fmtDuration(j.finished-j.started):(j.status==='processing'?'running…':'—');
    const links=j.status==='done'
      ?`<a class="job-link" href="/results/${j.id}" target="_blank">View</a>`
      +` <a class="job-link" href="/download/${j.id}/audio">Audio</a>`
      +` <a class="job-link" href="/download/${j.id}/html">HTML</a>`
      +` <a class="job-link" href="/download/${j.id}/json">JSON</a>`
      +` <a class="job-link" href="/download/${j.id}/vtt">VTT</a>`
      :'—';
    html+=`<tr>
      <td>${esc(j.title||j.id.slice(0,8))}</td>
      <td><span class="status-badge ${sc}">${j.status}</span>
        ${j.log&&j.log.length?`<div class="progress-log">${esc(j.log[j.log.length-1])}</div>`:''}
      </td>
      <td>${j.model||'—'}</td><td>${ts}</td><td>${dur}</td><td>${links}</td>
    </tr>`;
  });
  html+='</tbody></table>';
  el.innerHTML=html;
}

let _depsCache={};

async function loadDeps(){
  const r=await fetch('/api/deps');
  const deps=await r.json();
  _depsCache=deps;

  // ── Populate noise mode dropdown ──────────────────────────────────────────
  const sel=document.getElementById('noise_mode');
  if(deps.noise_modes&&deps.noise_modes.length){
    sel.innerHTML='';
    deps.noise_modes.forEach(m=>{
      const opt=document.createElement('option');
      opt.value=m.value; opt.textContent=m.label;
      sel.appendChild(opt);
    });
  }

  renderDeps(deps,{});
}

function renderDeps(deps,updates){
  const el=document.getElementById('deps');
  el.innerHTML=Object.entries(deps)
    .filter(([k])=>k!=='noise_modes')
    .map(([k,v])=>{
      const upd=updates[k]||{};
      const statusColor=v.ok?'var(--success)':'var(--error)';
      const statusText=v.ok?'✓ '+(v.version||''):'✗ not installed';
      const updateBadge=upd.update_available
        ?`<span style="color:var(--warn);font-size:.66rem"> → ${esc(upd.latest)}</span>`
         +`<button class="mini-btn" onclick="startInstall('${esc(k)}','update')">↑ Update</button>`
        :'';
      const installBtn=(!v.ok&&v.installable)
        ?`<button class="mini-btn install-btn" onclick="startInstall('${esc(v.installable)}','install')">Install</button>`
        :'';
      return `<div class="feat">
        <strong>${esc(k)}</strong>
        <span style="color:${statusColor}">${esc(statusText)}</span>${updateBadge}${installBtn}
      </div>`;
    }).join('');
}

async function checkUpdates(btn){
  const orig=btn.textContent;
  btn.textContent='Checking…';btn.disabled=true;
  try{
    const r=await fetch('/api/check-updates');
    const updates=await r.json();
    renderDeps(_depsCache,updates);
    btn.textContent='✓ Done';
    setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},3000);
  }catch(e){
    btn.textContent='Error';
    setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},2000);
  }
}

function startInstall(pkg,action){
  const panel=document.getElementById('install-panel');
  const log=document.getElementById('install-log');
  panel.style.display='block';
  log.textContent='Starting '+action+' for '+pkg+'…\n';
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
  fetch('/api/install',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({pkg,action})
  }).then(r=>r.json()).then(d=>{
    if(d.iid)pollInstall(d.iid);
    else log.textContent+='Error: '+JSON.stringify(d)+'\n';
  }).catch(e=>{log.textContent+='Error: '+e+'\n';});
}

function pollInstall(iid){
  const log=document.getElementById('install-log');
  let lastLine=0;
  const iv=setInterval(async()=>{
    try{
      const r=await fetch('/api/install/'+iid);
      const d=await r.json();
      const newLines=d.log.slice(lastLine);
      if(newLines.length){
        log.textContent+=newLines.join('\n')+'\n';
        lastLine=d.log.length;
        log.scrollTop=log.scrollHeight;
      }
      if(d.status==='done'||d.status==='error'){
        clearInterval(iv);
        if(d.status==='done'){
          setTimeout(()=>loadDeps(),1200);
        }
      }
    }catch(e){clearInterval(iv);}
  },1000);
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

async function loadConfig(){
  try{
    const r=await fetch('/api/config');
    const d=await r.json();
    document.getElementById('ollama_host').value=d.ollama_host||'http://localhost:11434';
    document.getElementById('output_dir').value=d.output_dir||'';
    const os=document.getElementById('ollama_status');
    if(d.ollama_model){
      os.innerHTML=`<span style="color:var(--success)">✓ Ollama running — model: <strong>${esc(d.ollama_model)}</strong>. Chapter titles will be AI-generated.</span>`;
    }else{
      os.innerHTML=`Ollama not running. Install from <a href="https://ollama.com" target="_blank">ollama.com</a> then run <code>ollama pull llama3.2</code>.`;
    }
    const hs=document.getElementById('hf_status');
    if(d.hf_token_set){
      hs.innerHTML=`<span style="color:var(--success)">✓ Token saved (${esc(d.hf_token_hint)}). Speaker diarization is available.</span>`;
    }
  }catch(e){}
}

async function testOllama(){
  const host=document.getElementById('ollama_host').value||'http://localhost:11434';
  const el=document.getElementById('ollama_status');
  el.textContent='Testing…';
  try{
    const r=await fetch('/api/config');
    // Quick proxy via save + re-read
    await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ollama_host:host})});
    const r2=await fetch('/api/config');
    const d=await r2.json();
    if(d.ollama_model){
      el.innerHTML=`<span style="color:var(--success)">✓ Connected — model: <strong>${esc(d.ollama_model)}</strong></span>`;
    }else{
      el.innerHTML=`<span style="color:var(--error)">✗ Ollama not reachable at ${esc(host)}</span>`;
    }
  }catch(e){el.textContent='Error: '+e;}
}

async function saveSettings(){
  const body={
    ollama_host:document.getElementById('ollama_host').value,
    hf_token:document.getElementById('hf_token').value,
    output_dir:document.getElementById('output_dir').value,
  };
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  document.getElementById('hf_token').value='';
  if(!d.ok){
    document.getElementById('output_dir_status').innerHTML=`<span style="color:var(--error)">✗ ${esc(d.error||'Could not create folder')}</span>`;
  }else{
    document.getElementById('output_dir_status').innerHTML=`<span style="color:var(--success)">✓ Saved — new jobs will write here.</span>`;
  }
  await loadConfig();
}

// ── Theme toggle ──────────────────────────────────────────────────────────────
function applyTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  const btn=document.getElementById('theme-btn');
  if(btn)btn.textContent=t==='light'?'☀️':'🌙';
}
function toggleTheme(){
  const cur=document.documentElement.getAttribute('data-theme')||
    (window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
  const next=cur==='light'?'dark':'light';
  applyTheme(next);
  localStorage.setItem('cp-theme',next);
}
(function(){
  const saved=localStorage.getItem('cp-theme');
  const sys=window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark';
  applyTheme(saved||sys);
})();

// ── Transcribe-only toggle ────────────────────────────────────────────────────
function updateTranscribeOnly(){
  const skip=document.getElementById('transcribe_only').checked;
  const opts=document.getElementById('audio-opts');
  opts.style.opacity=skip?'0.35':'1';
  opts.style.pointerEvents=skip?'none':'';
}

pollJobs();loadDeps();loadConfig();
setInterval(()=>{
  fetch('/api/jobs').then(r=>r.json()).then(j=>{
    const running=j.some(x=>x.status==='processing'||x.status==='queued');
    if(running)renderJobs(j);
  }).catch(()=>{});
},3000);
</script>
</body>
</html>
"""


# ─── Job management ───────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Install jobs (separate dict — lightweight, no output files)
_install_jobs: dict[str, dict] = {}
_install_jobs_lock = threading.Lock()


def create_job(title: str, settings: dict) -> str:
    jid = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[jid] = {
            "id": jid,
            "title": title,
            "status": "queued",
            "settings": settings,
            "log": [],
            "created": time.time(),
            "outputs": {},
        }
    return jid


def job_log(jid: str, msg: str):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["log"].append(msg)
            print(f"[{jid[:8]}] {msg}")


def job_status(jid: str, status: str):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["status"] = status


# ─── Full processing pipeline ─────────────────────────────────────────────────

def run_pipeline(input_path: str, output_dir: str, settings: dict,
                 job_id: str | None = None) -> dict:
    """
    Runs the full processing pipeline. Returns dict of output file paths.
    Produces exactly 4 outputs (matching Auphonic):
      {title}.mp3 / .mp4  — improved audio
      {title}.vtt          — YouTube-compatible closed captions
      {title}.json         — word-level transcript (Auphonic format)
      {title}.html         — self-contained interactive transcript editor

    settings keys: model, language, task, normalize,
                   noise_mode (none|afftdn|noisereduce|deepfilternet),
                   diarize, hf_token, lufs, outfmt (mp3|mp4), title
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    stem = settings.get("title") or Path(input_path).stem
    safe_stem = re.sub(r'[<>:"/\\|?*]', "_", stem)[:120]
    fmt = settings.get("outfmt", "mp3").lower()
    if fmt not in ("mp3", "mp4"):
        fmt = "mp3"

    def log(msg: str):
        job_log(job_id, msg) if job_id else print(msg)

    log(f"Processing: {Path(input_path).name}")
    log(f"Output dir: {output_dir}")

    # ── 1. Audio processing ──────────────────────────────────────────────────
    out_audio = os.path.join(output_dir, f"{safe_stem}.{fmt}")
    if settings.get("transcribe_only"):
        log("Audio processing skipped — transcribe-only mode.")
        import shutil as _shutil
        _shutil.copy2(input_path, out_audio)
        tmp_wav_dir = tempfile.mkdtemp(prefix="cp_wav_")
        whisper_wav = os.path.join(tmp_wav_dir, "whisper.wav")
        _ffmpeg("-i", input_path, "-ac", "1", "-ar", "16000", "-f", "wav", whisper_wav)
        wav_for_whisper = whisper_wav
    else:
        wav_for_whisper = process_audio(
            input_path, out_audio,
            fmt=fmt,
            normalize=settings.get("normalize", True),
            noise_mode=settings.get("noise_mode", "none"),
            target_lufs=float(settings.get("lufs", -16.0)),
            log=log,
        )

    duration = get_duration(out_audio) or get_duration(input_path)

    # ── 2. Transcription ─────────────────────────────────────────────────────
    raw_segs, detected_lang = transcribe(
        wav_for_whisper,
        model_size=settings.get("model", "small"),
        language=settings.get("language") or None,
        task=settings.get("task", "transcribe"),
        log=log,
    )

    # ── 3. Speaker diarization (optional) ────────────────────────────────────
    if settings.get("diarize") and HAS_PYANNOTE:
        hf_token = (settings.get("hf_token")
                    or os.environ.get("HF_TOKEN")
                    or load_config().get("hf_token", ""))
        if hf_token:
            try:
                diarization = diarize(wav_for_whisper, hf_token, log=log)
                raw_segs = assign_speakers(raw_segs, diarization)
            except Exception as exc:
                log(f"⚠️ Diarization failed: {exc}")
                import traceback as _tb
                log(_tb.format_exc())
        else:
            log("Diarization skipped: set HF_TOKEN env var or pass --hf-token")

    # ── 4. Paragraphs & chapters ──────────────────────────────────────────────
    raw_segs = mark_paragraphs(raw_segs)
    ollama_host = settings.get("ollama_host", "http://localhost:11434")
    chapters = detect_chapters_with_titles(
        raw_segs, duration,
        ollama_host=ollama_host,
        log=log,
    )

    # ── 5. Shownotes (summaries + tags via Ollama) ────────────────────────────
    shownotes: dict = {}
    ollama_model = ollama_available(ollama_host)
    if ollama_model:
        log("Generating shownotes (summaries & tags)…")
        shownotes = generate_shownotes(raw_segs, stem, ollama_model, ollama_host, log=log)

    # ── 6. Write the 4 output files ───────────────────────────────────────────
    log("Writing output files…")
    outputs: dict[str, str] = {"audio": out_audio}

    vtt_path = os.path.join(output_dir, safe_stem + ".vtt")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(to_vtt(raw_segs))
    outputs["vtt"] = vtt_path

    json_path = os.path.join(output_dir, safe_stem + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_auphonic_json(raw_segs), f, ensure_ascii=False, indent=2, cls=_SafeEncoder)
    outputs["json"] = json_path

    html_path = os.path.join(output_dir, safe_stem + ".html")
    # Use a server URL when running under Flask so the player can fetch the audio;
    # fall back to a relative path for CLI-generated HTML opened directly.
    if job_id:
        audio_ref = f"/audio/{job_id}/{safe_stem}.{fmt}"
    else:
        audio_ref = f"{safe_stem}.{fmt}"
    html = build_output_html(
        title=stem,
        audio_file=audio_ref,
        segments=raw_segs,
        chapters=chapters,
        language=detected_lang,
        duration=duration,
        shownotes=shownotes,
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    outputs["html"] = html_path

    log(f"Done — {len(raw_segs)} segments, {len(chapters)} chapters.")
    log(f"Outputs: {safe_stem}.{fmt}  |  .vtt  |  .json  |  .html")
    return outputs


# ─── Flask web server ─────────────────────────────────────────────────────────

try:
    from flask import Flask, request, jsonify, send_file, redirect
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


def make_app(output_dir: str) -> "Flask":
    from flask import Flask, request, jsonify, send_file, redirect, Response

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB

    @app.route("/")
    def index():
        return _ENGINE_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/process", methods=["POST"])
    def api_process():
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "no file"}), 400

        title = Path(f.filename or "audio").stem
        settings = {
            "model":     request.form.get("model", "small"),
            "language":  request.form.get("language", "").strip() or None,
            "task":      request.form.get("task", "transcribe"),
            "outfmt":    request.form.get("outfmt", "mp3"),
            "transcribe_only": request.form.get("transcribe_only", "0") == "1",
            "normalize":  request.form.get("normalize", "1") == "1",
            "noise_mode": request.form.get("noise_mode", "none"),
            "diarize":    request.form.get("diarize", "0") == "1",
            "lufs":      float(request.form.get("lufs", -16)),
            "title":     title,
        }

        jid = create_job(title, settings)

        # Name the folder after the audio file; add -01, -02 … if it already exists
        safe_stem = re.sub(r'[<>:"/\\|?*\s]+', "-", Path(f.filename or "audio").stem).strip("-") or "audio"
        base_dir = os.path.join(output_dir, safe_stem)
        if not os.path.exists(base_dir):
            job_dir = base_dir
        else:
            n = 1
            while True:
                candidate = f"{base_dir}-{n:02d}"
                if not os.path.exists(candidate):
                    job_dir = candidate
                    break
                n += 1
        Path(job_dir).mkdir(parents=True, exist_ok=True)

        # Save uploaded file
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", f.filename or "audio")
        upload_path = os.path.join(job_dir, "_upload_" + safe_name)
        f.save(upload_path)

        def worker():
            with _jobs_lock:
                _jobs[jid]["started"] = time.time()
            job_status(jid, "processing")
            try:
                outputs = run_pipeline(upload_path, job_dir, settings, job_id=jid)
                with _jobs_lock:
                    _jobs[jid]["outputs"] = outputs
                    _jobs[jid]["status"] = "done"
                    _jobs[jid]["finished"] = time.time()
                job_log(jid, "Processing complete.")
            except Exception as exc:
                job_log(jid, f"ERROR: {exc}")
                with _jobs_lock:
                    _jobs[jid]["finished"] = time.time()
                job_status(jid, "error")
                traceback.print_exc()

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"id": jid})

    @app.route("/api/jobs")
    def api_jobs():
        with _jobs_lock:
            jobs = [
                {k: v for k, v in j.items() if k != "outputs"}
                for j in sorted(_jobs.values(), key=lambda x: -x["created"])
            ]
        return jsonify(jobs)

    @app.route("/api/jobs/<jid>")
    def api_job(jid):
        with _jobs_lock:
            j = _jobs.get(jid)
        if not j:
            return jsonify({"error": "not found"}), 404
        return jsonify({k: v for k, v in j.items() if k != "outputs"})

    @app.route("/results/<jid>")
    def results(jid):
        with _jobs_lock:
            j = _jobs.get(jid)
        if not j:
            return "Job not found", 404
        html_path = j.get("outputs", {}).get("html")
        if not html_path or not os.path.exists(html_path):
            status = j.get("status", "unknown")
            return f"<p>Job status: {status}. Check back when processing is complete.</p>", 202
        # Serve HTML but also make audio accessible
        return send_file(html_path)

    @app.route("/download/<jid>/<fmt>")
    def download(jid, fmt):
        with _jobs_lock:
            j = _jobs.get(jid)
        if not j:
            return "Job not found", 404
        outputs = j.get("outputs", {})
        path = outputs.get(fmt)
        if not path or not os.path.exists(path):
            return f"{fmt} output not found", 404
        return send_file(path, as_attachment=True)

    @app.route("/audio/<jid>/<filename>")
    def audio_file(jid, filename):
        """Serve audio for the transcript editor when viewed via /results/."""
        with _jobs_lock:
            j = _jobs.get(jid)
        if not j:
            return "Not found", 404
        audio_path = j.get("outputs", {}).get("audio")
        if audio_path and os.path.exists(audio_path):
            ext = os.path.splitext(audio_path)[1].lower()
            mime = "audio/mp4" if ext == ".m4a" or ext == ".mp4" else "audio/mpeg"
            return send_file(audio_path, mimetype=mime)
        return "Not found", 404

    @app.route("/api/config", methods=["GET"])
    def api_config_get():
        cfg = load_config()
        token = cfg.get("hf_token", "")
        return jsonify({
            "hf_token_set": bool(token),
            "hf_token_hint": f"…{token[-6:]}" if token else "",
            "ollama_host": cfg.get("ollama_host", "http://localhost:11434"),
            "ollama_model": ollama_available(cfg.get("ollama_host", "http://localhost:11434")),
            "output_dir": output_dir,
        })

    @app.route("/api/config", methods=["POST"])
    def api_config_post():
        data = request.get_json(force=True) or {}
        updates = {}
        if "hf_token" in data and data["hf_token"].strip():
            updates["hf_token"] = data["hf_token"].strip()
        if "ollama_host" in data and data["ollama_host"].strip():
            updates["ollama_host"] = data["ollama_host"].strip()
        if "output_dir" in data and data["output_dir"].strip():
            new_dir = os.path.expanduser(data["output_dir"].strip())
            try:
                Path(new_dir).mkdir(parents=True, exist_ok=True)
                updates["output_dir"] = new_dir
                # Hot-reload: update the closure variable used by new jobs
                nonlocal output_dir
                output_dir = new_dir
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400
        if updates:
            save_config(updates)
        return jsonify({"ok": True})

    # ── Package install endpoints ─────────────────────────────────────────────

    _PKG_MAP = {
        "noisereduce":    ["noisereduce", "soundfile"],
        "soundfile":      ["soundfile", "noisereduce"],
        "pyannote":       ["pyannote.audio"],
        "faster-whisper": ["faster-whisper"],
        "pyloudnorm":     ["pyloudnorm"],
    }

    @app.route("/api/install", methods=["POST"])
    def api_install():
        data    = request.get_json() or {}
        pkg_key = data.get("pkg", "")
        action  = data.get("action", "install")

        iid = str(uuid.uuid4())
        with _install_jobs_lock:
            _install_jobs[iid] = {"status": "running", "log": []}

        def _log(msg):
            with _install_jobs_lock:
                _install_jobs[iid]["log"].append(msg)
            print(f"[install:{iid[:8]}] {msg}")

        def _run():
            try:
                if pkg_key == "deepfilternet":
                    if action == "update" and _DF_VENV_PYTHON.exists():
                        _log("Upgrading DeepFilterNet in isolated venv…")
                        _upgrade_deepfilternet_venv(_log)
                    else:
                        _log("Setting up isolated venv for DeepFilterNet…")
                        _log("⚠ Requires Rust — first install may take 5–15 minutes.")
                        _install_deepfilternet_venv(_log)
                elif pkg_key in _PKG_MAP:
                    packages = _PKG_MAP[pkg_key]
                    verb = "Upgrading" if action == "update" else "Installing"
                    _log(f"{verb}: {', '.join(packages)}")
                    _pip_install(packages, _log, upgrade=(action == "update"))
                else:
                    _log(f"Unknown package key: '{pkg_key}'")
                    with _install_jobs_lock:
                        _install_jobs[iid]["status"] = "error"
                    return
                with _install_jobs_lock:
                    _install_jobs[iid]["status"] = "done"
                _log("✓ Complete — reload the page to see updated status.")
            except Exception as exc:
                _log(f"✗ Error: {exc}")
                with _install_jobs_lock:
                    _install_jobs[iid]["status"] = "error"

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"iid": iid})

    @app.route("/api/install/<iid>")
    def api_install_status(iid):
        with _install_jobs_lock:
            job = _install_jobs.get(iid)
        if not job:
            return jsonify({"error": "not found"}), 404
        return jsonify(job)

    @app.route("/api/check-updates")
    def api_check_updates():
        """Check PyPI for newer versions of installed packages (parallel, cached 24 h)."""
        import importlib.metadata as _im

        check_pkgs = {
            "faster-whisper": (HAS_FASTER_WHISPER, "faster-whisper"),
            "pyloudnorm":      (HAS_PYLOUDNORM,     "pyloudnorm"),
            "soundfile":       (HAS_SOUNDFILE,       "soundfile"),
            "noisereduce":     (HAS_NOISEREDUCE,     "noisereduce"),
            "pyannote.audio":  (HAS_PYANNOTE,        "pyannote.audio"),
        }

        results: dict = {}
        lock = threading.Lock()

        def _check(display_key, ok, pypi_name):
            if not ok:
                with lock:
                    results[display_key] = {"update_available": False}
                return
            try:
                installed = _im.version(pypi_name)
            except Exception:
                with lock:
                    results[display_key] = {"update_available": False}
                return
            latest = _pypi_latest(pypi_name)
            with lock:
                if latest and latest != installed:
                    results[display_key] = {"update_available": True,
                                            "installed": installed, "latest": latest}
                else:
                    results[display_key] = {"update_available": False,
                                            "installed": installed, "latest": latest}

        threads = [
            threading.Thread(target=_check, args=(dk, ok, pn))
            for dk, (ok, pn) in check_pkgs.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=8)
        return jsonify(results)

    @app.route("/api/deps")
    def api_deps():
        def ver(pkg):
            try:
                import importlib.metadata
                return importlib.metadata.version(pkg)
            except Exception:
                return None

        ffmpeg_ok = os.path.isfile(_FFMPEG_BIN) or bool(shutil.which("ffmpeg"))

        # Build the list of available noise reduction modes
        noise_modes = [
            {"value": "none",   "label": "None"},
            {"value": "afftdn", "label": "Standard (ffmpeg afftdn)"},
        ]
        if HAS_NOISEREDUCE and HAS_SOUNDFILE and HAS_NUMPY:
            noise_modes.append({
                "value": "noisereduce",
                "label": "Dynamic (noisereduce — adapts over time)",
            })
        if HAS_DEEPFILTERNET:
            noise_modes.append({
                "value": "deepfilternet",
                "label": "AI Enhanced (DeepFilterNet — highest quality)",
            })

        def pkg(ok, version, installable=None):
            d = {"ok": ok, "version": version}
            if installable:
                d["installable"] = installable
            return d

        return jsonify({
            "ffmpeg":         pkg(ffmpeg_ok, "system" if ffmpeg_ok else None),
            "faster-whisper": pkg(HAS_FASTER_WHISPER, ver("faster-whisper")),
            "pyloudnorm":     pkg(HAS_PYLOUDNORM, ver("pyloudnorm")),
            "soundfile":      pkg(HAS_SOUNDFILE, ver("soundfile"),
                                  None if HAS_SOUNDFILE else "noisereduce"),
            "noisereduce":    pkg(HAS_NOISEREDUCE, ver("noisereduce"),
                                  None if HAS_NOISEREDUCE else "noisereduce"),
            "pyannote.audio": pkg(HAS_PYANNOTE, ver("pyannote.audio"),
                                  None if HAS_PYANNOTE else "pyannote"),
            "deepfilternet":  pkg(HAS_DEEPFILTERNET,
                                  "isolated venv" if HAS_DEEPFILTERNET else None,
                                  None if HAS_DEEPFILTERNET else "deepfilternet"),
            "noise_modes":    noise_modes,
        })

    return app


# ─── CLI ──────────────────────────────────────────────────────────────────────

def cmd_setup(args):
    """Interactive setup: store HuggingFace token and Ollama settings."""
    cfg = load_config()
    print("\n⟁ auphonic-oss setup\n")

    # ── HuggingFace token ────────────────────────────────────────────────────
    print("Speaker diarization requires a free HuggingFace token.")
    print("Steps to get one (takes ~2 minutes):")
    print("  1. Create a free account at https://huggingface.co/join")
    print("  2. Go to  https://huggingface.co/settings/tokens  → New token")
    print("  3. Accept the model license at https://huggingface.co/pyannote/speaker-diarization-3.1")
    print("  4. Paste the token below.\n")

    # Try to open the browser automatically
    import webbrowser
    webbrowser.open("https://huggingface.co/settings/tokens")

    current = cfg.get("hf_token", "")
    hint = f" (current: …{current[-6:]})" if current else ""
    raw = input(f"HuggingFace token{hint} [Enter to skip]: ").strip()
    if raw:
        save_config({"hf_token": raw})
        print("  ✓ Token saved.\n")
    else:
        print("  — Skipped.\n")

    # ── Ollama host ──────────────────────────────────────────────────────────
    current_host = cfg.get("ollama_host", "http://localhost:11434")
    raw_host = input(f"Ollama host [{current_host}]: ").strip()
    host = raw_host or current_host
    model = ollama_available(host)
    if model:
        print(f"  ✓ Ollama is running — will use model '{model}' for chapter titles.")
    else:
        print(f"  ✗ Ollama not reachable at {host}.")
        print("    Install from https://ollama.com then run:  ollama pull llama3.2")
        print("    Chapter titles will fall back to first-words heuristic until then.")
    save_config({"ollama_host": host})
    print(f"  ✓ Ollama host saved.\n")

    print("Setup complete. Config stored at:", CONFIG_FILE)
    print("Run 'python castpolish.py serve' to start the web interface.\n")


def cmd_process(args):
    if not (os.path.isfile(_FFMPEG_BIN) or shutil.which("ffmpeg")):
        sys.exit("ERROR: ffmpeg not found. Install it: brew install ffmpeg")
    if not HAS_FASTER_WHISPER and not HAS_OPENAI_WHISPER:
        sys.exit("ERROR: Install faster-whisper:  pip install faster-whisper")

    cfg = load_config()
    settings = {
        "model":       args.model,
        "language":    args.language,
        "task":        args.task,
        "outfmt":      args.format,
        "normalize":   not args.no_normalize,
        "noise_mode":  args.noise_mode,
        "diarize":     args.diarize,
        "hf_token":    args.hf_token or os.environ.get("HF_TOKEN") or cfg.get("hf_token"),
        "ollama_host": cfg.get("ollama_host", "http://localhost:11434"),
        "lufs":        args.lufs,
        "title":       args.title or Path(args.input).stem,
    }

    out_dir = args.output_dir or os.path.join(os.getcwd(), "output",
                                               Path(args.input).stem)
    outputs = run_pipeline(args.input, out_dir, settings)

    print("\n── Outputs ─────────────────────────────────────")
    labels = {"audio": "audio", "vtt": "captions", "json": "transcript", "html": "editor"}
    for key, path in outputs.items():
        label = labels.get(key, key)
        print(f"  {label:12s}  {path}")
    print()


def cmd_serve(args):
    if not HAS_FLASK:
        sys.exit("ERROR: Flask not installed:  pip install flask")
    if not (os.path.isfile(_FFMPEG_BIN) or shutil.which("ffmpeg")):
        print("WARNING: ffmpeg not found. Audio processing will fail.")
    if not HAS_FASTER_WHISPER and not HAS_OPENAI_WHISPER:
        print("WARNING: No transcription backend. Install faster-whisper.")

    out_dir = args.output_dir or load_config().get("output_dir") or os.path.join(Path.home(), "CastPolish-output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    app = make_app(out_dir)
    host, port = "127.0.0.1", args.port

    print(f"\n  ⟁ CastPolish")
    print(f"  Web interface:  http://{host}:{port}/")
    print(f"  Output dir:     {out_dir}")
    print(f"  Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False, threaded=True)


def main():
    parser = argparse.ArgumentParser(
        prog="castpolish",
        description="CastPolish — Open-source audio processing & transcription (Auphonic alternative)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── setup ──
    sub.add_parser("setup",
                   help="Store HuggingFace token & Ollama settings (opens browser)")

    # ── serve ──
    serve_p = sub.add_parser("serve", help="Start local web interface")
    serve_p.add_argument("--port",       type=int, default=8765)
    serve_p.add_argument("--output-dir", help="Where to store job outputs")

    # ── process ──
    proc_p = sub.add_parser("process", help="Process an audio file from CLI")
    proc_p.add_argument("input",          help="Input audio/video file")
    proc_p.add_argument("--model",        default="small",
                        choices=["tiny","base","small","medium","large-v2","large-v3"],
                        help="Whisper model (default: small)")
    proc_p.add_argument("--language",     default=None,
                        help="Language code, e.g. en (default: auto-detect)")
    proc_p.add_argument("--task",         default="transcribe",
                        choices=["transcribe","translate"])
    proc_p.add_argument("--format",        default="mp3", choices=["mp3","mp4"],
                        help="Output audio format (default: mp3)")
    proc_p.add_argument("--no-normalize", action="store_true",
                        help="Skip loudness normalisation and leveling")
    proc_p.add_argument("--noise-mode",  dest="noise_mode", default="none",
                        choices=["none", "afftdn", "noisereduce", "deepfilternet"],
                        help="Noise reduction: none | afftdn | noisereduce | deepfilternet")
    proc_p.add_argument("--diarize",      action="store_true",
                        help="Speaker diarization (requires pyannote.audio + HF_TOKEN)")
    proc_p.add_argument("--hf-token",     help="HuggingFace token for diarization")
    proc_p.add_argument("--lufs",         type=float, default=-16.0,
                        help="Loudness target in LUFS (default: -16, EBU R128)")
    proc_p.add_argument("--title",        help="Override output title/filename")
    proc_p.add_argument("--output-dir",   help="Output directory")

    args = parser.parse_args()
    {"setup": cmd_setup, "serve": cmd_serve, "process": cmd_process}[args.command](args)


if __name__ == "__main__":
    main()
