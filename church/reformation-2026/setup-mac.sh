#!/bin/bash
# Sets up the Reformation 2026 video project folder on the Mac.
# Usage: bash church/reformation-2026/setup-mac.sh [destination]
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/Movies/Reformation-2026}"

echo "Project folder: $DEST"
for d in 01-script 02-vo 03-grok-clips 04-broll 05-stills-wittenberg 06-music-sfx 07-edit 08-exports 09-post-copy; do
  mkdir -p "$DEST/$d"
done

cp "$SRC/SCRIPT.md" "$SRC/PRODUCTION-KIT.md" "$SRC/IDEAS-AND-ALT-OPENS.md" "$SRC/README.md" "$SRC/HANDOFF.md" "$DEST/01-script/"
cp "$SRC/vo-only.txt" "$DEST/01-script/"
cp "$SRC/vo-only.txt" "$DEST/02-vo/"
cp "$SRC/POST-COPY.md" "$DEST/09-post-copy/"
cp "$SRC/check-master.sh" "$DEST/08-exports/"
cp "$SRC/make_animatic.py" "$DEST/07-edit/"
cp "$SRC/generate_stills.py" "$DEST/03-grok-clips/"
cp "$SRC/render_vo.py" "$DEST/02-vo/"
chmod +x "$DEST/08-exports/check-master.sh"

# Grok prompts as a standalone file the Grok agent can read
awk '/^## 3\. Grok compositing briefs/,/^## 4\. ElevenLabs/' "$SRC/PRODUCTION-KIT.md" | sed '$d' > "$DEST/03-grok-clips/PROMPTS.txt"

echo
echo "Looking for Wittenberg photos in ~/Pictures (loose files only)..."
found=0
while IFS= read -r -d '' f; do
  cp -n "$f" "$DEST/05-stills-wittenberg/" && found=$((found+1))
done < <(find "$HOME/Pictures" -type f \( -iname '*witten*' -o -iname '*luther*' \) \
          \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.heic' -o -iname '*.tif' -o -iname '*.tiff' \) \
          -not -path '*.photoslibrary*' -print0 2>/dev/null)
if [ "$found" -eq 0 ]; then
  echo "  None found by filename. If they live in the Photos app: select them, File > Export >"
  echo "  Export Unmodified Original, into $DEST/05-stills-wittenberg/"
else
  echo "  Copied $found photo(s) into 05-stills-wittenberg/"
fi

echo
echo "Checking tools..."
if command -v brew >/dev/null 2>&1; then echo "  Homebrew: ok"; else echo "  Homebrew: missing  ->  https://brew.sh"; fi
if command -v ffmpeg >/dev/null 2>&1; then echo "  ffmpeg: ok"; else echo "  ffmpeg: missing  ->  brew install ffmpeg"; fi
if command -v ffprobe >/dev/null 2>&1; then echo "  ffprobe: ok"; else echo "  ffprobe: missing  ->  brew install ffmpeg"; fi

echo
echo "Done. Next: AirDrop phone footage into $DEST/04-broll/ and open HANDOFF.md in 01-script/."
open "$DEST" 2>/dev/null || true
