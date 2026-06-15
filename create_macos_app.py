#!/usr/bin/env python3
"""
Creates a native macOS .app launcher for CastPolish.
Run once:  python3 create_macos_app.py

Double-click the resulting auphonic-oss.app to start the server
and open the web interface. Drag it to your Dock or Applications
folder for quick access.
"""

import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME    = "CastPolish"
SERVER_PORT = 8765
SCRIPT_DIR  = Path(__file__).parent.resolve()
SERVER_PY   = SCRIPT_DIR / "castpolish.py"
PID_FILE    = Path.home() / ".castpolish" / "server.pid"
LOG_FILE    = Path("/tmp/castpolish.log")
PURPLE      = (124, 106, 247)   # brand colour #7c6af7


# ── Icon generation ───────────────────────────────────────────────────────────

def _sign(px, py, x1, y1, x2, y2):
    return (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)


def _make_icon_pixels(size: int):
    """
    Returns an (size, size, 4) uint8 numpy RGBA array:
    purple circle with a white play-button triangle.
    """
    import numpy as np

    x = np.arange(size, dtype=np.float32)
    y = np.arange(size, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)       # shape (size, size)

    cx, cy = size / 2.0, size / 2.0
    dx, dy = xx - cx, yy - cy
    dist   = np.hypot(dx, dy)
    radius = size / 2.0 - 1.0

    # Subtle radial gradient on the background
    grad = np.clip(1.0 - 0.18 * (dx + dy) / size, 0.75, 1.0)
    bg   = np.clip(
        np.stack([np.full((size, size), c, dtype=np.float32) for c in PURPLE], axis=2)
        * grad[:, :, np.newaxis],
        0, 255
    ).astype(np.uint8)

    # ── Play triangle ─────────────────────────────────────────────────────────
    m = size * 0.22
    p1x, p1y = cx - m * 0.55, cy - m          # top-left
    p2x, p2y = cx - m * 0.55, cy + m          # bottom-left
    p3x, p3y = cx + m * 0.95, cy              # right tip

    d1 = (xx - p2x) * (p1y - p2y) - (p1x - p2x) * (yy - p2y)
    d2 = (xx - p3x) * (p2y - p3y) - (p2x - p3x) * (yy - p3y)
    d3 = (xx - p1x) * (p3y - p1y) - (p3x - p1x) * (yy - p1y)

    has_neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    has_pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    in_tri  = ~(has_neg & has_pos)

    # ── Compose RGBA ──────────────────────────────────────────────────────────
    aa = max(1.5, size * 0.002)
    circle_alpha = np.clip((radius + aa - dist) / aa * 255, 0, 255).astype(np.uint8)

    rgba       = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = bg
    rgba[in_tri, :3] = 255          # white triangle
    rgba[:, :, 3]    = circle_alpha  # anti-aliased circular mask
    rgba[dist > radius + aa] = 0    # fully transparent outside circle

    return rgba


def _rgba_to_png(rgba) -> bytes:
    """Encode a numpy RGBA array as a PNG bytestring (no Pillow needed)."""
    import numpy as np

    size = rgba.shape[0]

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    # One filter byte (0 = None) per row, then raw RGBA bytes
    rows = b"".join(b"\x00" + bytes(rgba[y].flatten()) for y in range(size))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )


def _make_png(size: int) -> bytes:
    return _rgba_to_png(_make_icon_pixels(size))


def _create_iconset(iconset_dir: Path):
    """Populate a .iconset directory with all sizes macOS requires."""
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # (logical_size, actual_pixel_size, suffix)
    entries = [
        (16,  16,  ""),   (16,  32,  "@2x"),
        (32,  32,  ""),   (32,  64,  "@2x"),
        (128, 128, ""),   (128, 256, "@2x"),
        (256, 256, ""),   (256, 512, "@2x"),
        (512, 512, ""),   (512, 1024,"@2x"),
    ]

    rendered: dict[int, bytes] = {}
    for _, px, _ in entries:
        if px not in rendered:
            print(f"    rendering {px}×{px}…", end=" ", flush=True)
            rendered[px] = _make_png(px)
            print("done")

    for logical, px, suffix in entries:
        fname = f"icon_{logical}x{logical}{suffix}.png"
        (iconset_dir / fname).write_bytes(rendered[px])


def _build_icns(iconset_dir: Path, icns_out: Path):
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_out)],
        check=True, capture_output=True,
    )


# ── AppleScript launcher ──────────────────────────────────────────────────────

def _find_python() -> str:
    """Return the absolute path of the best available python3 (>=3.10)."""
    import shutil as _shutil
    candidates = [
        sys.executable,
        _shutil.which("python3") or "",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return "/usr/bin/env python3"


def _launcher_sh(port: int, pid_file: Path, log_file: Path) -> str:
    """Shell script that daemonises the Flask server.
    Uses $0 to locate castpolish.py relative to itself — works after app is moved."""
    python_bin = _find_python()
    return f'''\
#!/bin/sh
# CastPolish server launcher — generated by create_macos_app.py
# SCRIPT_DIR is resolved at runtime so the app works from any location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
mkdir -p "{pid_file.parent}"
nohup "{python_bin}" "$SCRIPT_DIR/castpolish.py" serve --port {port} \\
    </dev/null >>"{log_file}" 2>&1 &
echo $! > "{pid_file}"
'''


def _applescript(port: int, log_file: Path) -> str:
    """AppleScript launcher.
    Uses (path to me) to locate launcher.sh — works after app is moved."""
    url = f"http://localhost:{port}/"
    return f'''\
on run
    set theURL to "{url}"
    set theLog to "{log_file}"

    -- Resolve launcher.sh relative to this app bundle (works when app is moved)
    set appPosixPath to POSIX path of (path to me)
    set theLauncher to appPosixPath & "Contents/Resources/launcher.sh"

    -- If server already up, just open it
    try
        do shell script "curl -sf --max-time 1 " & theURL & " > /dev/null"
        open location theURL
        return
    end try

    -- Start server via the bundled launcher script
    do shell script "/bin/sh " & quoted form of theLauncher

    -- Wait up to 20 seconds for readiness
    set maxWait to 20
    set waited to 0
    set ready to false
    repeat while waited < maxWait
        delay 1
        set waited to waited + 1
        try
            do shell script "curl -sf --max-time 1 " & theURL & " > /dev/null"
            set ready to true
            exit repeat
        end try
    end repeat

    if ready then
        open location theURL
        display notification "Server running at " & theURL with title "CastPolish" subtitle "Ready"
    else
        display alert "CastPolish failed to start" message ¬
            "Check the log at " & theLog & " for details." as critical
    end if
end run
'''


def _compile_app(app_path: Path, script_text: str):
    tmp = app_path.parent / "_tmp_launcher.applescript"
    tmp.write_text(script_text)
    try:
        if app_path.exists():
            shutil.rmtree(app_path)
        subprocess.run(
            ["osacompile", "-o", str(app_path), str(tmp)],
            check=True, capture_output=True,
        )
    finally:
        tmp.unlink(missing_ok=True)


def _apply_icon(app_path: Path, icns_path: Path):
    resources = app_path / "Contents" / "Resources"

    # Replace osacompile's default applet icon
    dest_icns = resources / f"{APP_NAME}.icns"
    shutil.copy(icns_path, dest_icns)

    # Point Info.plist at our icon file
    plist = app_path / "Contents" / "Info.plist"
    text  = plist.read_text()
    text  = text.replace("<string>applet</string>", f"<string>{APP_NAME}</string>")
    plist.write_text(text)

    # Remove the old applet.icns
    for f in resources.glob("applet.icns"):
        f.unlink()

    # CFBundleExecutable must match the actual binary name; osacompile names it "applet"
    macos_dir = app_path / "Contents" / "MacOS"
    applet_bin = macos_dir / "applet"
    named_bin  = macos_dir / APP_NAME
    if applet_bin.exists() and not named_bin.exists():
        shutil.copy(applet_bin, named_bin)

    # Touch the app so Finder refreshes its icon cache
    subprocess.run(["touch", str(app_path)], check=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if sys.platform != "darwin":
        sys.exit("This script is macOS-only.")

    if not SERVER_PY.exists():
        sys.exit(f"Cannot find {SERVER_PY}\nRun this script from the auphonic-oss directory.")

    app_path = SCRIPT_DIR / f"{APP_NAME}.app"
    tmp_dir  = SCRIPT_DIR / ".app_build"
    tmp_dir.mkdir(exist_ok=True)

    print(f"\n  ⟁ Building {APP_NAME}.app\n")

    # 1. Generate icon
    print("  [1/3] Generating icon…")
    iconset_dir = tmp_dir / f"{APP_NAME}.iconset"
    icns_path   = tmp_dir / f"{APP_NAME}.icns"
    _create_iconset(iconset_dir)
    _build_icns(iconset_dir, icns_path)
    print("        Icon built.\n")

    # 2. Compile AppleScript launcher
    print("  [2/3] Compiling launcher…")
    resources_dir  = app_path / "Contents" / "Resources"
    launcher_sh    = resources_dir / "launcher.sh"
    bundled_server = resources_dir / "castpolish.py"
    # AppleScript uses (path to me) — no hardcoded path needed
    script = _applescript(SERVER_PORT, LOG_FILE)
    _compile_app(app_path, script)
    # Inject launcher.sh (uses $0-relative path) and a fresh castpolish.py
    launcher_sh.write_text(_launcher_sh(SERVER_PORT, PID_FILE, LOG_FILE))
    launcher_sh.chmod(0o755)
    shutil.copy(SERVER_PY, bundled_server)
    # Bake in the git build stamp — the bundle has no .git, so castpolish.py's
    # get_build_version() reads this file to show "v1.6.0 (a1b2c3d)" in the app.
    try:
        short = subprocess.run(
            ["git", "-C", str(SCRIPT_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if short:
            (resources_dir / "build_stamp.txt").write_text(short + "\n")
            print(f"        Build stamp: {short}")
    except Exception as exc:
        print(f"        (build stamp skipped: {exc})")
    print(f"        App compiled.\n")

    # 3. Apply custom icon
    print("  [3/3] Applying icon…")
    _apply_icon(app_path, icns_path)
    print("        Icon applied.\n")

    # Clean up temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Ad-hoc sign so Gatekeeper doesn't block the app
    print("  [4/4] Signing app…")
    subprocess.run(["find", str(app_path), "-name", "._*", "-delete"], check=False)
    subprocess.run(["xattr", "-cr", str(app_path)], check=False)
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        check=False, capture_output=True,
    )
    print("        Signed.\n")

    print(f"  ✓ Done:  {app_path}\n")
    print("  Next steps:")
    print(f"    • Double-click {APP_NAME}.app to start")
    print(f"    • Or drag it to your Applications folder:")
    print(f"        cp -r \"{app_path}\" /Applications/")
    print(f"    • Or drag it to the Dock from Applications")
    print(f"\n  Server log (if something goes wrong): {LOG_FILE}\n")

    # Offer to open the folder in Finder
    answer = input("  Open folder in Finder? [Y/n]: ").strip().lower()
    if answer != "n":
        subprocess.run(["open", "-R", str(app_path)])


if __name__ == "__main__":
    main()
