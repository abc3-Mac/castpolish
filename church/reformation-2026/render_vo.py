#!/usr/bin/env python3
"""Render the Reformation 2026 narration in Albert's ElevenLabs voice clone.

Reads 02-vo/vo-only.txt (one paragraph per segment) plus the two on-camera pastor lines
(rendered as STAND-INS for the animatic; the real ones are recorded in the sanctuary).
Uses the same voice, model and settings as castopod-server/tooling/gen_ship.py.
Writes 02-vo/<segment>.mp3, a loudness-normalised 02-vo/vo-all-16lufs.mp3, and vo-timing.txt.
Usage: python3 render_vo.py [--dry]   (skips segments whose mp3 already exists)
"""
import os, sys, json, time, urllib.request, subprocess, pathlib
ROOT = pathlib.Path.home() / "Movies/Reformation-2026"; VO = ROOT / "02-vo"
sys.path.insert(0, os.path.expanduser("~/Documents/castopod-server/tooling"))
try:
    from voice_processor import to_speakable
except Exception as e:
    print("voice_processor unavailable, using raw text:", e); to_speakable = None

env = {}
for line in open(os.path.expanduser("~/.elevenlabs.env")):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v
API, VOICE = env["ELEVENLABS_API_KEY"], env["ELEVENLABS_VOICE_ID"]

paras = [p.strip() for p in (VO / "vo-only.txt").read_text().split("\n\n") if p.strip()]
names = ["01-open", "02-strike", "03-cell", "04-romans", "05-door", "06-montage", "08-invite"]
assert len(paras) == len(names), f"expected {len(names)} narration paragraphs, found {len(paras)}"
segments = list(zip(names, paras)) + [
    ("07-pastor", "Five hundred years later, the question is the same: Am I enough? The honest answer is no — but Jesus is. You are forgiven, and you are free to love your neighbor."),
    ("09-end", "Come meet the Jesus Luther found. We'll save you a seat."),
]

def speakable(t):
    if not to_speakable: return t
    try: return to_speakable(t, spell_years_out=False, engine="elevenlabs")
    except TypeError: return to_speakable(t, spell_years_out=False)

def tts(text, prev, nxt):
    body = {"text": text, "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True, "speed": 1.08}}
    if prev: body["previous_text"] = prev[-600:]
    if nxt: body["next_text"] = nxt[:600]
    u = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128"
    r = urllib.request.Request(u, data=json.dumps(body).encode(),
        headers={"xi-api-key": API, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    with urllib.request.urlopen(r, timeout=180) as resp: return resp.read()

spoken = [(n, speakable(t)) for n, t in segments]
for n, t in spoken: print(f"[{n}] {t}")
if "--dry" in sys.argv: sys.exit(0)

for i, (n, t) in enumerate(spoken):
    dst = VO / f"{n}.mp3"
    if dst.exists() and dst.stat().st_size > 2000: print(f"{n}: exists, skip"); continue
    prev = spoken[i-1][1] if i > 0 and i < 7 else ""; nxt = spoken[i+1][1] if i < 6 else ""
    try: audio = tts(t, prev, nxt)
    except urllib.error.HTTPError as e: print(f"{n}: HTTP {e.code} -> {e.read().decode()[:300]}"); sys.exit(2)
    if audio[:3] != b"ID3" and audio[0] != 0xFF: print(f"{n}: not audio -> {audio[:120]!r}"); sys.exit(3)
    dst.write_bytes(audio); print(f"{n}: OK {len(audio)} bytes"); time.sleep(1)

lines = []; total = 0.0
for n, _ in spoken:
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(VO / f"{n}.mp3")], capture_output=True, text=True).stdout.strip())
    lines.append(f"{n:12s} {d:6.1f} s"); total += d if not n.startswith(("07", "09")) else 0
lst = VO / "concat.txt"; lst.write_text("".join(f"file '{VO / (n + '.mp3')}'\n" for n, _ in spoken[:7]))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "160k", str(VO / "vo-all-16lufs.mp3")])
rep = "\n".join(lines) + f"\n\nnarration only (7 VO segments): {total:.1f} s of speech\n"
(VO / "vo-timing.txt").write_text(rep); print(rep)
