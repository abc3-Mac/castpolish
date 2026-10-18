# Reformation 2026 Video — Saint Paul's Lutheran Church, Troy, Illinois

Saint Paul's Lutheran Church (LCMS) · 112 N. Border St., Troy, IL 62294 · saintpaulstroy.org · 618-667-6681 · Pastor: Rev. Dr. Albert B. Collver III · St. Paul's Lutheran School shares the campus.

Everything needed to produce a 90-second vertical 4K video, "The Storm and the Door," for Reformation Weekend, post it to YouTube and Facebook by Thursday, and link it in Friday's newsletter.

## Files

| File | What it is |
|---|---|
| `SCRIPT.md` | The script: timecoded VO, on-camera lines, visuals, SFX/music cues, 60-s trim guide, accuracy notes |
| `vo-only.txt` | Narration only, split by segment, ready to paste into ElevenLabs |
| `IDEAS-AND-ALT-OPENS.md` | Four alternate cold opens, hook captions, "why it matters today" angles, extra post ideas |
| `PRODUCTION-KIT.md` | Tech spec, phone shot list, Grok prompts, ElevenLabs settings, music/SFX plan, edit notes |
| `POST-COPY.md` | YouTube title/description, Facebook post, Friday newsletter blurb |
| `HANDOFF.md` | How to run this on the Mac, plus paste-ready prompts for Claude Code, ElevenLabs, Grok, and the editor |
| `setup-mac.sh` | Builds the project folder on the Mac, gathers Wittenberg photos, checks tools |
| `check-master.sh` | Verifies the final export: 9:16, 4K, under 90 s, loudness |

## Schedule (week of Oct 18, 2026)

| Day | Who | Task |
|---|---|---|
| Sun Oct 18 | Pastor | Read `SCRIPT.md`, choose cold open (default: thunderstorm), confirm service dates/times |
| Mon Oct 19 | Pastor | Shoot on-camera segment + sanctuary/Troy B-roll (see shot list). Record organist playing "A Mighty Fortress" if possible |
| Mon Oct 19 | Agent: VO | Generate ElevenLabs narration from `vo-only.txt` |
| Mon–Tue | Agent: Grok | Generate clips G1–G8 from `PRODUCTION-KIT.md` section 3 |
| Tue Oct 20 | Agent: Edit | Assemble timeline, captions, music, SFX. First cut to pastor by evening |
| Wed Oct 21 | Pastor + Edit | Notes, final cut, run `check-master.sh`, export |
| Thu Oct 22 | Agent: Post | Upload to YouTube and Facebook with `POST-COPY.md`; create Facebook event |
| Fri Oct 23 | Pastor | Paste the links into the newsletter blurb and send |
| Sat/Sun Oct 24–25 | Everyone | Reformation Weekend |

If Thursday slips, Friday morning upload still makes the newsletter.

## Decisions to make early
1. Thunderstorm open (default) or one of the alternates in `IDEAS-AND-ALT-OPENS.md`.
2. ElevenLabs narrator for the invitation, or the pastor's own voice over B-roll (record both, decide in edit).
3. Bible class topic for the newsletter and the Saturday post.
5. Whether to include a 2-second shot of St. Paul's Lutheran School (kids, playground, sign) in the Troy B-roll; it signals "families welcome" without a word of narration.
4. Music source: church organist recording (best) or a licensed library track.
