# Production Kit — Shot List, Grok Briefs, ElevenLabs, Music/SFX, Edit Spec

## 1. Technical spec (lock this before anyone starts)

| Item | Setting |
|---|---|
| Frame | 2160 x 3840 (9:16 vertical), 4K |
| Frame rate | 30 fps (or 24 fps if you want a filmic look; pick one and keep every clip the same) |
| Length | 85–88 s. Hard cap 90 s or Facebook will not post it as a Reel |
| Audio | Stereo, 48 kHz. Loudness about -14 LUFS integrated, peaks under -1 dB |
| Captions | Burned in (most people watch muted). Also upload an SRT to YouTube |
| Safe zones | Keep text and faces inside the middle 80 %. Avoid the bottom 20 % (platform UI) and top 12 % |
| Fonts | One serif for captions and dates (Reformation feel), one clean sans for times/address |
| Color | Warm, slightly desaturated for history; natural, brighter for the Troy footage so "today" visibly feels like today |
| Export | H.264 or H.265, high bitrate (40–60 Mbps), MP4. One master; platforms re-encode anyway |

## 2. Shot list — what the pastor shoots on the phone (Mon/Tue)

Shoot everything **vertical** at 4K 30 fps. Lock exposure/focus by long-pressing. Use a tripod or lean the phone on a pew. Shoot 10–15 s of every clip; the editor only needs 2–4 s.

### On-camera segments (record 3 takes each, as separate clips)
1. **Pastor segment, 0:44–0:62** (about 18 s). Medium shot, waist up, altar soft behind, windows lighting the face from the side. Eyes to the lens. Speak slower than feels natural. Pause after "Am I enough?"
2. **Closing line, 0:78+** ("Come meet the Jesus Luther found. We'll save you a seat."). Same spot or standing at the open front door.
3. **Safety take of the full invitation** (0:62–0:78) on camera, in case the ElevenLabs voice feels wrong for the local invite. A real pastor inviting real people is often stronger than a narrator.

**Audio for on-camera:** a lav mic or a second phone recording Voice Memos in a shirt pocket, 6–8 inches from the mouth. Turn off the HVAC for the take. Clap once at the start so the editor can sync.

### Sanctuary B-roll
4. Altar with candles being lit (hand enters frame, lights candle, exits).
5. Pulpit with the Bible open; slow push in (walk slowly toward it, or pinch-zoom 0.5x to 1x).
6. A hymnal opened to "A Mighty Fortress Is Our God" (close-up of the page, finger tracing the line).
7. Pews from the back of the nave, low angle, sunlight through windows.
8. Baptismal font, cross, any stained glass with Luther's rose or a Reformation theme.
9. Front doors opening from the inside, light pouring in (the "door" rhyme with Wittenberg).

### Around Troy, Illinois
10. Church exterior on N. Border St.: steeple from the street, the church sign, the main entrance, and the St. Paul's Lutheran School sign next door (a 2-second school shot reads "families welcome").
11. Two or three "this is our town" shots: downtown Troy (Main/Market Street storefronts), the water tower, Tri-Township Park, a harvested cornfield or fall trees on the edge of town, the I-55/I-70 overpass at dusk if you want a "Metro East" feel. Early morning or late afternoon light.
11b. Optional: a slow drive-by of the church from a passenger seat (phone braced on the window frame), 10 s, for the invitation section.
12. Basement classroom: coffee pouring, chairs set in a circle, a Bible and a notepad on the table, a welcome sign.
13. People, if available and willing: a greeter at the door, two people talking over coffee, a family in a pew. Smiles, no staged waving.

### Stills to pull from your Pictures folder
14. Wittenberg Castle Church door (the Theses door). Highest resolution you have.
15. Wittenberg town square, St. Mary's (Town Church), Luther statue, Lutherhaus — any 3–5 for the montage.

## 3. Grok compositing briefs

**How these get made on the Mac:** the Grok CLI (`~/.grok/bin/grok`, signed in) has Imagine tools built in. `python3 03-grok-clips/generate_stills.py` generates every still below (720x1280 each; the tool has no size option) into `03-grok-clips/<clip>/`. For motion, `reference_to_video` makes 1–15 s clips at 720p/24 fps with its own sound, pinned to a first and last frame — used for G2 (strike) and G6 (press). Everything Grok makes is upscaled 3x to 2160x3840 in the edit with light grain; the painterly style hides the upscale. Your own photos are native 4K and need no upscale.

Give Grok (Imagine / video) one clip at a time. Every prompt starts with the same header so the clips match.

**Header for every prompt:**
> Vertical 9:16, 2160x3840, 30 fps, 6 seconds, cinematic, painterly early-16th-century Germany, muted earth tones with warm candlelight, film grain, no text, no modern objects, no readable faces (figures in shadow, hood, or from behind).

**Clip G1 — The road and the storm (0:00–0:03)**
Rain streaking across a black-to-dark-grey sky, a muddy dirt road between fields, a lone hooded figure walking away from camera, wind in the grass, distant lightning flickers on the horizon, slow handheld drift.

**Clip G2 — The strike (0:03–0:10)**
Same road, the figure in mid-frame, sky splits with a single massive lightning bolt striking a tree 20 feet away, blinding white flash, the figure thrown backward into the mud, smoke, rain continues. Slow motion on the fall.

**Clip G3 — The cell (0:10–0:19)**
Stone monastery cell, one candle on a wooden desk, a kneeling monk seen from behind, hands clasped around a worn leather Bible, breath visible, slow push-in toward the hands. Very dark, very still.

**Clip G4 — Light on the page (0:19–0:28)**
Extreme close-up of a hand-printed Latin Bible page turning, warm light growing from the top of the frame until the page glows, dust in the light, slow. Then tilt up from the page to a plain wooden cross on the stone wall above the desk, the same warm light catching it. (This lands on "God had already come down — in Jesus.")

**Clip G5 — The door (0:28–0:33)** — image-to-video from YOUR photo
Use `05-stills-wittenberg/THESES-DOOR_bronze_2010_IMG_0801.jpg` as the source (portrait, 1936x2592 — upscale ~1.5x for 4K vertical, or do this as a Ken Burns move in the editor instead of Grok). Prompt: slow tilt down from the crucifixion mosaic to the bronze door, then a gentle push-in, pre-dawn blue light, subtle drifting mist, no other change to the image. (Keep the real photo; do not let Grok redraw the door or the mosaic.)

**Clip G6 — The press (0:33–0:36)**
Wooden Gutenberg-style printing press, lever pulled down hard, a printed sheet lifted, then dozens of sheets fanning outward and filling the frame, rapid cuts feel.

**Clip G7 — Montage pieces (0:36–0:44), 1.5 s each**
a) An open German Bible on a plain wooden table, morning light.
b) A family of five at a farmhouse kitchen table, a father reading from a small book, children listening (faces soft, from the side).
c) A congregation singing, seen from behind, hymnals raised, candlelight.
d) A simple altar cross in a plain church, daylight through a window behind it, slow push-in. (Lands on "and met Jesus in it for themselves.")

**Clip G8 — Transition texture (used under captions)**
Slow drifting parchment texture with faint handwritten Latin, very subtle, for the Romans 1:17 and date captions.

Tips: ask for 2–3 variations of G2 (the strike) — it's the money shot. If Grok produces a visible face, regenerate; a modern-looking face on "Luther" reads as AI instantly. Lightning and rain can also be layered as overlays in the editor if Grok's weather looks off.

## 4. ElevenLabs voice-over

**On the Mac:** `python3 02-vo/render_vo.py` renders every narration segment in the pastor's own ElevenLabs voice clone (the podcast voice, `~/.elevenlabs.env`), one file per segment plus a -16 LUFS master, and runs the text through the shared `voice_processor` (so Wittenberg is read the German way). The two on-camera lines are rendered too, as stand-ins for the animatic only. First render (18 Oct 2026): 74 s of narration + 25 s of pastor lines — about 25 s over the cap at the clone's natural pace, so the trim guide in SCRIPT.md applies or the read must be quicker.

**Voice:** a warm, low, documentary narrator. Try a few of the stock "narration" voices and pick one that sounds like a person telling a story at a table, not a movie trailer. Avoid anything breathy or overly theatrical.

**Model/settings (starting point):** Multilingual v2 or v3. Stability 0.45–0.55, Similarity 0.75, Style 0.15–0.25, Speed 0.92–0.95 (slightly slower than default). Speaker boost on.

**Workflow:**
1. Paste `vo-only.txt` one segment at a time (it's split by blank lines). Generating segment by segment lets you re-roll a single line without re-timing everything.
2. Export each as WAV (or highest MP3), 48 kHz if offered.
3. Listen for: "theses" (THEE-seez), "Wittenberg" (WIT-en-berg is fine for an American audience), "Saint Anne" (two clear words). If a word is mangled, spell it phonetically in the text box, e.g. "THEE-seez".
4. The em dashes and ellipses in the text are intentional; they create the pauses. If the voice rushes "Not earned. Not bought. Given." make them three separate generations.
5. Keep the voice's raw files; the editor applies a light EQ and -16 LUFS normalization, nothing else.

**Which lines are NOT ElevenLabs:** the pastor segment (0:44–0:62) and the closing line are the pastor on camera. Optional: the invitation (0:62–0:78) also works better as the pastor's real voice over B-roll. Record both and decide in the edit.


**Voice levelling (19 Oct 2026, in `make_animatic.py`):** every narration segment is loudness-normalised to -17 LUFS; the on-camera clips get high-pass 90 Hz, light FFT noise reduction, -2 dB at 250 Hz, +3 dB at 3.2 kHz, 3:1 compression, then the same -17 LUFS, so the phone sound sits beside the close-miked narration. The final mix (voice + ducked organ) is mastered to -14 LUFS / -1.5 dBTP. First 4K master: `08-exports/reformation-2026-master-9x16-DRAFT-v11.mp4` passes `check-master.sh`.

## 5. Music and sound effects

**Music plan (18 Oct 2026):** Luther hymns on pipe organ. First choice: the church organist recorded on the phone — "A Mighty Fortress" straight, plus a quiet verse of "Out of the Depths" (Aus tiefer Not) or "Dear Christians, One and All, Rejoice" for the storm and the cell. Stand-in until then: `python3 06-music-sfx/hymn_midi.py --sf2 ~/Library/Audio/Sounds/Banks/GeneralUser-GS.sf2` renders the real tune through a sampled pipe organ (FluidSynth + GeneralUser GS, installed 18 Oct 2026); `organ_mighty_fortress.py` is the older pure-Python synth of the same — the public-domain four-part Ein feste Burg from the Mutopia Project — as a synthesized organ (soft flute under the storm, parts entering at Romans, 16' pedal from the door, mixture and swell under the invitation, final chord under the end card), and `make_animatic.py` ducks it under the voice. `gen_underscore.py` (ElevenLabs Music, chorale idiom, does not quote the tune) is the fallback. Cue map: silence and rain on the open; low pedal enters in the cell; warm resolution on Romans; the chorale enters clearly under the invitation and swells on the end card.

**Music plan (three moods, one track if possible):**
- 0:00–0:19: none, then a single low sustained note (cello/organ pedal) from 0:10.
- 0:19–0:44: warm resolution, slow build, strings or soft piano.
- 0:44–0:62: duck to -22 dB under the pastor.
- 0:62–0:88: "A Mighty Fortress Is Our God" (public-domain hymn, Luther 1529). Organ or piano. Rise to full on the end card, hold the last chord, fade over 2 s.

**Where to get it legally:**
- Best: record your own organist or pianist playing "A Mighty Fortress" on the church instrument, 60–90 s, phone on the bench. Free, local, authentic, and no copyright claim.
- Otherwise: a licensed library (Epidemic Sound, Artlist, Musicbed) or YouTube Audio Library (free, check "attribution not required"). Search "cinematic hymn organ" or "reverent strings build."
- Do not use a commercial recording of the hymn; the tune is public domain but the recording is not, and Facebook/YouTube will mute or claim it.

**Levels:** music sits at about -20 dB under narration, never fighting the voice. If you can hear the lyrics or hum the tune while the VO is talking, it's too loud.

**SFX cue sheet (free from Freesound, Pixabay, or the editor's library):**
| Time | SFX |
|---|---|
| 0:00 | Steady rain, distant thunder rolling |
| 0:05 | Lightning crack (hard, close), then 1 s of near-silence/ringing |
| 0:19–0:28 | Two or three page turns |
| 0:28–0:31 | Three hammer strikes on wood, spaced about 0.7 s apart |
| 0:33 | Printing press thump, paper rustle |
| 0:62 | Church bell, one or two strikes (record St. Paul's real bell if it has one) |
| 0:78 | Nothing but music |

## 6. Edit assembly notes

- Build on a 2160x3840, 30 fps timeline. Drop the VO first, then cut picture to the words. Never stretch the voice to fit a picture.
- Captions: full-sentence captions for the VO, big and centered in the middle-lower third. The three "callout" captions (date, Romans 1:17, service times) get a larger, slower treatment.
- Transition from history to today at 0:44: a hard cut from the warm painterly montage to the bright, real sanctuary. That contrast is the point. No dissolve.
- The end card must be readable in 2 seconds: church name, "Reformation Weekend," Sat 5 PM / Sun 9 AM / Bible class 10:30 AM, 112 N. Border St, Troy, IL 62294, saintpaulstroy.org. Hold 8 s minimum.
- Add the church logo small in a corner for the entire video (inside the safe zone).
- Export two files: `reformation-2026-master-9x16.mp4` (full quality) and the same file trimmed to 60 s if the 60-s cut is needed for any other platform.
- Export a 1080x1920 version for the newsletter thumbnail/preview and a 1:1 still of the end card for the Facebook event.
