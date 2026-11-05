"""Find the audio tools, check songs, and convert them to the game's format."""
import glob
import json
import os
import shutil
import subprocess
import sys
import wave

from .errors import ModError
from .formats.acb import Track

AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus")
SHORTEST_SONG = 10
BITRATE = "256000"
FFMPEG_PACKAGE = "Gyan.FFmpeg.Essentials"
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW, "stdin": subprocess.DEVNULL}


def resource(relative):
    if getattr(sys, "frozen", False):
        roots = [sys._MEIPASS, os.path.dirname(sys.executable)]
    else:
        roots = [os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))]
    return next((p for p in (os.path.join(r, relative) for r in roots) if os.path.exists(p)), None)


def find_tool(name):
    """Look next to the app, on PATH, then in winget's folder, since PATH is stale right after an install."""
    found = resource(os.path.join("tools", name)) or shutil.which(name)
    if found:
        return found
    packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    hits = glob.glob(os.path.join(packages, "Gyan.FFmpeg*", "**", "bin", name), recursive=True)
    return hits[0] if hits else None


def ffmpeg_ready():
    return bool(find_tool("ffmpeg.exe") and find_tool("ffprobe.exe"))


def install_ffmpeg():
    if not shutil.which("winget"):
        raise ModError("winget is not available. Install FFmpeg yourself and reopen the app.")
    done = subprocess.run(["winget", "install", "-e", "--id", FFMPEG_PACKAGE, "--silent",
                           "--accept-package-agreements", "--accept-source-agreements"],
                          capture_output=True, text=True, **HIDDEN)
    if not ffmpeg_ready():
        raise ModError(f"FFmpeg did not install (winget exit code {done.returncode}).")


def probe(path):
    """Return the length in seconds, or raise ModError saying why the file can't be used."""
    name = os.path.basename(path)
    tool = find_tool("ffprobe.exe")
    if not tool:
        raise ModError("FFmpeg is needed to read songs.")
    done = subprocess.run([tool, "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=codec_type:format=duration", "-of", "json", path],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", **HIDDEN)
    try:
        info = json.loads(done.stdout)
        seconds = float(info["format"]["duration"])
    except (ValueError, KeyError):
        raise ModError(f"{name} is not a readable audio file.") from None
    if not info.get("streams"):
        raise ModError(f"{name} has no audio.")
    if seconds < SHORTEST_SONG:
        raise ModError(f"{name} is shorter than {SHORTEST_SONG} seconds.")
    return seconds


def convert(path, work, index, rate):
    """Convert a song to HCA at the slot's sample rate."""
    name = os.path.basename(path)
    wav_path, hca_path = os.path.join(work, f"{index}.wav"), os.path.join(work, f"{index}.hca")
    ffmpeg, encoder = find_tool("ffmpeg.exe"), resource(os.path.join("tools", "VGAudioCli.exe"))
    if not ffmpeg or not encoder:
        raise ModError("The audio tools are missing.")
    try:
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", path, "-map", "0:a:0", "-map_metadata", "-1",
                        "-bitexact", "-ar", str(rate), "-ac", "2", "-c:a", "pcm_s16le", wav_path],
                       check=True, capture_output=True, **HIDDEN)
        subprocess.run([encoder, "-i", wav_path, "-o", hca_path, "--bitrate", BITRATE],
                       check=True, capture_output=True, **HIDDEN)
    except subprocess.CalledProcessError:
        raise ModError(f"Could not convert {name}.") from None
    with wave.open(wav_path) as audio:
        samples = audio.getnframes()
    os.remove(wav_path)
    check = subprocess.run([ffmpeg, "-v", "error", "-i", hca_path, "-f", "null", "-"],
                           capture_output=True, text=True, **HIDDEN)
    if check.stderr.strip():
        raise ModError(f"{name} failed its check after converting.")
    with open(hca_path, "rb") as f:
        data = f.read()
    os.remove(hca_path)
    return Track(data, samples, rate)
