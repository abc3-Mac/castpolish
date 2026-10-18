# Hand-off: Building This on the Mac

This package was written in a cloud session on the `claude/optimistic-einstein-8a79a2` branch of the castpolish repo. Nothing has touched your Mac yet. Here's how to bring it over and run the production there.

## Step 1 — Get the files onto the Mac (2 minutes)

Open Terminal on the Mac:

```bash
cd ~/path/to/castpolish            # wherever your local clone lives
git fetch origin claude/optimistic-einstein-8a79a2
git checkout claude/optimistic-einstein-8a79a2
bash church/reformation-2026/setup-mac.sh
```

`setup-mac.sh` will:
- create `~/Movies/Reformation-2026/` with folders for `01-script`, `02-vo`, `03-grok-clips`, `04-broll`, `05-stills-wittenberg`, `06-music-sfx`, `07-edit`, `08-exports`, `09-post-copy`
- copy the script, VO text, and post copy into it
- search `~/Pictures` (loose files only, not the Photos library) for anything with "witten", "luther", or "wittenberg" in the filename and copy it to `05-stills-wittenberg`
- check for Homebrew, ffmpeg, and ffprobe and tell you the install command if they're missing

If your Wittenberg photos are inside the Photos app rather than loose files, select them in Photos and **File → Export → Export Unmodified Original** into `05-stills-wittenberg`.

## Step 2 — Open Claude Code on the Mac and paste this

```
I'm producing a 90-second vertical 4K Reformation video for Saint Paul's Lutheran Church in Troy.
The full package is in ~/Movies/Reformation-2026/ (also in this repo under church/reformation-2026/).
Read 01-script/SCRIPT.md and 01-script/PRODUCTION-KIT.md first.

Act as the production coordinator. Do these in order and report after each:
1. Confirm the folder structure exists and list what's in 05-stills-wittenberg and 04-broll.
2. From 01-script/vo-only.txt, prepare the ElevenLabs job: one text block per segment,
   with the voice settings from PRODUCTION-KIT.md section 4. If the ElevenLabs CLI or API key
   is available on this machine, generate the segments into 02-vo/ as WAV; otherwise give me
   the exact text blocks to paste into the ElevenLabs web app.
3. Write the eight Grok prompts from PRODUCTION-KIT.md section 3 into 03-grok-clips/PROMPTS.txt,
   one per file-name (G1-storm-road.mp4, G2-strike.mp4, ...), so I can paste them into Grok and
   save the results with those names.
4. Once 02-vo, 03-grok-clips, 04-broll, and 05-stills-wittenberg have files, build an edit
   checklist in 07-edit/EDIT-PLAN.md that maps each timecode in SCRIPT.md to a specific file.
5. When I export 08-exports/reformation-2026-master-9x16.mp4, run
   church/reformation-2026/check-master.sh on it and tell me what to fix.
6. Fill in POST-COPY.md with the final address, website, Bible class topic, and links I give you,
   and save the finished versions to 09-post-copy/.
Do not change the script wording without asking; the pastor approved it.
```

## Step 3 — What the pastor does personally
- Shoot the on-camera segment and the B-roll (shot list in PRODUCTION-KIT.md section 2). AirDrop the clips into `04-broll/`.
- Export the Wittenberg photos into `05-stills-wittenberg/`.
- Optional but recommended: record the organist playing "A Mighty Fortress" (60–90 s) into `06-music-sfx/`.

## Step 4 — Prompts for the other agents (copy/paste)

### ElevenLabs agent
```
Generate narration for a church history video. Voice: warm, low, documentary narrator, unhurried,
not theatrical. Model: Multilingual v2 (or v3). Stability 0.5, Similarity 0.75, Style 0.2, Speed 0.93.
Generate each paragraph below as a separate file, named vo-01.wav through vo-07.wav, 48 kHz.
Pronounce "theses" as THEE-seez. Honor the dashes and periods as pauses.
[paste the contents of vo-only.txt]
```

### Grok agent
```
Generate vertical 9:16 video clips (2160x3840, 30 fps, 6 s each) for a cinematic short about
Martin Luther. Use the header and the eight prompts in 03-grok-clips/PROMPTS.txt exactly.
For G5, use the attached Wittenberg door photo as the source image and only add a slow push-in
and mist; do not redraw the door. Produce three variations of G2 (the lightning strike).
Regenerate any clip that shows a clear modern-looking face. Name files G1..G8 as listed.
```

### Editor agent (CapCut, DaVinci Resolve, Final Cut, or Premiere)
```
Assemble ~/Movies/Reformation-2026 into a 2160x3840 30 fps timeline following 07-edit/EDIT-PLAN.md
and the timecodes in SCRIPT.md. Lay the VO first, cut picture to the words. Burned-in captions
in the middle-lower third inside the 80% safe zone. Music ducks to -22 dB under speech,
"A Mighty Fortress" rises on the end card. Hard cut (no dissolve) at 0:44 from history to the
real sanctuary. End card holds 8 s. Total length 85–88 s, never over 90. Export H.264 MP4,
50 Mbps, 48 kHz stereo, -14 LUFS, to 08-exports/reformation-2026-master-9x16.mp4,
plus a 1080x1920 preview and a 1:1 PNG of the end card.
```

### Posting agent
```
Upload 08-exports/reformation-2026-master-9x16.mp4 to the church YouTube channel and Facebook page
using the finished copy in 09-post-copy/. YouTube: vertical upload, add the SRT, thumbnail = end
card. Facebook: post as a Reel, create a Facebook Event for Reformation Weekend using the 1:1
end-card image, share the Reel into the event, pin the post. Send me both public links for the
Friday newsletter.
```

## Step 5 — Friday
Paste the YouTube and Facebook links into the newsletter blurb from `POST-COPY.md` and send.
