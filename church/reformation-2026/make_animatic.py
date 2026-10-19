#!/usr/bin/env python3
"""Animatic of "The Storm and the Door" — the pastor's own photos and footage only (no generated images),
and the ElevenLabs narration (02-vo/<segment>.mp3; falls back to macOS `say` if a file is missing).

Still placeholders: the pastor's on-camera segment and the Troy B-roll (red STAND-IN bands).
Music: 06-music-sfx/organ-underscore-v1.mp3 (ElevenLabs Music stand-in) ducked under the voice.

Usage:  python3 make_animatic.py            # 1080x1920 draft
        python3 make_animatic.py --4k       # 2160x3840
Output: 07-edit/animatic/animatic-v10.mp4 and animatic-v10-timing.txt
"""
import subprocess, sys, pathlib, textwrap, shutil
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

ROOT = pathlib.Path.home() / "Movies/Reformation-2026"
STILLS = ROOT / "05-stills-wittenberg"
GROK = ROOT / "03-grok-clips"
VO = ROOT / "02-vo"
WORK = ROOT / "07-edit/animatic"; WORK.mkdir(parents=True, exist_ok=True)
FOURK = "--4k" in sys.argv
W, H = (2160, 3840) if FOURK else (1080, 1920)
RW, RH = int(W * 1.5), int(H * 1.5)          # render frames larger, zoompan samples down
FPS = 30
VO_VOICE, PASTOR_VOICE = "Daniel", "Samantha"   # fallbacks only
F_SERIF = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
F_SANS = "/System/Library/Fonts/Helvetica.ttc"

def still(rel):
    rel = str(rel)
    if rel.startswith("/"): return pathlib.Path(rel)
    if rel.startswith("grok:"): return GROK / rel[5:]
    return STILLS / rel

# ---------------------------------------------------------------- segments
# Each: name, fallback voice, line, shots [(image|clip|None, caption, slate, darken, zoom)], pad seconds
S = [
 ("01-open", VO_VOICE, "A storm. A dirt road. A young law student, alone.",
  [("LUTHERSTEIN_Duebener-Heide_IMG_4706.jpg#center=0.35,0.6", "Is God for or\nagainst me?\n\n§The Lutherstein, Dübener Heide — on Luther's road from Erfurt", "", 0.45, "in")], 1.0),
 ("02-strike", VO_VOICE, "Lightning strikes so close it throws him to the ground. Martin Luther cries out: \"Saint Anne, help me! I will become a monk!\"",
  [("LUTHERSTEIN_Duebener-Heide_IMG_4706.jpg#center=0.62,0.35", "§July 1505 · the road near Erfurt", "", 0.55, "storm", 4.3),
   ("LUTHER_portrait_Cranach.jpg#center=0.5,0.42", "§Martin Luther · Lucas Cranach the Elder", "", 0.1, "in", 5.7)], 0.35),
 ("03-cell", VO_VOICE, "He kept that vow. Prayed, fasted, confessed for hours — and was still terrified. How could a sinner stand before a holy God?",
  [("ERFURT_Augustinian-monastery_cloister.jpg#center=0.5,0.5", "§The Augustinian monastery, Erfurt — where Luther became a monk", "", 0.25, "in", 1.1),
   ("ERFURT_Augustinian-monastery_altar.jpg#center=0.56,0.45", "§The altar where Luther lay prostrate before God", "", 0.15, "in", 1.0)], 0.35),
 ("04-romans", VO_VOICE, "Then he found it in Romans: \"The righteous shall live by faith.\" He'd been climbing toward God. God had already come down — in Jesus. Not earned. Not bought. Given.",
  [("LUTHERSTUBE_Luthers-study_Lutherhaus.jpg#center=0.82,0.5", "“The righteous shall live by faith.”\n— Romans 1:17\n\n§Luther's study, Wittenberg", "", 0.1, "in", 1.0),
   ("THESES-DOOR_bronze_2010_IMG_0801.jpg#mosaic", "", "", 0.0, "in", 1.0)], 0.35),
 ("05-door", VO_VOICE, "October 31, 1517. He nails ninety-five theses to a church door in Wittenberg. The printing press does the rest.",
  [("THESES-DOOR_bronze_2010_IMG_0801.jpg", "October 31, 1517", "", 0.05, "in", 3.3),
   ("LUTHERHAUS_Wittenberg_wide_with-Katharina-statue.jpg#pan=0.15,0.62", "", "", 0.0, "pan", 2.6),
   ("google-album-wittenberg-2010/036_IMG_0865.JPG#center=0.5,0.45", "", "", 0.0, "in", 1.7),
   ("google-album-wittenberg-2010/029_IMG_0853.JPG#center=0.55,0.4", "", "", 0.05, "out", 1.2),
   ("STADTKIRCHE_Wittenberg_towers_IMG_0299.jpg#center=0.5,0.4", "", "", 0.0, "in", 1.4)], 0.3),
 ("07-pastor", PASTOR_VOICE, "Five hundred years later, the question is the same: Am I enough? The honest answer is no — but Jesus is. You are forgiven, and you are free to love your neighbor.",
  [("/Users/abc3/Movies/Reformation-2026/04-broll/pastor-on-camera/pastor-take2.mp4", "Pastor Albert Collver · Saint Paul's Lutheran, Troy, IL", "", 0, "live")], 0),
 ("08-invite", VO_VOICE, "Join us at Saint Paul's Lutheran in Troy — Saturday at 5, Sunday at 9, Bible class at 10:30. Everyone is welcome.",
  [("/Users/abc3/Movies/Reformation-2026/04-broll/troy-church/IMG_4628.HEIC#center=0.27,0.45", "Saturday 5 PM\nSunday 9 AM\nBible Class 10:30 AM", "", 0.45, "in")], 0.3),
 ("09-end", PASTOR_VOICE, "Come meet the Jesus Luther found. We'll save you a seat.",
  [("/Users/abc3/Movies/Reformation-2026/04-broll/pastor-on-camera/pastor-closing.mp4", "", "", 0, "live"),
   ("/Users/abc3/Movies/Reformation-2026/04-broll/troy-church/IMG_0599.DNG", "Saint Paul's Lutheran Church\nREFORMATION WEEKEND\n\nSaturday 5 PM · Sunday 9 AM\nBible Class 10:30 AM\n\n112 N. Border St, Troy, IL\nsaintpaulstroy.org", "", 0.5, "in")], 5.2),
]

# ---------------------------------------------------------------- helpers
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode: raise SystemExit(f"FAILED: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r

def dur(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout.strip())

def load_cover(rel):
    """Open a still, crop to 9:16 cover at RWxRH (upscales small Grok frames). '#mosaic' = top of the door photo."""
    name, _, mode = rel.partition("#")
    centre = (0.5, 0.45)
    if mode.startswith("center="):
        centre = tuple(float(v) for v in mode[7:].split(",")); mode = ""
    p = still(name)
    if p.suffix.lower() in (".heic", ".dng") or not p.exists():
        jpg = WORK / (p.stem + ".jpg")
        if not jpg.exists():
            src = p if p.exists() else p.with_suffix(".HEIC")
            run(["sips", "-s", "format", "jpeg", str(src), "--out", str(jpg)])
        p = jpg
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    if mode == "mosaic":
        im = im.crop((0, 0, im.width, int(im.height * 0.42)))
    return ImageOps.fit(im, (RW, RH), Image.LANCZOS, centering=centre)

def font(path, size, index=0):
    try: return ImageFont.truetype(path, size, index=index)
    except Exception: return ImageFont.load_default()

def draw_center(d, text, f, y, fill, shadow=True, line_gap=1.25):
    lh = f.size * line_gap
    for i, line in enumerate(text.split("\n")):
        if not line: continue
        bb = d.textbbox((0, 0), line, font=f)
        x = (RW - (bb[2] - bb[0])) / 2; yy = y + i * lh
        if shadow: d.text((x + 4, yy + 4), line, font=f, fill=(0, 0, 0))
        d.text((x, yy), line, font=f, fill=fill)

def render_frame(image_rel, caption, slate, darken):
    if image_rel:
        im = load_cover(image_rel)
        if darken: im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), darken)
    else:
        im = Image.new("RGB", (RW, RH), (8, 8, 10))
    d = ImageDraw.Draw(im, "RGBA")
    if caption:
        big = "\n" in caption and len(caption) > 60          # end card
        title = caption.startswith("Is God")
        f = font(F_SERIF, int(RW * (0.052 if big else 0.078 if title else 0.062)))
        fs = font(F_SERIF, int(f.size * 0.5))
        lines = [textwrap.fill(l, 28) if (l and not l.startswith("§")) else ("§" + textwrap.fill(l[1:], 40) if l else l) for l in caption.split("\n")]
        n = sum(1 for l in lines if not l.startswith("§")) + sum(0.6 for l in lines if l.startswith("§"))
        y = RH * 0.42 - n * f.size * 1.25 / 2 if (image_rel is None or big or title) else RH * 0.70
        if all(l.startswith("§") or not l for l in lines): y = RH * 0.80
        for l in lines:
            if l.startswith("§"):
                draw_center(d, l[1:], fs, y, (230, 220, 200)); y += fs.size * 1.4 * (l.count("\n") + 1)
            else:
                draw_center(d, l, f, y, (245, 238, 220)); y += f.size * 1.25 * (l.count("\n") + 1)
    if slate:
        f = font(F_SANS, int(RW * 0.030), 0)
        wrapped = textwrap.fill("STAND-IN · " + slate, 46)
        n = wrapped.count("\n") + 1
        band_h = int(n * f.size * 1.3 + RW * 0.04)
        d.rectangle((0, RH * 0.08, RW, RH * 0.08 + band_h), fill=(120, 20, 20, 170))
        draw_center(d, wrapped, f, RH * 0.08 + RW * 0.02, (255, 230, 200), shadow=False, line_gap=1.3)
    return im

ENC = ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"]

def shot_clip(frame_png, seconds, zoom, out):
    frames = max(1, int(round(seconds * FPS)))
    z = {"in": "'min(1+0.0010*on,1.18)'", "out": "'max(1.18-0.0010*on,1.0)'"}.get(zoom, "'1.001'")
    vf = f"zoompan=z={z}:d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}"
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(frame_png),
         "-vf", vf, "-frames:v", str(frames), *ENC, str(out)])

def video_clip(src, seconds, out, caption=None, keep_audio=False, grain=True):
    """A clip: Grok 720p video (upscaled with grain) or real footage (scaled to fit). Optional lower-third caption 1–6 s."""
    vf = f"scale={W}:{H}:flags=lanczos" + (",unsharp=5:5:0.3,noise=alls=5:allf=t" if grain else "") + f",tpad=stop_mode=clone:stop_duration=60,fps={FPS}"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
    if caption:
        png = out.with_suffix(".lower3.png")
        im = Image.new("RGBA", (RW, RH), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        f = font(F_SERIF, int(RW * 0.040)); fs = font(F_SERIF, int(RW * 0.030))
        name, _, rest = caption.partition(" · ")
        d.rectangle((0, RH * 0.80, RW, RH * 0.80 + f.size * 3.2), fill=(0, 0, 0, 120))
        draw_center(d, name, f, RH * 0.80 + f.size * 0.4, (245, 238, 220)); draw_center(d, rest, fs, RH * 0.80 + f.size * 1.9, (230, 220, 200))
        im.save(png)
        cmd += ["-i", str(png), "-filter_complex", f"[0:v]{vf}[v0];[1:v]scale={W}:{H}[c];[v0][c]overlay=0:0:enable='between(t,1,6)'[v]", "-map", "[v]"]
        if keep_audio: cmd += ["-map", "0:a"]
    else:
        cmd += ["-vf", vf]
        if not keep_audio: cmd += ["-an"]
    cmd += ["-t", f"{seconds:.3f}", *ENC]
    if keep_audio: cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    run(cmd + [str(out)])

def concat(files, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])

# ---------------------------------------------------------------- build
timing, seg_files, t = [], [], 0.0
for name, voice, line, shots, pad in S:
    seg = WORK / name; seg.mkdir(exist_ok=True)
    real = VO / f"{name}.mp3"
    live = [sh for sh in shots if sh[4] == "live"]
    if live:
        src = still(live[0][0]); audio = seg / "live.wav"; source = "on camera"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "2", "-ar", "48000",
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(audio)])
    elif real.exists():
        audio = real; source = "ElevenLabs"
    else:
        audio = seg / "vo.aiff"; source = f"say/{voice}"
        run(["say", "-v", voice, "-r", "178", "-o", str(audio), line])
    vo = dur(audio)
    lead = 0.0 if live else 1.2 if name == "01-open" else 0.2
    total = vo + pad if live else lead + vo + pad
    weights = [sh[5] if len(sh) > 5 else 1.0 for sh in shots]
    clips = []
    for i, sh in enumerate(shots):
        img, cap, slate, dark, zoom = sh[:5]
        if live:
            others = sum(w for sh2, w in zip(shots, weights) if sh2[4] != "live") or 1.0
            share = vo if zoom == "live" else pad * weights[i] / others
        else:
            share = total * weights[i] / sum(weights)
        mp4 = seg / f"shot{i}.mp4"
        if zoom == "clip":
            video_clip(still(img), share, mp4)
        elif zoom == "live":
            video_clip(still(img), share, mp4, caption=cap, keep_audio=False, grain=False)
        elif zoom == "pan":
            name, _, spec = img.partition("#"); a, b = (float(v) for v in spec[4:].split(",")) if spec.startswith("pan=") else (0.0, 1.0)
            src = still(name); frames = max(1, int(round(share * FPS)))
            if src.suffix.lower() in (".heic", ".dng"):
                jpg = WORK / (src.stem + ".jpg"); jpg.exists() or run(["sips", "-s", "format", "jpeg", str(src), "--out", str(jpg)]); src = jpg
            vf = (f"scale=-2:{H},crop={W}:{H}:x='(iw-ow)*({a}+({b}-{a})*min(n/{frames},1))':y=0,fps={FPS}")
            run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(src), "-vf", vf, "-frames:v", str(frames), *ENC, str(mp4)])
        elif zoom == "storm":
            png = seg / f"shot{i}.png"
            fr = render_frame(img, cap, slate, dark)
            fr = ImageEnhance.Color(fr).enhance(0.35)
            fr = Image.blend(fr, Image.new("RGB", fr.size, (18, 28, 55)), 0.30)
            fr.save(png)
            raw = seg / f"shot{i}-raw.mp4"; shot_clip(png, share, "in", raw)
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-f", "lavfi", "-i", f"color=white:s={W}x{H}:r={FPS}",
                 "-filter_complex", "[0:v]format=gbrp[a];[1:v]format=gbrp[w];[a][w]blend=all_mode=screen:all_opacity=0.9:enable='between(t,0.80,0.90)+between(t,0.97,1.03)+between(t,1.20,1.24)+between(t,3.9,3.96)',format=yuv420p[v]",
                 "-map", "[v]", "-t", f"{share:.3f}", *ENC, str(mp4)])
        else:
            png = seg / f"shot{i}.png"
            render_frame(img, cap, slate, dark).save(png)
            shot_clip(png, share, zoom, mp4)
        clips.append(mp4)
    vid = seg / "video.mp4"
    concat(clips, vid) if len(clips) > 1 else shutil.copy(clips[0], vid)
    out = seg / "segment.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid), "-i", str(audio),
         "-filter_complex",
         f"[1:a]adelay={int(lead*1000)}|{int(lead*1000)},apad,atrim=0:{total:.3f}[a];"
         f"[0:v]fade=t=in:st=0:d=0.5,fade=t=out:st={total-0.4:.3f}:d=0.4,trim=0:{total:.3f}[v]",
         "-map", "[v]", "-map", "[a]", *ENC, "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", str(out)])
    timing.append((name, t, total, vo, source)); t += total; seg_files.append(out)

MUSIC = ROOT / "06-music-sfx/organ-mighty-fortress-v2.mp3"   # FluidSynth + GeneralUser GS; organist recording replaces it
if not MUSIC.exists(): MUSIC = ROOT / "06-music-sfx/organ-mighty-fortress-v1.mp3"
if not MUSIC.exists(): MUSIC = ROOT / "06-music-sfx/organ-underscore-v1.mp3"
dry = WORK / "animatic-v10-nomusic.mp4"
concat(seg_files, dry)
final = WORK / ("animatic-v10-4k.mp4" if FOURK else "animatic-v10.mp4")
if MUSIC.exists():
    # music under the whole piece, ducked by the voice, faded out over the last 4 s
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(dry), "-i", str(MUSIC), "-filter_complex",
         f"[1:a]atrim=0:{t:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
         f"afade=t=in:st=0:d=3,afade=t=out:st={t-4:.3f}:d=4,volume=0.55[m];"
         f"[0:a]asplit[n][sc];[m][sc]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=700:makeup=1[md];"
         f"[n][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(final)])
    music_note = f"music: {MUSIC.name} (ducked under voice)"
else:
    shutil.copy(dry, final); music_note = "music: none"
report = [f"{'segment':12s} {'start':>7s} {'length':>7s} {'speech':>7s}  voice"]
report += [f"{n:12s} {s:7.1f} {d:7.1f} {v:7.1f}  {src}" for n, s, d, v, src in timing]
report += ["", f"TOTAL {t:.1f} s  (cap 90 s)   output: {final}  {W}x{H} @ {FPS} fps", music_note]
(WORK / "animatic-v10-timing.txt").write_text("\n".join(report) + "\n")
print("\n".join(report))
