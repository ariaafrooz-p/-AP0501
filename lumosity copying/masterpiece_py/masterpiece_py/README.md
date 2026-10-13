# Masterpiece (Python)

A playable re-creation of the *Masterpiece* spatial-reasoning puzzle, rebuilt from the data and code
recovered from the Unity WebGL build. Drag the coloured pieces into the dark shape. Rotate pieces with
the buttons or the keyboard. Fewer rotations = more points.

## Run
    python main.py            # optional: --seed 42 for reproducible puzzles, --no-sound to play silently
Needs Python 3.8+ with Tkinter (included with the python.org installers for Windows and macOS; on
Debian/Ubuntu: `sudo apt install python3-tk`). No other packages.

Controls: mouse drag = move, **Q / E** (or left/right arrows, or the two arrow buttons) = rotate the selected piece,
**H** = hint, **P** / **Esc** / the pause button = pause menu, **Space / click** = continue (or skip the intro). A game is 4 puzzles.

Pause menu (like the original): Resume, Restart (new game), Mute Sound, Mute Music, Quit, How To Play.
Mute Sound / Mute Music switch the effects / the ambient music off and on (the label flips to Unmute).

Hover and press effects (taken from screenshots of the original): the pause-menu item under the mouse becomes a solid cyan
button with a white icon and label; the pause button turns cyan with white bars; a rotate button fills solid cyan while it is
pressed (its arrow disappears into the background; keyboard Q/E flash the button too); the cursor becomes a hand over buttons.
The piece you are holding is orange-yellow with a small ring on its rotation pivot, and a hint draws dotted yellow outlines
around the target slot and over the hinted piece's white outline.

## Intro
A new game starts with the original's intro: the camera pans across a desk (starfish, sketch paper, coffee cup, the oval
painting with a missing piece, loose pieces on a mat with a hammer) and arrives at the puzzle board, the HUD fixed on screen.
Click, Space, Enter or Esc skips it; `python main.py --skip-intro` goes straight to the board. Every new game plays it:
the first start, Restart in the pause menu, and Play again after the last puzzle. The puzzle clock starts when the board has arrived.

It is built from your screenshots of the original (`tools/build_intro.py`): the wood is fixed to the screen (the 1280x960 wood
texture shown 1:1) and the desk slides over it, so each screenshot minus its wood gives the desk objects; five screenshots
are registered, blended into one wide transparent strip (`data/intro_world.png`, 3091x720) and upscaled about 1.5x, and the
real board layer is pasted on the end so the pan lands exactly on the game's board. The HUD boxes are a real alpha overlay
(`data/hud.png`) because they must stay put while the desk moves.
Caveats: the art is upscaled from small screenshots, so it is a little softer than the vector original; the pan's duration
and easing are my guess (0.6 s rest + 5.5 s smooth pan); the original's wood may move slightly differently.
Tk draws the PNG layers with real transparency (Tk 8.6, what Python ships); if your Tk did not, the transparent parts would
show flat wood orange instead (the pan would still work).

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
- `data/intro_world.png`, `data/intro.json`, `data/hud.png`, `data/board_layer.png`  the intro strip and its layers
- `tools/build_intro.py`        builds the intro strip from the intro screenshots (needs opencv-python + numpy)
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
