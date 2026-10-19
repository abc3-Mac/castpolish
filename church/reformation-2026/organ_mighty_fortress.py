#!/usr/bin/env python3
"""Render "A Mighty Fortress Is Our God" (Ein feste Burg, isometric form, C major) as a pipe organ.

Notes: the four-part public-domain setting from the Mutopia Project
(https://www.mutopiaproject.org/ftp/LutherM/ein_feste_burg/ein_feste_burg.ly, source cyberhymnal.org).
Synthesis: additive organ voices in numpy; registration grows across the piece to follow the video:
  soft flute, soprano+alto only           -> under the storm and the cell
  principal, all four parts fade in       -> from the Romans resolution
  full organ with 16' pedal and mixture   -> door, montage, invitation, end card
Usage: python3 organ_mighty_fortress.py [--end-at 86] [--lead 2.5]
Output: organ-mighty-fortress-v1.wav and .mp3 (with church reverb)
"""
import re, sys, math, subprocess, pathlib
import numpy as np

OUT = pathlib.Path(__file__).resolve().parent
SR = 48000
END_AT = float(sys.argv[sys.argv.index("--end-at") + 1]) if "--end-at" in sys.argv else 86.0   # final chord fully released by here
LEAD = float(sys.argv[sys.argv.index("--lead") + 1]) if "--lead" in sys.argv else 2.5

VOICES = {
"S": "c''4 c'' c'' g'8 a' b'4 c''8 b' a'4 g' c'' b' a' g' a' f'8 e' d'4 c' c'' c'' c'' g'8 a' b'4 c''8 b' a'4 g' c'' b' a' g' a' f'8 e' d'4 c' c' g' a' g' fis' g'2. c'4 g' g' a' b' c''2. b'4 c'' b' a' a' g'2. a'4 a' g' a' f' e'2. c''4 b' a' g' a' f'8 e' d'4 c'",
"A": "e'4 c' e' d' g' e' fis' g' e' e' c' c' c' a b c' e' c' e' d' e' c' d'8 c' b4 c' e' c' c' c' a b c' c' e' e' d' d'8 c' b2. c'4 d' e' c' d' c'2. e'4 e' e' e' d'8 c' b2. c'4 f' e' e' d' b2. c'4 e' c' e' e' a b c'",
"T": "g4 g g b b a d'8 c' b4 a g f e e f g e g g g b g e fis g e g f e e f g8 f e4 e g c' b a g2. e4 g g f f e2. b4 a gis a fis g2. c'4 c' b a a gis2. a4 g a c' c' f g8 f e4",
"B": "c4 e c g d a d g a e f c a, d g, c c e c g e a, d g, a, e f c a, d g, c c c a, b,8 c d4 g,2. c4 b, c f d a,2. gis,4 a, b, c d g,2. f,4 a, c cis d e2. a,4 e f c a, d g, c",
}
STEP = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

def parse(ly):
    """LilyPond absolute pitch -> list of (midi, start_beat, dur_beats)."""
    out, beat, dur = [], 0.0, 1.0
    for tok in ly.split():
        m = re.fullmatch(r"([a-g])(is|es)?('*|,*)(\d+)?(\.*)", tok)
        if not m: continue
        step, acc, octv, d, dots = m.groups()
        if d:
            dur = 4.0 / int(d); dur *= 1.5 if dots == "." else 1.0
        midi = 48 + STEP[step] + (1 if acc == "is" else -1 if acc == "es" else 0) + 12 * (octv.count("'") - octv.count(","))
        out.append((midi, beat, dur)); beat += dur
    return out

parts = {v: parse(ly) for v, ly in VOICES.items()}
total_beats = max(s + d for _, s, d in parts["S"])
last_onset = max(s for _, s, _ in parts["S"])
# tempo so the final chord starts around END_AT - 7 s, leaving a long held chord and release
final_hold = 6.0
spb = (END_AT - final_hold - LEAD) / last_onset          # seconds per beat
bpm = 60 / spb
print(f"beats {total_beats:.0f}, tempo {bpm:.0f} bpm, last chord at {LEAD + last_onset*spb:.1f}s, ends {END_AT}s")

def tone(freq, seconds, harmonics, attack=0.04, release=0.25):
    n = int(seconds * SR); t = np.arange(n) / SR
    y = np.zeros(n)
    for k, amp in enumerate(harmonics, 1):
        if freq * k > SR / 2.2: break
        y += amp * np.sin(2 * math.pi * freq * k * t)
        y += amp * 0.35 * np.sin(2 * math.pi * freq * k * 1.0012 * t + 0.7)   # gentle chorus
    env = np.ones(n)
    a = min(int(attack * SR), n); r = min(int(release * SR), n)
    env[:a] = np.linspace(0, 1, a); env[n - r:] = np.linspace(1, 0, r)
    return y * env

FLUTE = [1.0, 0.18, 0.04]
PRINCIPAL = [1.0, 0.55, 0.30, 0.22, 0.10, 0.07, 0.05, 0.04]
MIXTURE = [0.0, 0.5, 0.0, 0.5, 0.0, 0.35, 0.0, 0.3]

def render_voice(events, harmonics, transpose=0, length_s=None):
    buf = np.zeros(int(length_s * SR))
    for midi, start, dur in events:
        f = 440.0 * 2 ** ((midi + transpose - 69) / 12)
        s0 = int((LEAD + start * spb) * SR)
        secs = dur * spb * 1.02 + 0.2
        if start == last_onset: secs = final_hold + 0.5
        y = tone(f, secs, harmonics)
        e = min(s0 + len(y), len(buf)); buf[s0:e] += y[:e - s0]
    return buf

LEN = END_AT + 2.0
mix = np.zeros(int(LEN * SR)); t = np.arange(len(mix)) / SR

def ramp(t, t0, t1):            # 0 before t0, 1 after t1, linear between
    return np.clip((t - t0) / max(t1 - t0, 1e-6), 0, 1)

# registration curves (seconds, matched to the animatic timing: Romans 28 s, door 42 s, invite 71 s)
flute_gain = 0.30 * (1 - ramp(t, 26, 40))
princ_gain = 0.55 * ramp(t, 26, 40) + 0.25 * ramp(t, 42, 50)
lower_gain = ramp(t, 27, 38)                                   # tenor + bass enter with the Romans resolution
pedal_gain = 0.50 * ramp(t, 42, 48)
mixture_gain = 0.35 * ramp(t, 64, 72)
swell = 1.0 + 0.35 * ramp(t, 70, 80)

for v, ev in parts.items():
    upper = v in ("S", "A")
    fl = render_voice(ev, FLUTE, 0, LEN); pr = render_voice(ev, PRINCIPAL, 0, LEN); mx = render_voice(ev, MIXTURE, 0, LEN)
    g = 1.0 if upper else lower_gain
    mix += g * (fl * flute_gain + pr * princ_gain + mx * mixture_gain)
mix += render_voice(parts["B"], PRINCIPAL[:4], -12, LEN) * pedal_gain
mix *= swell
mix /= np.max(np.abs(mix)) * 1.15
wav = OUT / "organ-mighty-fortress-v1.wav"
import wave
with wave.open(str(wav), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())
mp3 = OUT / "organ-mighty-fortress-v1.mp3"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af",
                "aecho=0.75:0.6:45|110|230|420:0.32|0.24|0.16|0.08,lowpass=f=9000,aformat=channel_layouts=stereo",
                "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
print("wrote", mp3.name)
