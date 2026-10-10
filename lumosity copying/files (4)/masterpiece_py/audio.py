"""Sound for Masterpiece. Standard library only (uses pygame if it is installed).

The game core never plays sound itself: it queues events ("pickup", "drop", ...) and the view hands them to
`Audio.handle`. `Audio.update` plays the background music: the three ambient wind-chime clips one after another with
random pauses, so no backend needs loop support.

Backends, tried in this order:
  pygame        if installed (pip install pygame): the most reliable mixer
  windows-mci   Windows only: the built-in winmm MCI API through ctypes, several sounds can overlap
  system-player macOS `afplay`, Linux `paplay` / `aplay` / `play`
  none          silent (also used with --no-sound)

Which clip belongs to which action is my reading of the file names (the original wires them up in compiled code).
"""
import os
import random
import shutil
import subprocess
import sys
import wave

EVENT_CLIPS = {
    "pickup": ["pickup0", "pickup1", "pickup2", "pickup3"],
    "drop": ["drop"],
    "rotate": ["tileRotate08"],
    "hint": ["hint"],
    "slide": ["woodSlide"],                      # a new puzzle starts
    "solved_perfect": ["chimes_AnswerPerfect"],
    "solved_great": ["chimes_AnswerExcellent"],
    "solved_ok": ["chimes_AnswerCorrect"],
    "game_start": ["gameStart"],
    "game_end": ["gameEnd"],
    "menu_open": ["popUpAppear"],
    "menu_close": ["popUpDisappear"],
}
MUSIC_CLIPS = ["ambient_WindChimes1", "ambient_WindChimes2", "ambient_WindChimes_short"]


# ------------------------------------------------------------------ backends
class NullBackend:
    name = "none"

    def __init__(self, reason=""):
        self.reason = reason

    def load(self, name, path):
        pass

    def play(self, name):
        pass

    def stop(self, name):
        pass

    def close(self):
        pass


class PygameBackend:
    name = "pygame"

    def __init__(self):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        self._pg = pygame
        self._sounds = {}

    def load(self, name, path):
        self._sounds[name] = self._pg.mixer.Sound(path)

    def play(self, name):
        if name in self._sounds:
            self._sounds[name].play()

    def stop(self, name):
        if name in self._sounds:
            self._sounds[name].stop()

    def close(self):
        self._pg.mixer.quit()


class WindowsMciBackend:
    """winmm MCI through ctypes: every clip gets its own alias, so music and effects play at the same time."""
    name = "windows-mci"

    def __init__(self):
        import ctypes
        self._winmm = ctypes.windll.winmm          # raises AttributeError / OSError on other systems
        self._buf = ctypes.create_unicode_buffer(256)
        self._aliases = {}

    def _mci(self, command):
        return self._winmm.mciSendStringW(command, self._buf, 255, 0)

    def load(self, name, path):
        alias = "mp_" + name
        if self._mci('open "%s" type waveaudio alias %s' % (path, alias)) == 0:
            self._aliases[name] = alias

    def play(self, name):
        alias = self._aliases.get(name)
        if alias:
            self._mci("seek %s to start" % alias)
            self._mci("play %s" % alias)

    def stop(self, name):
        alias = self._aliases.get(name)
        if alias:
            self._mci("stop %s" % alias)

    def close(self):
        for alias in self._aliases.values():
            self._mci("close %s" % alias)
        self._aliases = {}


class SubprocessBackend:
    """Fire-and-forget system players (macOS afplay, Linux paplay/aplay/play)."""
    name = "system-player"

    def __init__(self):
        if sys.platform == "darwin":
            cmd = ["afplay"]
        else:
            cmd = next(([c] + a for c, a in (("paplay", []), ("aplay", ["-q"]), ("play", ["-q"])) if shutil.which(c)), None)
        if not cmd or not shutil.which(cmd[0]):
            raise RuntimeError("no command line audio player found")
        self._cmd = cmd
        self._paths = {}
        self._procs = {}

    def load(self, name, path):
        self._paths[name] = path

    def play(self, name):
        path = self._paths.get(name)
        if not path:
            return
        procs = [p for p in self._procs.get(name, []) if p.poll() is None]
        procs.append(subprocess.Popen(self._cmd + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self._procs[name] = procs

    def stop(self, name):
        for p in self._procs.pop(name, []):
            if p.poll() is None:
                p.terminate()

    def close(self):
        for name in list(self._procs):
            self.stop(name)


def make_backend():
    problems = []
    for factory in (PygameBackend, WindowsMciBackend, SubprocessBackend):
        try:
            return factory()
        except Exception as e:                      # missing library / wrong OS / no device: try the next one
            problems.append("%s: %s" % (factory.__name__, e))
    return NullBackend("; ".join(problems))


# --------------------------------------------------------------------- Audio
class Audio:
    def __init__(self, folder=None, backend=None, rng=None, music_gap=(0.8, 3.0)):
        self.folder = folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "audio")
        self.backend = backend if backend is not None else make_backend()
        self.rng = rng or random.Random()
        self.music_gap = music_gap
        self.durations = {}
        names = {c for clips in EVENT_CLIPS.values() for c in clips} | set(MUSIC_CLIPS)
        for name in sorted(names):
            path = os.path.join(self.folder, name + ".wav")
            if not os.path.exists(path):
                continue
            try:
                with wave.open(path) as w:
                    self.durations[name] = w.getnframes() / float(w.getframerate())
                self.backend.load(name, path)
            except Exception:                        # a clip that will not load must never stop the game
                self.durations.pop(name, None)
        self.clock = 0.0
        self.music_until = 0.0
        self.music_playing = None
        self.last_music = None

    @property
    def backend_name(self):
        return self.backend.name

    def handle(self, events, sound_on=True):
        """Play the effects for the game's events (dropped silently while sound is muted)."""
        if not sound_on:
            return
        for e in events:
            clips = [c for c in EVENT_CLIPS.get(e, []) if c in self.durations]
            if clips:
                self.backend.play(self.rng.choice(clips))

    def update(self, dt, music_on=True):
        """Background music: one ambient clip after another with a random pause in between."""
        self.clock += dt
        if not music_on:
            if self.music_playing:
                self.backend.stop(self.music_playing)
                self.music_playing = None
            self.music_until = 0.0                   # start straight away when music is switched back on
            return
        if self.clock < self.music_until:
            return
        choices = [c for c in MUSIC_CLIPS if c in self.durations and c != self.last_music]
        if not choices:
            return
        name = self.rng.choice(choices)
        self.backend.play(name)
        self.last_music = self.music_playing = name
        self.music_until = self.clock + self.durations[name] + self.rng.uniform(*self.music_gap)

    def close(self):
        try:
            self.backend.close()
        except Exception:
            pass
