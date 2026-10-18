#!/usr/bin/env python3
"""Rough animatic of "The Storm and the Door" — stills + captions + macOS TTS.

Stand-in for timing and feel only. Grok clips, the pastor's on-camera segment,
Troy B-roll, music and SFX are all placeholders here.

Usage:  python3 make_animatic.py            # 1080x1920 draft
        python3 make_animatic.py --4k       # 2160x3840
Output: 07-edit/animatic/animatic-v1.mp4 and animatic-v1-timing.txt
"""
import subprocess, sys, pathlib, textwrap, shutil, json
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

ROOT = pathlib.Path.home() / "Movies/Reformation-2026"
STILLS = ROOT / "05-stills-wittenberg"
WORK = ROOT / "07-edit/animatic"; WORK.mkdir(parents=True, exist_ok=True)
FOURK = "--4k" in sys.argv
W, H = (2160, 3840) if FOURK else (1080, 1920)
RW, RH = int(W * 1.5), int(H * 1.5)          # render frames larger, zoompan samples down
FPS = 30
VO_VOICE, PASTOR_VOICE = "Daniel", "Samantha"
F_SERIF = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
F_SERIF_R = "/System/Library/Fonts/Supplemental/Georgia.ttf"
F_SANS = "/System/Library/Fonts/Helvetica.ttc"

def still(rel): return STILLS / rel

# ---------------------------------------------------------------- segments
# Each: name, voice, line, shots [(image or None, caption, slate, darken, zoom)], pad seconds
S = [
 ("01-open", VO_VOICE, "A storm. A dirt road. A young law student, alone.",
  [(None, "July 1505 · A road near Erfurt, Germany", "G1 (Grok): rain over a dark road — placeholder", 0, "in")], 1.0),
 ("02-strike", VO_VOICE, "Lightning strikes so close it throws him to the ground. Martin Luther cries out: \"Saint Anne, help me! I will become a monk!\"",
  [("door-candidates/IMG_4832.jpg", "", "G2 (Grok): the lightning strike — placeholder", 0.55, "in")], 0.35),
 ("03-cell", VO_VOICE, "He kept that vow. Prayed, fasted, confessed for hours — and was still terrified. How could a sinner stand before a holy God?",
  [("google-album-wittenberg-2010/033_IMG_0857.jpg", "", "G3 (Grok): the monastery cell — placeholder", 0.6, "in")], 0.35),
 ("04-romans", VO_VOICE, "Then he found it in Romans: \"The righteous shall live by faith.\" He'd been climbing toward God. God had already come down — in Jesus. Not earned. Not bought. Given.",
  [("THESES-DOOR_bronze_2010_IMG_0801.jpg#mosaic", "“The righteous shall live by faith.”\n— Romans 1:17", "G4 (Grok): light on the page, tilt up to the cross — placeholder", 0.15, "in")], 0.35),
 ("05-door", VO_VOICE, "October 31, 1517. He nails ninety-five theses to a church door in Wittenberg. The printing press does the rest.",
  [("THESES-DOOR_bronze_2010_IMG_0801.jpg", "October 31, 1517", "", 0.05, "in"),
   (None, "", "G6 (Grok): the printing press — placeholder", 0, "none")], 0.3),
 ("06-montage", VO_VOICE, "Soon ordinary people had a Bible in their own language — and met Jesus in it for themselves.",
  [("google-album-wittenberg-2010/002_IMG_0778.jpg", "", "", 0.1, "out"),
   ("google-album-wittenberg-2010/036_IMG_0865.jpg", "", "", 0.05, "in"),
   ("google-album-wittenberg-2010/029_IMG_0853.jpg", "", "", 0.05, "out"),
   ("google-album-wittenberg-2010/050_IMG_0893.jpg", "", "", 0.1, "in")], 0.3),
 ("07-pastor", PASTOR_VOICE, "Five hundred years later, the question hasn't changed: Am I enough? The honest answer is no — and that's the good news, because Jesus is. It was never about Luther. It's about Christ, for you. You are forgiven. You are free to love your neighbor.",
  [("google-album-wittenberg-2010/012_IMG_0804.jpg", "Pastor Albert Collver · Saint Paul's Lutheran, Troy, IL", "PASTOR ON CAMERA — record in the sanctuary, altar behind, eyes to lens (TTS stand-in)", 0.5, "none")], 0.35),
 ("08-invite", VO_VOICE, "Celebrate the Reformation at Saint Paul's Lutheran Church in Troy: Saturday at 5 PM or Sunday at 9 AM, Bible class at 10:30 in the church basement. Members, neighbors, the curious — all are welcome.",
  [(None, "Saturday 5 PM\nSunday 9 AM\nBible Class 10:30 AM", "Troy B-roll: steeple, sign, doors opening, candles, coffee, faces — placeholder", 0, "none")], 0.3),
 ("09-end", PASTOR_VOICE, "Come meet the Jesus Luther found. We'll save you a seat.",
  [(None, "Saint Paul's Lutheran Church\nREFORMATION WEEKEND\n\nSaturday 5 PM · Sunday 9 AM\nBible Class 10:30 AM\n\n112 N. Border St, Troy, IL\nsaintpaulstroy.org", "", 0, "none")], 6.0),
]

# ---------------------------------------------------------------- helpers
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode: raise SystemExit(f"FAILED: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r

def dur(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout.strip())

def load_cover(rel):
    """Open a still, crop to 9:16 cover at RWxRH. '#mosaic' = top 45% of the door photo."""
    name, _, mode = rel.partition("#")
    p = still(name)
    if p.suffix.lower() == ".heic" or not p.exists():
        jpg = WORK / (p.stem + ".jpg")
        if not jpg.exists():
            src = p if p.exists() else p.with_suffix(".HEIC")
            run(["sips", "-s", "format", "jpeg", str(src), "--out", str(jpg)])
        p = jpg
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    if mode == "mosaic":
        im = im.crop((0, 0, im.width, int(im.height * 0.42)))
    return ImageOps.fit(im, (RW, RH), Image.LANCZOS, centering=(0.5, 0.45))

def font(path, size, index=0):
    try: return ImageFont.truetype(path, size, index=index)
    except Exception: return ImageFont.load_default()

def draw_center(d, text, f, y, fill, shadow=True, line_gap=1.25):
    lines = text.split("\n")
    lh = f.size * line_gap
    for i, line in enumerate(lines):
        if not line: continue
        bb = d.textbbox((0, 0), line, font=f)
        x = (RW - (bb[2] - bb[0])) / 2
        yy = y + i * lh
        if shadow: d.text((x + 4, yy + 4), line, font=f, fill=(0, 0, 0))
        d.text((x, yy), line, font=f, fill=fill)
    return y + len(lines) * lh

def render_frame(image_rel, caption, slate, darken):
    if image_rel:
        im = load_cover(image_rel)
        if darken:
            im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), darken)
    else:
        im = Image.new("RGB", (RW, RH), (8, 8, 10))
    d = ImageDraw.Draw(im, "RGBA")
    if caption:
        big = "\n" in caption and len(caption) > 60          # end card
        f = font(F_SERIF, int(RW * (0.052 if big else 0.062)))
        wrapped = "\n".join(textwrap.fill(l, 28) if l else "" for l in caption.split("\n"))
        n = wrapped.count("\n") + 1
        y = RH * 0.42 - n * f.size * 1.25 / 2 if (image_rel is None or big) else RH * 0.70
        draw_center(d, wrapped, f, y, (245, 238, 220))
    if slate:
        f = font(F_SANS, int(RW * 0.030), 0)
        wrapped = textwrap.fill("STAND-IN · " + slate, 46)
        n = wrapped.count("\n") + 1
        band_h = int(n * f.size * 1.3 + RW * 0.04)
        d.rectangle((0, RH * 0.08, RW, RH * 0.08 + band_h), fill=(120, 20, 20, 170))
        draw_center(d, wrapped, f, RH * 0.08 + RW * 0.02, (255, 230, 200), shadow=False, line_gap=1.3)
    return im

def shot_clip(frame_png, seconds, zoom, out):
    frames = max(1, int(round(seconds * FPS)))
    if zoom == "in":
        z = f"'min(1+0.0010*on,1.18)'"
    elif zoom == "out":
        z = f"'max(1.18-0.0010*on,1.0)'"
    else:
        z = "'1.001'"
    vf = (f"zoompan=z={z}:d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
          f"format=yuv420p")
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(frame_png),
         "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out)])

def concat(files, out, extra=()):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", *extra, str(out)])

# ---------------------------------------------------------------- build
timing, seg_files, t = [], [], 0.0
for name, voice, line, shots, pad in S:
    seg = WORK / name; seg.mkdir(exist_ok=True)
    aiff = seg / "vo.aiff"
    run(["say", "-v", voice, "-r", "178", "-o", str(aiff), line])
    vo = dur(aiff)
    lead = 1.2 if name == "01-open" else 0.3
    total = lead + vo + pad
    # video: split total across shots (first shot gets any remainder)
    share = total / len(shots)
    clips = []
    for i, (img, cap, slate, dark, zoom) in enumerate(shots):
        png = seg / f"shot{i}.png"
        render_frame(img, cap, slate, dark).save(png)
        mp4 = seg / f"shot{i}.mp4"
        shot_clip(png, share, zoom, mp4); clips.append(mp4)
    vid = seg / "video.mp4"
    concat(clips, vid) if len(clips) > 1 else shutil.copy(clips[0], vid)
    # audio: lead-in silence + narration + pad; fade video in/out
    out = seg / "segment.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid), "-i", str(aiff),
         "-filter_complex",
         f"[1:a]adelay={int(lead*1000)}|{int(lead*1000)},apad,atrim=0:{total:.3f},volume=1.6[a];"
         f"[0:v]fade=t=in:st=0:d=0.5,fade=t=out:st={total-0.4:.3f}:d=0.4,trim=0:{total:.3f}[v]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", str(out)])
    timing.append((name, t, total, vo)); t += total; seg_files.append(out)

final = WORK / ("animatic-v1-4k.mp4" if FOURK else "animatic-v1.mp4")
concat(seg_files, final)
report = [f"{'segment':12s} {'start':>7s} {'length':>7s} {'speech':>7s}"]
report += [f"{n:12s} {s:7.1f} {d:7.1f} {v:7.1f}" for n, s, d, v in timing]
report += ["", f"TOTAL {t:.1f} s  (cap 90 s)   output: {final}  {W}x{H} @ {FPS} fps",
           f"voices: VO={VO_VOICE}, pastor stand-in={PASTOR_VOICE} (macOS say, 178 wpm)"]
(WORK / "animatic-v1-timing.txt").write_text("\n".join(report) + "\n")
print("\n".join(report))
