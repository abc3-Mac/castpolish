#!/usr/bin/env python3
"""
mps_diarization_repro.py — reproduce / retest the pyannote-on-MPS crash.

Background
----------
On 2026-06-19 a 2.5-hour diarization run inside CastPolish aborted partway
through with a hard Metal assertion:

    Unable to reach MTLCompilerService ... error 32 - Broken pipe
    MPSKernelDAG.mm:1290: failed assertion `Error getting visible function...'

That is a SIGABRT from Apple's Metal shader-compiler service dropping its
connection under sustained load — NOT a catchable Python exception. CastPolish
now defaults speaker diarization to CPU (config key `diarize_device`) to avoid
it. See README → "Diarization device".

What this script is for
-----------------------
1. A minimal, standalone repro to attach to a PyTorch MPS issue
   (the realistic upstream fix lives in pytorch/pytorch, not Apple Feedback —
   search their tracker for "MTLCompilerService" / "MPS" / "failed assertion").
2. A retest harness: after a macOS or PyTorch update, run this on a long file.
   - If it PRINTS "✅ Completed on MPS" → MPS may be stable again; you can try
     flipping CastPolish back to GPU by setting "diarize_device": "mps" (or
     "auto") in ~/.castpolish/config.json.
   - If it ABORTS with the Metal assertion → still broken; stay on CPU.

Because the failure is a process-level abort, this script cannot "catch" it —
a crash means the OS prints the assertion and the process dies with a non-zero
signal. Success is the run finishing and printing the completion banner.

Usage
-----
    python3 tools/mps_diarization_repro.py /path/to/long_audio.{wav,mp3,m4a,mp4}

    # HF token is read from (in order): $HF_TOKEN, ~/.castpolish/config.json
    # Use a recording at least ~60-90 min long; short clips rarely trigger it.

Requirements: pyannote.audio, torch (with MPS), and a HuggingFace token that
has accepted the pyannote/speaker-diarization-3.1 model license.
"""
import json
import os
import sys
import time
from pathlib import Path


def load_hf_token() -> str:
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        return token
    cfg = Path.home() / ".castpolish" / "config.json"
    if cfg.exists():
        try:
            return json.loads(cfg.read_text()).get("hf_token", "").strip()
        except (json.JSONDecodeError, OSError):
            pass
    return ""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        print("ERROR: pass exactly one audio file path.", file=sys.stderr)
        return 2

    audio_path = sys.argv[1]
    if not os.path.isfile(audio_path):
        print(f"ERROR: file not found: {audio_path}", file=sys.stderr)
        return 2

    token = load_hf_token()
    if not token:
        print("ERROR: no HuggingFace token. Set $HF_TOKEN or put it in "
              "~/.castpolish/config.json", file=sys.stderr)
        return 2

    import torch
    from pyannote.audio import Pipeline

    # ── Environment banner (copy/paste this into a bug report) ───────────────
    import platform
    print("=" * 70)
    print("pyannote-on-MPS repro / retest")
    print("=" * 70)
    print(f"macOS:           {platform.mac_ver()[0]}  ({platform.machine()})")
    print(f"Python:          {platform.python_version()}")
    print(f"torch:           {torch.__version__}")
    print(f"MPS available:   {torch.backends.mps.is_available()}")
    print(f"MPS built:       {torch.backends.mps.is_built()}")
    try:
        import pyannote.audio as pa
        print(f"pyannote.audio:  {pa.__version__}")
    except Exception:
        pass
    print(f"audio file:      {audio_path}")
    sz = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"file size:       {sz:.1f} MB")
    print("=" * 70)

    if not torch.backends.mps.is_available():
        print("MPS is not available on this machine — nothing to test. Exiting.")
        return 1

    device = torch.device("mps")
    print(f"\nLoading pyannote/speaker-diarization-3.1 onto {device} …")
    t0 = time.time()
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", token=token
    )
    pipeline.to(device)
    print(f"  pipeline loaded in {time.time() - t0:.1f}s")

    # Show per-stage progress if pyannote exposes the hook (it does in v3+).
    hook = None
    try:
        from pyannote.audio.pipelines.utils.hook import ProgressHook
        hook = ProgressHook()
    except Exception:
        pass

    print("\nRunning diarization on MPS — this is where the crash historically "
          "occurs (~30+ min in on a long file).")
    print("If the process dies with 'MTLCompilerService ... Broken pipe' / "
          "'failed assertion', the MPS bug is still present.\n")
    sys.stdout.flush()

    t1 = time.time()
    if hook is not None:
        with hook as h:
            result = pipeline(audio_path, hook=h)
    else:
        result = pipeline(audio_path)
    elapsed = time.time() - t1

    annotation = getattr(result, "speaker_diarization", result)
    speakers = set()
    turns = 0
    for _turn, _, spk in annotation.itertracks(yield_label=True):
        speakers.add(spk)
        turns += 1

    print("\n" + "=" * 70)
    print(f"✅ Completed on MPS in {elapsed/60:.1f} min "
          f"({turns} turns, {len(speakers)} speakers).")
    print("MPS finished without aborting — it MAY be stable again on this "
          "OS/torch combo.")
    print("To try the GPU path in CastPolish, set \"diarize_device\": \"mps\" "
          "in ~/.castpolish/config.json and re-run a real job to confirm.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
