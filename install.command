#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  CastPolish installer / updater
#  Double-click this file in Finder (or run in Terminal) on macOS.
#  Safe to run on a fresh machine OR to update an existing install.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"
CYAN="\033[0;36m";  BOLD="\033[1m";      RESET="\033[0m"

ok()   { echo -e "${GREEN}  ✓  $*${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
err()  { echo -e "${RED}  ✗  $*${RESET}"; }
info() { echo -e "${CYAN}  →  $*${RESET}"; }
hdr()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── Change to the directory this script lives in ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Keep Terminal window open when double-clicked from Finder ─────────────────
if [ -t 0 ]; then : ; else
  osascript -e "tell application \"Terminal\" to do script \"bash '$0'\"" 2>/dev/null || true
  exit 0
fi

clear
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   CastPolish  —  Install / Update    ║"
echo -e "  ╚══════════════════════════════════════╝${RESET}"
echo ""

# ── Helper: yes/no prompt ─────────────────────────────────────────────────────
ask() {
  # ask "Question text" → returns 0 for yes, 1 for no
  # Uses regex instead of ${,,} — compatible with macOS bash 3.2
  local prompt="${1} [y/N]: "
  read -r -p "$(echo -e "${YELLOW}  ?  ${prompt}${RESET}")" ans
  [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 1 / 7 — Homebrew"
# ─────────────────────────────────────────────────────────────────────────────
if command -v brew &>/dev/null; then
  ok "Homebrew already installed ($(brew --version | head -1))"
else
  info "Installing Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add Homebrew to PATH for the rest of this script
  if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -f /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  ok "Homebrew installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 2 / 7 — ffmpeg"
# ─────────────────────────────────────────────────────────────────────────────
if command -v ffmpeg &>/dev/null; then
  ok "ffmpeg already installed ($(ffmpeg -version 2>&1 | head -1 | awk '{print $3}'))"
else
  info "Installing ffmpeg via Homebrew…"
  brew install ffmpeg
  ok "ffmpeg installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 3 / 7 — Python 3.10+"
# ─────────────────────────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" &>/dev/null; then
    _ver="$($candidate -c 'import sys; print(sys.version_info[:2])')"
    _maj="$($candidate -c 'import sys; print(sys.version_info[0])')"
    _min="$($candidate -c 'import sys; print(sys.version_info[1])')"
    if [ "$_maj" -ge 3 ] && [ "$_min" -ge 10 ]; then
      PYTHON="$(command -v $candidate)"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  info "Python 3.10+ not found — installing via Homebrew…"
  brew install python@3.12
  PYTHON="$(brew --prefix)/bin/python3.12"
  ok "Python installed: $PYTHON"
else
  ok "Python found: $PYTHON ($($PYTHON --version))"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 4 / 7 — CastPolish source"
# ─────────────────────────────────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/castpolish.py" ]; then
  ok "castpolish.py present — pulling latest from GitHub…"
  if git -C "$SCRIPT_DIR" pull --ff-only 2>/dev/null; then
    ok "Updated to latest."
  else
    warn "git pull skipped (local changes or not a git repo — files left as-is)."
  fi
else
  INSTALL_DIR="$HOME/Documents/castpolish"
  info "Cloning castpolish to $INSTALL_DIR …"
  git clone https://github.com/abc3-Mac/castpolish "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  SCRIPT_DIR="$INSTALL_DIR"
  ok "Cloned."
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 5 / 7 — Core Python packages"
# ─────────────────────────────────────────────────────────────────────────────
CORE_PKGS=(flask flask-cors pyloudnorm soundfile noisereduce numpy)

info "Installing / upgrading: ${CORE_PKGS[*]}"
"$PYTHON" -m pip install --upgrade "${CORE_PKGS[@]}"
ok "Core packages ready."

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 6 / 7 — Optional packages"
# ─────────────────────────────────────────────────────────────────────────────

# ── Whisper transcription ────────────────────────────────────────────────────
echo ""
info "faster-whisper enables AI transcription (recommended, ~200 MB models)."
if ask "Install / upgrade faster-whisper?"; then
  "$PYTHON" -m pip install --upgrade faster-whisper
  ok "faster-whisper installed."
else
  warn "Skipped faster-whisper."
fi

# ── Ollama (local LLM for shownotes) ────────────────────────────────────────
echo ""
info "Ollama enables AI shownotes generation via a local LLM."
if ask "Install Ollama + pull llama3.2 model?"; then
  if command -v ollama &>/dev/null; then
    ok "Ollama already installed."
  else
    brew install ollama
    ok "Ollama installed."
  fi
  info "Pulling llama3.2 model (~2 GB — this may take a few minutes)…"
  ollama pull llama3.2
  ok "llama3.2 model ready."
else
  warn "Skipped Ollama."
fi

# ── pyannote.audio (speaker diarization) ────────────────────────────────────
echo ""
info "pyannote.audio enables speaker diarization (who said what)."
warn "Requires a free HuggingFace token from https://hf.co/pyannote/speaker-diarization-3.1"
if ask "Install pyannote.audio + torch (large download ~2 GB)?"; then
  "$PYTHON" -m pip install --upgrade pyannote.audio
  ok "pyannote.audio installed. Run: python castpolish.py setup  to add your HF token."
else
  warn "Skipped pyannote.audio."
fi

# ── DeepFilterNet (AI noise reduction) ──────────────────────────────────────
echo ""
info "DeepFilterNet is an AI noise reduction model (highest quality)."
warn "Requires Rust compiler (~600 MB) and takes 5–15 min to compile on first install."
if ask "Install DeepFilterNet in an isolated virtual environment?"; then
  # Ensure Rust is available
  if ! command -v cargo &>/dev/null; then
    # Load from cargo env if partially installed
    if [ -f "$HOME/.cargo/env" ]; then
      # shellcheck source=/dev/null
      source "$HOME/.cargo/env"
    fi
  fi
  if ! command -v cargo &>/dev/null; then
    info "Installing Rust via rustup…"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
    ok "Rust installed."
  else
    ok "Rust already installed ($(cargo --version))"
  fi

  DF_VENV="$HOME/.castpolish/df_venv"
  info "Creating isolated venv at $DF_VENV …"
  "$PYTHON" -m venv --clear "$DF_VENV"
  "$DF_VENV/bin/pip" install --upgrade pip
  info "Installing deepfilternet (compiling from source — please be patient)…"
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
  fi
  "$DF_VENV/bin/pip" install deepfilternet
  ok "DeepFilterNet installed in $DF_VENV"
else
  warn "Skipped DeepFilterNet."
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 7 / 7 — Build macOS app"
# ─────────────────────────────────────────────────────────────────────────────
echo ""
if ask "Build CastPolish.app (native macOS launcher)?"; then
  "$PYTHON" "$SCRIPT_DIR/create_macos_app.py" <<< "n"
  ok "CastPolish.app built in $SCRIPT_DIR"

  if ask "Copy CastPolish.app to /Applications/?"; then
    cp -r "$SCRIPT_DIR/CastPolish.app" /Applications/CastPolish.app
    ok "Installed to /Applications/CastPolish.app"
  fi
else
  warn "Skipped app build."
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════"
echo -e "  ✓  CastPolish is ready!"
echo -e "  ══════════════════════════════════════════${RESET}"
echo ""
info "To start the web UI:"
echo "    $PYTHON $SCRIPT_DIR/castpolish.py serve"
echo ""
info "Or double-click CastPolish.app."
echo ""
read -r -p "  Press Enter to close this window…"
