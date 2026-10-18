#!/usr/bin/env python3
"""Generate a stand-in pipe-organ underscore for "The Storm and the Door" with the ElevenLabs Music API
(the same route as the Bad Boll podcast bumpers). An original piece in the Lutheran chorale idiom —
it will NOT quote "Ein feste Burg" note for note; the church organist's recording is the real plan.

Usage: python3 gen_underscore.py [--redo]   -> 06-music-sfx/organ-underscore-v1.mp3 (~100 s)
"""
import json, os, sys, urllib.request, urllib.error, pathlib
OUT = pathlib.Path(__file__).resolve().parent
env = {}
for line in open(os.path.expanduser("~/.elevenlabs.env")):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v
API = env["ELEVENLABS_API_KEY"]

PROMPT = ("Solo pipe organ instrumental underscore for a 90-second Reformation Day church video, in the idiom of "
          "Martin Luther's 16th-century German chorales. It opens almost silent: a single low pedal tone and sparse, "
          "dark, solemn modal chords in the spirit of 'Aus tiefer Not' for the first thirty-five seconds, slow and still. "
          "Around forty seconds a warm major chord resolves, like light arriving. From about fifty seconds it builds "
          "steadily into a confident, bright, full-organ chorale in the spirit of 'Ein feste Burg ist unser Gott' "
          "(A Mighty Fortress Is Our God), stately four-four, hymn-like phrases, and ends with one big sustained chord "
          "that rings in a stone church and fades naturally. Pipe organ only: no drums, no vocals, no choir, no "
          "orchestra, no modern instruments. Natural cathedral reverb.")

redo = "--redo" in sys.argv
n = 1
while (OUT / f"organ-underscore-v{n}.mp3").exists() and redo: n += 1
dst = OUT / f"organ-underscore-v{n}.mp3"
if dst.exists() and dst.stat().st_size > 10000: print(f"{dst.name}: exists (use --redo)"); sys.exit(0)
body = {"prompt": PROMPT, "music_length_ms": 100000, "model_id": "music_v1"}
req = urllib.request.Request("https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128",
    data=json.dumps(body).encode(), headers={"xi-api-key": API, "Content-Type": "application/json"}, method="POST")
try:
    audio = urllib.request.urlopen(req, timeout=600).read()
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} -> {e.read().decode()[:400]}"); sys.exit(2)
if audio[:3] != b"ID3" and audio[0] != 0xFF: print("not audio:", audio[:200]); sys.exit(3)
dst.write_bytes(audio); print(f"{dst.name}: OK {len(audio)} bytes")
