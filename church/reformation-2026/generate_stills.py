#!/usr/bin/env python3
"""Generate the Grok stills for "The Storm and the Door" via the Grok CLI's image tools.

Each clip gets its own folder; the result is copied in as <clip>-vN.jpg.
Usage: python3 generate_stills.py [clip ...]   (default: all)
"""
import subprocess, pathlib, sys, time, urllib.parse, shutil, os

ROOT = pathlib.Path(__file__).resolve().parent
GROK = pathlib.Path.home() / ".grok/bin/grok"
SESSIONS = pathlib.Path.home() / ".grok/sessions"
HEADER = ("Vertical 9:16, cinematic, painterly early-16th-century Germany, muted earth tones with warm "
          "candlelight, film grain, no text, no modern objects, no readable faces (figures in shadow, hood, or from behind).")
G1 = ROOT / "G1-road/G1-road-v1.jpg"

def gen(body):
    return ("image_gen", f'Call the image_gen tool exactly once with aspect_ratio 9:16 and this prompt: "{HEADER} {body}" '
                         "Then reply with the saved file path only.")

CLIPS = {
 "G2-strike": ("image_edit",
   f'Call the image_edit tool exactly once with image "{G1}" and this prompt: "Keep the same painterly road, fields, '
   'hooded figure and rain. A single massive lightning bolt now strikes a lone tree beside the road twenty feet from the '
   f'figure, a blinding white flash lighting the whole scene, the figure thrown backward into the mud, smoke and rain. {HEADER}" '
   'Then reply with the saved file path only.'),
 "G3-cell": gen("Stone monastery cell, one candle on a wooden desk, a kneeling monk seen from behind, hands clasped around a worn leather Bible, breath visible in the cold air. Very dark, very still."),
 "G4-page": gen("Extreme close-up of an open hand-printed Latin Bible on a wooden desk, the page headed with the large words EPISTOLA AD ROMANOS and nothing else legible, dense blackletter text below, warm golden light growing from the top of the frame until the page glows, dust drifting in the light."),
 "G4b-cross": gen("A wooden crucifix with the carved body of Christ on the cross, hanging on a rough stone wall above a monk's desk, a single candle below it, warm light catching the carved figure, deep shadow around, quiet and reverent. The figure of Christ is clearly present on the cross."),
 "G6-press": gen("Wooden Gutenberg-style printing press in a dim workshop, the lever pulled down hard, a freshly printed sheet lifted from the bed, dozens of printed sheets fanning outward and filling the air."),
 "G7a-bible": gen("An open German Bible on a plain wooden table, morning light from a small window, a wooden cup beside it."),
 "G7b-family": gen("A family of five at a farmhouse kitchen table, a father reading aloud from a small book, children listening, seen from the side with faces soft and in shadow, candle and hearth light."),
 "G7c-singing": gen("A congregation singing in a stone church, seen from behind, hymnals raised, candlelight, a high window glowing ahead of them."),
 "G7d-altar-cross": gen("A simple altar cross in a plain whitewashed church, daylight through a tall window behind it, empty wooden pews in the foreground."),
 "G8-parchment": gen("Slow drifting parchment texture filling the frame, faint handwritten Latin, very subtle, soft warm tone, suitable as a background for captions."),
}

def newest_image(cwd, since):
    enc = urllib.parse.quote(str(cwd), safe="")
    cands = [p for p in (SESSIONS / enc).rglob("images/*") if p.is_file() and p.stat().st_mtime >= since]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

def main():
    names = sys.argv[1:] or list(CLIPS)
    log = open(ROOT / "generate.log", "a")
    log.write(f"=== {time.ctime()} ===\n")
    for name in names:
        tool, prompt = CLIPS[name]
        d = ROOT / name; d.mkdir(exist_ok=True)
        t0 = time.time()
        print(f"--- {name} ({tool}) ---", flush=True); log.write(f"--- {name} ({tool}) ---\n")
        r = subprocess.run([str(GROK), "-p", prompt, "--tools", tool, "--max-turns", "4", "--output-format", "plain"],
                           cwd=d, capture_output=True, text=True, timeout=600)
        log.write(r.stdout + r.stderr + "\n")
        src = newest_image(d, t0)
        if src:
            n = 1
            while (d / f"{name}-v{n}.jpg").exists(): n += 1
            dst = d / f"{name}-v{n}.jpg"; shutil.copy(src, dst)
            dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(dst)], capture_output=True, text=True).stdout.split()
            msg = f"saved {dst.name} {dims[-3]}x{dims[-1]} in {time.time()-t0:.0f}s"
        else:
            msg = f"NO IMAGE for {name}: {r.stdout.strip()[-300:]}"
        print(msg, flush=True); log.write(msg + "\n"); log.flush()
    print("done")

if __name__ == "__main__":
    main()
