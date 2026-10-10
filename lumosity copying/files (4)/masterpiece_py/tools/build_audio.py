"""Convert the exported .m4a clips to 16-bit PCM WAV (plays with the standard library / any backend).
Needs ffmpeg once, at build time. Usage: python tools/build_audio.py <media_dir> <out_dir>
<media_dir> is the export's 'media' folder (contains scene/audio and cug-shared-assets/audio)."""
import os, subprocess, sys

CLIPS = [  # (sub folder, base name)
    ("scene", "pickup0"), ("scene", "pickup1"), ("scene", "pickup2"), ("scene", "pickup3"),
    ("scene", "drop"), ("scene", "tileRotate08"), ("scene", "woodSlide"), ("scene", "hint"),
    ("scene", "chimes_AnswerCorrect"), ("scene", "chimes_AnswerExcellent"), ("scene", "chimes_AnswerPerfect"),
    ("scene", "ambient_WindChimes1"), ("scene", "ambient_WindChimes2"), ("scene", "ambient_WindChimes_short"),
    ("cug-shared-assets", "gameStart"), ("cug-shared-assets", "gameEnd"),
    ("cug-shared-assets", "popUpAppear"), ("cug-shared-assets", "popUpDisappear"),
]

# The exported clips are authored very quietly (peaks between -4 dB and -43 dB; the original mixes them up in its
# audio mixer, which is not in the data). We normalise each clip to a target peak (dBFS) instead. These levels are my
# own choice: effects fairly prominent, the ambient music well below them.
TARGET_PEAK_DB = {
    "ambient_WindChimes1": -20, "ambient_WindChimes2": -20, "ambient_WindChimes_short": -20,
    "pickup0": -9, "pickup1": -9, "pickup2": -9, "pickup3": -9, "drop": -8, "tileRotate08": -8, "woodSlide": -12,
    "hint": -7, "popUpAppear": -9, "popUpDisappear": -9,
}
DEFAULT_PEAK_DB = -6


def peak_db(src):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].split("dB")[0])
    raise RuntimeError("could not measure " + src)


if __name__ == "__main__":
    media, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for sub, name in CLIPS:
        src = os.path.join(media, sub, "audio", name + ".m4a")
        dst = os.path.join(out, name + ".wav")
        gain = TARGET_PEAK_DB.get(name, DEFAULT_PEAK_DB) - peak_db(src)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", "volume=%.2fdB" % gain,
                        "-acodec", "pcm_s16le", "-ar", "44100", dst], check=True)
        print("%-28s %7d bytes" % (name + ".wav", os.path.getsize(dst)))
