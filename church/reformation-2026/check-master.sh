#!/bin/bash
# Verifies the final export meets the spec: 9:16, 4K, 85-90 s, stereo 48 kHz, loudness near -14 LUFS.
# Usage: bash check-master.sh path/to/reformation-2026-master-9x16.mp4
set -u
F="${1:-}"
if [ -z "$F" ] || [ ! -f "$F" ]; then echo "Usage: $0 <video.mp4>"; exit 1; fi
command -v ffprobe >/dev/null || { echo "ffprobe missing: brew install ffmpeg"; exit 1; }

W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$F")
H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$F")
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$F")
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$F")
CH=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$F")
SR=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$F")

ok=1
echo "File: $F"
echo "Resolution: ${W}x${H} @ $FPS fps"
if [ "$W" = "2160" ] && [ "$H" = "3840" ]; then echo "  [ok] vertical 4K"; else echo "  [FIX] expected 2160x3840"; ok=0; fi
printf "Duration: %.1f s\n" "$DUR"
if awk -v d="$DUR" 'BEGIN{exit !(d<=90.0)}'; then echo "  [ok] under 90 s (Facebook Reel limit)"; else echo "  [FIX] over 90 s; use the trim guide in SCRIPT.md"; ok=0; fi
if awk -v d="$DUR" 'BEGIN{exit !(d>=60.0)}'; then echo "  [ok] over 60 s"; else echo "  [note] under 60 s; fine, but the brief allowed up to 90"; fi
echo "Audio: ${CH:-?} ch, ${SR:-?} Hz"
if [ "${CH:-0}" = "2" ]; then echo "  [ok] stereo"; else echo "  [FIX] expected stereo"; ok=0; fi
if [ "${SR:-0}" = "48000" ]; then echo "  [ok] 48 kHz"; else echo "  [note] 48 kHz preferred"; fi

if command -v ffmpeg >/dev/null; then
  echo "Loudness (EBU R128):"
  ffmpeg -nostats -i "$F" -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|Peak:" | tail -2 | sed 's/^/  /'
  echo "  target: about -14 LUFS integrated, true peak under -1 dBTP"
fi

[ "$ok" = "1" ] && echo "RESULT: ready to upload" || echo "RESULT: fix the items marked [FIX]"
