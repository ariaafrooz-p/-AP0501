# Masterpiece (Python)

A playable re-creation of the *Masterpiece* spatial-reasoning puzzle, rebuilt from the data and code
recovered from the Unity WebGL build. Drag the coloured pieces into the dark shape. Rotate pieces with
the buttons or the keyboard. Fewer rotations = more points.

## Run
    python main.py            # optional: --seed 42 for reproducible puzzles, --no-sound to play silently
Needs Python 3.8+ with Tkinter (included with the python.org installers for Windows and macOS; on
Debian/Ubuntu: `sudo apt install python3-tk`). No other packages.

Controls: mouse drag = move, **Q / E** (or left/right arrows, or the two arrow buttons) = rotate the selected piece,
**H** = hint, **P** / **Esc** / the pause button = pause menu, **Space / click** = continue. A game is 4 puzzles.

Pause menu (like the original): Resume, Restart (new game), Mute Sound, Mute Music, Quit, How To Play.
Mute Sound / Mute Music switch the effects / the ambient music off and on (the label flips to Unmute).

## Sound
The game's own clips (pick-up, drop, rotate, hint, wood slide, the three result chimes, start/end jingles, menu pops and
the ambient wind chimes) are in `data/audio/*.wav`. `audio.py` plays them with the standard library only, trying in order:
pygame (if you `pip install pygame`), Windows' built-in MCI (via ctypes), `afplay` (macOS) or `paplay`/`aplay`/`play`
(Linux). On start the game prints which one it picked (`sound: windows-mci`). If none works it stays silent and still runs.
Music: the three ambient clips play one after another with random pauses, quietly in the background.

Caveats: I could not listen to it. The tests use a fake backend, and the Windows/pygame/system-player code paths have not
been run on a real sound card. Which clip goes with which action is my reading of the file names, and the loudness
(`tools/build_audio.py`) is my own choice: the originals are authored very quietly and the real game boosts them in its audio mixer.

## Test
    python tests/test_core.py         # headless: geometry, snapping, scoring, full auto-played games
    python tests/preview.py outdir    # needs Pillow; renders PNG screenshots of the game scenes

## Layout
- `core.py`   all game logic and the scene description (no UI imports)
- `main.py`   thin Tkinter view (draws core's primitives, forwards mouse/keys)
- `data/piece_colliders.json`   23 collider polygons (from the bundle): used for all game logic
- `data/piece_outlines.json`    smooth curved outlines of the 23 pieces (traced from the exported sprite meshes): used for drawing/clicking
- `data/rotate_arrow.json`      outline of the rotate-arrow icon
- `data/background.png`         baked wood table + board + translucent HUD/bottom bar (944x720)
- `data/wood.png`, `data/pause.png`  plain wood (summary / how-to) and wood with the translucent pause-menu buttons baked in
- `tools/build_background.py`   rebuilds background.png from the exported wood/frame textures + screenshots of the original
- `audio.py`                   sound backends + event-to-clip logic;  `data/audio/`  the 18 clips converted to WAV
- `tools/build_audio.py`        converts + level-matches the exported .m4a clips (needs ffmpeg)
- `tools/extract_outlines.py`   rebuilds the two files above from the exported sprite SVGs
- `data/silhouettes_csv.txt`    5,152 puzzles, `level,Piece:rotation:x:y;...`

## What is original and what is mine
From the original (decoded game data / wasm code):
- the 23 piece shapes and all 5,152 puzzles; difficulty level = the first number of each row
- rotation steps: 60 degrees for `Polyiamond*` pieces, 45 degrees for all others
- over-budget rotation penalty: each extra rotation costs `10 * (100 // budget)` points, for at most
  `budget` extra rotations, never more than the current score (`SpatialReasoningReferee.Penalty`)
- points are rounded up to a multiple of 10 (`Referee.RoundUpToTen`)
- adaptive level: smoothed move toward a target, slower coming down, floored at the minimum
  (`Referee.NextScoreLevel`), 4 puzzles per game, snap-to-slot behaviour, hint button

My own choices (the original keeps these in config that the code does not reveal) - all constants at the
top of `core.py`: base points (500 + 50 per piece, scaled so the decoded penalty matters), the perfect
bonus (25 %), hint cost (20 % per hint), the time thresholds (20-60 s), level damping (2.0) and rate (0.5),
starting level (8), and the rule that maps performance to a target level.
The *shapes* of the pieces and the rotate arrow are traced from the original sprites. The look around them
(layout, colours, fonts) is my own approximation of screenshots of the original. The wood texture and the board's line
pattern come from the exported game textures; the board's tile colours were sampled from the screenshots. No original
fonts or audio are used.

## Known limits
- No tutorial, animations or multiple languages.
- Scoring scale is mine: a screenshot of the original shows a score of 8,740 on puzzle 1, so its scale or carry-over differs.
- A puzzle counts as solved when every piece is snapped into a slot, or when the pieces cover the shape
  with under 3 % overlap/overflow (so a different tiling of the same shape also wins).
