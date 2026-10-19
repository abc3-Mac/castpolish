#!/usr/bin/env python3
"""Write "A Mighty Fortress" (Ein feste Burg, isometric, C major) as a MIDI file for a soundfont organ,
then render it with FluidSynth if a soundfont is given.

Score: the public-domain four-part Mutopia setting (same notes as organ_mighty_fortress.py).
Registration follows the video, done with GM patches, channel volume and expression:
  0–26 s   Flute (GM 74) soprano+alto only, quiet           — storm and cell
  26–40 s  Church Organ (GM 20) all four parts fade in       — Romans
  42 s+    16' pedal (bass an octave down) on a second organ — door
  64 s+    mixture: upper parts doubled an octave up, soft   — montage/invitation
  70–80 s  swell to full                                     — invitation, end card
Usage: python3 hymn_midi.py [--sf2 PATH] [--end-at 86] [--lead 2.5]
Output: organ-mighty-fortress.mid and, with --sf2, organ-mighty-fortress-v2.wav/.mp3
"""
import re, sys, struct, subprocess, pathlib

OUT = pathlib.Path(__file__).resolve().parent
END_AT = float(sys.argv[sys.argv.index("--end-at") + 1]) if "--end-at" in sys.argv else 86.0
LEAD = float(sys.argv[sys.argv.index("--lead") + 1]) if "--lead" in sys.argv else 2.5
SF2 = sys.argv[sys.argv.index("--sf2") + 1] if "--sf2" in sys.argv else None

VOICES = {
"S": "c''4 c'' c'' g'8 a' b'4 c''8 b' a'4 g' c'' b' a' g' a' f'8 e' d'4 c' c'' c'' c'' g'8 a' b'4 c''8 b' a'4 g' c'' b' a' g' a' f'8 e' d'4 c' c' g' a' g' fis' g'2. c'4 g' g' a' b' c''2. b'4 c'' b' a' a' g'2. a'4 a' g' a' f' e'2. c''4 b' a' g' a' f'8 e' d'4 c'",
"A": "e'4 c' e' d' g' e' fis' g' e' e' c' c' c' a b c' e' c' e' d' e' c' d'8 c' b4 c' e' c' c' c' a b c' c' e' e' d' d'8 c' b2. c'4 d' e' c' d' c'2. e'4 e' e' e' d'8 c' b2. c'4 f' e' e' d' b2. c'4 e' c' e' e' a b c'",
"T": "g4 g g b b a d'8 c' b4 a g f e e f g e g g g b g e fis g e g f e e f g8 f e4 e g c' b a g2. e4 g g f f e2. b4 a gis a fis g2. c'4 c' b a a gis2. a4 g a c' c' f g8 f e4",
"B": "c4 e c g d a d g a e f c a, d g, c c e c g e a, d g, a, e f c a, d g, c c c a, b,8 c d4 g,2. c4 b, c f d a,2. gis,4 a, b, c d g,2. f,4 a, c cis d e2. a,4 e f c a, d g, c",
}
STEP = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

def parse(ly):
    out, beat, dur = [], 0.0, 1.0
    for tok in ly.split():
        m = re.fullmatch(r"([a-g])(is|es)?('*|,*)(\d+)?(\.*)", tok)
        if not m: continue
        step, acc, octv, d, dots = m.groups()
        if d: dur = 4.0 / int(d) * (1.5 if dots == "." else 1.0)
        midi = 48 + STEP[step] + (1 if acc == "is" else -1 if acc == "es" else 0) + 12 * (octv.count("'") - octv.count(","))
        out.append((midi, beat, dur)); beat += dur
    return out

parts = {v: parse(ly) for v, ly in VOICES.items()}
last_onset = max(s for _, s, _ in parts["S"])
FINAL_HOLD = 6.0
spb = (END_AT - FINAL_HOLD - LEAD) / last_onset
bpm = 60 / spb
TPQ = 480
def tick(sec): return int(round(sec / spb * TPQ))        # seconds -> ticks (tempo is constant)

# ---- channels: (program, pan) ----
CH = {"flute": (0, 73, 64), "organ": (1, 19, 64), "pedal": (2, 19, 60), "mix": (3, 19, 70)}

events = []  # (tick, order, bytes)
def ev(t, data, order=1): events.append((t, order, data))
def vbytes(ch, cc, val, t): ev(t, bytes([0xB0 | ch, cc, val]), 0)

for name, (ch, prog, pan) in CH.items():
    ev(0, bytes([0xC0 | ch, prog]), 0); vbytes(ch, 10, pan, 0); vbytes(ch, 91, 90, 0)   # reverb send

def ramp(ch, cc, t0, t1, v0, v1, steps=40):
    for i in range(steps + 1):
        t = t0 + (t1 - t0) * i / steps
        vbytes(ch, cc, int(round(v0 + (v1 - v0) * i / steps)), tick(t))

# registration automation (seconds)
ramp(0, 7, 0, 0, 70, 70); ramp(0, 7, 26, 40, 70, 0)                     # flute fades out at Romans
ramp(1, 7, 0, 0, 0, 0); ramp(1, 7, 26, 40, 0, 95); ramp(1, 7, 42, 50, 95, 110)
ramp(2, 7, 0, 0, 0, 0); ramp(2, 7, 42, 48, 0, 100)                      # pedal in at the door
ramp(3, 7, 0, 0, 0, 0); ramp(3, 7, 64, 72, 0, 60)                       # mixture
for ch in (1, 2, 3): ramp(ch, 11, 0, 0, 100, 100); ramp(ch, 11, 70, 80, 100, 127)   # swell
ramp(0, 11, 0, 0, 100, 100)

def note(ch, midi, start_s, dur_s, vel):
    ev(tick(start_s), bytes([0x90 | ch, midi, vel]), 1)
    ev(tick(start_s + dur_s), bytes([0x80 | ch, midi, 0]), 1)

for v, evs in parts.items():
    for midi, s, d in evs:
        t0 = LEAD + s * spb; dur = d * spb * 0.98
        if s == last_onset: dur = FINAL_HOLD
        if v in ("S", "A"):
            note(0, midi, t0, dur, 80)                 # flute (faded out later)
            note(3, midi + 12, t0, dur, 60)            # mixture (faded in later)
        note(1, midi, t0, dur, 96)                     # organ, all parts
        if v == "B": note(2, midi - 12, t0, dur, 100)  # 16' pedal

# ---- write a format-0 MIDI ----
events.sort(key=lambda e: (e[0], e[1]))
def vlq(n):
    out = [n & 0x7F]; n >>= 7
    while n: out.append((n & 0x7F) | 0x80); n >>= 7
    return bytes(reversed(out))
track = bytearray(b"\x00\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / bpm))[1:])   # tempo
last = 0
for t, _, data in events:
    track += vlq(t - last) + data; last = t
track += vlq(tick(2.0)) + b"\xFF\x2F\x00"
mid = OUT / "organ-mighty-fortress.mid"
mid.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, TPQ) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track))
print(f"wrote {mid.name}: {bpm:.0f} bpm, last chord at {LEAD + last_onset*spb:.1f} s, ends {END_AT} s")

if SF2:
    wav = OUT / "organ-mighty-fortress-v2.wav"; mp3 = OUT / "organ-mighty-fortress-v2.mp3"
    subprocess.run(["fluidsynth", "-ni", "-g", "0.8", "-r", "48000", "-R", "1", "-o", "synth.reverb.room-size=0.85",
                    "-o", "synth.reverb.damp=0.3", "-o", "synth.reverb.width=0.9", "-o", "synth.reverb.level=0.7",
                    "-F", str(wav), SF2, str(mid)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", f"atrim=0:{END_AT + 2:.1f},afade=t=out:st={END_AT - 1:.1f}:d=3",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
    print("rendered", mp3.name)
