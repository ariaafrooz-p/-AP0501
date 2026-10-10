"""Run:  python tests/test_core.py   (no test framework needed)"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core
from core import *


def overlap_fraction(data, sil):
    polys = [xform(data.shapes[c], r, x, y) for c, r, x, y in sil]
    x0, y0, x1, y1 = bbox(polys)
    cov = over = 0
    y = y0 + 0.3719                       # off-grid samples (grid-aligned ones land on shared edges)
    while y <= y1:
        x = x0 + 0.2131
        while x <= x1:
            n = sum(point_in_poly((x, y), p) for p in polys)
            cov += n >= 1
            over += n >= 2
            x += 5
        y += 5
    return over / max(cov, 1)


def inside_point(poly):
    """A point guaranteed to be inside the polygon (the pivot can lie outside concave pieces)."""
    c = centroid(poly)
    if point_in_poly(c, poly):
        return c
    x0, y0, x1, y1 = bbox([poly])
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if point_in_poly((x + 0.31, y + 0.17), poly):
                return (x + 0.31, y + 0.17)
            x += 3
        y += 3
    raise AssertionError("no interior point")


def solve_perfectly(game):
    """Play the current trial optimally through the public mouse/key API.
    Uses the pairing piece i <-> slot i, which is the pairing the rotation budget is defined on."""
    pz = game.puzzle
    for piece in list(pz.pieces):
        slot = pz.slots[piece.id]
        shape = pz.data.shapes[piece.cls]
        # select the piece with a click inside it
        cx, cy = inside_point(pz.draw_poly_of(piece))
        px, py = game.w2p(cx, cy)
        game.mouse_down(px, py)
        game.mouse_up(px, py)
        assert game.selected is piece, (piece.cls, game.selected and game.selected.cls)
        # rotate the shortest way
        st = step_for(piece.cls)
        n = 360 // st
        # symmetric pieces match at several rotations: take the cheapest one (either direction)
        ccw = min((j for j in range(n) if poly_match(xform(shape, piece.rot + j * st), xform(shape, slot.rot), 1.0)),
                  key=lambda j: min(j, n - j))
        for _ in range(min(ccw, n - ccw)):
            game.action("rotl" if ccw <= n - ccw else "rotr")
        # drag it close to (not exactly on) its slot and release
        pc = centroid(pz.poly_of(piece))
        sc = centroid(slot.poly)
        cx, cy = inside_point(pz.draw_poly_of(piece))
        game.mouse_down(*game.w2p(cx, cy))
        tx, ty = game.w2p(cx + sc[0] - pc[0] + 9, cy + sc[1] - pc[1] - 7)
        game.mouse_move(tx, ty)
        game.mouse_up(tx, ty)


def main():
    data = GameData()
    # 1. data
    assert len(data.shapes) == 23, len(data.shapes)
    assert sum(len(v) for v in data.levels.values()) == 5152
    print("ok data: 23 shapes, 5152 puzzles, levels", data.level_keys[0], "-", data.level_keys[-1])

    # 2. geometry: pieces in every sampled puzzle must tile without overlapping (validates rotation convention)
    rng = random.Random(1)
    worst = 0.0
    for _ in range(250):
        key = rng.choice(data.level_keys)
        worst = max(worst, overlap_fraction(data, rng.choice(data.levels[key])))
    assert worst < 0.02, worst
    print("ok geometry: worst piece overlap over 250 puzzles = %.4f" % worst)

    # 3. rotation steps used by the data are multiples of the step we assume
    for key, sils in data.levels.items():
        for sil in sils:
            for c, r, x, y in sil:
                assert (r % step_for(c)) < 1e-6 or step_for(c) - (r % step_for(c)) < 1e-6, (c, r)
    print("ok rotation steps consistent with data")

    # 4. scoring functions vs decoded wasm behaviour
    assert round_up_to_ten(41) == 50 and round_up_to_ten(40) == 40 and round_up_to_ten(0.1) == 10
    # penalty = per * (budget - min(moves, 2*budget)), per = 10 * (100 // budget), floored at -score
    assert penalty(1000, 3, 3) == 0 and penalty(1000, 2, 3) == 0          # within budget
    assert penalty(1000, 5, 4) == -250                                    # 1 over:  250 * (4-5)
    assert penalty(1000, 6, 4) == -500                                    # 2 over
    assert penalty(1000, 99, 4) == -1000                                  # capped at 2*budget -> 250 * (4-8)
    assert penalty(200, 5, 4) == -200                                     # never more than the score
    assert penalty(500, 9, 4) == -500
    assert penalty(1000, 5, 4, enabled=False) == 0
    assert penalty(1000, 130, 101) == 0                                   # 100 // 101 == 0 -> no per-move cost
    assert abs(Referee.next_score_level(10, 20) - 15) < 1e-9          # up: halfway to target
    assert abs(Referee.next_score_level(10, 2) - 8.0) < 1e-9          # down: t=10+(2-10)/2=6 -> 10+(6-10)*.5=8
    assert Referee.next_score_level(1, -50) == 0                      # clamped at minimum
    print("ok scoring functions")

    # 5. snapping + win detection on a fresh puzzle
    rng = random.Random(7)
    pz = Puzzle(data, rng.choice(data.levels[12]), rng)
    assert pz.budget >= 1 and not pz.is_solved()
    for s in pz.slots:                                     # place each piece exactly into a slot (cheat)
        pc = next(p for p in pz.pieces if p.slot is None and p.cls == s.cls and
                  poly_match(xform(data.shapes[p.cls], p.rot), xform(data.shapes[s.cls], s.rot), 1.0)) \
            if any(p.slot is None and p.cls == s.cls and
                   poly_match(xform(data.shapes[p.cls], p.rot), xform(data.shapes[s.cls], s.rot), 1.0) for p in pz.pieces) else None
        if pc is None:
            continue
    # a piece with the right orientation 20 units away snaps; one 80 units away does not
    pz2 = Puzzle(data, [("Square", 0, 0, 0)], random.Random(3))
    p = pz2.pieces[0]
    s = pz2.slots[0]
    p.rot = s.rot
    sc = centroid(s.poly)
    p.x, p.y = p.x * 0 + sc[0] + 80, sc[1]
    pz2.drop(p)
    assert p.slot is None
    p.x, p.y = sc[0] + 20, sc[1] - 15
    pz2.drop(p)
    assert p.slot is s and abs(centroid(pz2.poly_of(p))[0] - sc[0]) < 1e-6
    assert pz2.is_solved()
    print("ok snapping and single-piece win")

    # 6. coverage-based win: shifted placement is NOT a win, exact placement is
    pz3 = Puzzle(data, data.levels[12][0], random.Random(5))
    for p in pz3.pieces:
        s = next(s for s in pz3.slots if s.piece is None and s.cls == p.cls and s not in [q.slot for q in pz3.pieces if q.slot])
        p.rot, p.x, p.y = s.rot, s.x, s.y
    assert pz3.is_solved()
    for p in pz3.pieces:
        p.x += 25
    assert not pz3.is_solved()
    print("ok coverage check (exact = solved, shifted = not solved)")

    # 7. full game through the input API: optimal play must give PERFECT every time
    for seed in (1, 2, 3):
        g = Game(data, seed=seed)
        for t in range(TRIALS_PER_GAME):
            assert g.state == "playing", (seed, t, g.state)
            solve_perfectly(g)
            assert g.state == "solved", (seed, t, g.state, g.puzzle.coverage())
            r = g.last
            assert r["moves"] == r["budget"], r
            assert r["rating"] == "PERFECT" and r["points"] > 0, r
            g.key("space")
        assert g.state == "summary"
        scene = g.scene()
        assert any(p[0] == "text" and "Game over" in p[3] for p in scene)
        g.key("space")
        assert g.state == "playing" and g.trial == 1 and g.referee.total == 0
    print("ok full games (3 seeds) played optimally through mouse/key API")

    # 8. levels adapt upward when playing perfectly and fast
    g = Game(data, seed=11)
    start = g.referee.level
    for _ in range(3):
        solve_perfectly(g)
        g.key("space")
    assert g.referee.level > start, (start, g.referee.level)
    print("ok adaptive level: %.1f -> %.1f after perfect play" % (start, g.referee.level))

    # 9. hint + rotation bookkeeping
    g = Game(data, seed=4)
    g.action("hint")
    assert g.puzzle.hint_slot is not None and g.puzzle.hints == 1
    g.tick(5.0)
    assert g.puzzle.hint_slot is None
    p = g.puzzle.pieces[0]
    px, py = g.w2p(p.x, p.y)
    g.mouse_down(px, py)
    g.mouse_up(px, py)
    before = g.puzzle.moves
    g.key("q")
    assert g.puzzle.moves == before + 1
    print("ok hint timeout and rotation counting")
    # 10. layout regressions: every start piece fully visible (not under the bar/HUD) and no overlapping start pieces
    rng = random.Random(21)
    G = Game(data, seed=1)
    view = dict(board=Game.BOARD_RECT, center=(Game.CX, Game.CY), max_scale=1.36, play=(8, 52, Game.W - 8, Game.BAR_Y - 8))
    for _ in range(150):
        pz = Puzzle(data, rng.choice(data.levels[rng.choice(data.level_keys)]), rng, view)
        G.S = pz.S
        polys = [pz.draw_poly_of(p) for p in pz.pieces]
        for poly in polys:
            pts = [G.w2p(x, y) for x, y in poly]
            assert min(p[0] for p in pts) > 7 and max(p[0] for p in pts) < Game.W - 7
            assert min(p[1] for p in pts) > 51 and max(p[1] for p in pts) < Game.BAR_Y - 7, "piece under HUD/bar"
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                x0, y0, x1, y1 = bbox([polys[i]])
                n = hit = 0
                y = y0 + 1.3
                while y < y1:
                    x = x0 + 1.1
                    while x < x1:
                        if point_in_poly((x, y), polys[i]):
                            n += 1
                            hit += point_in_poly((x, y), polys[j])
                        x += 8
                    y += 8
                assert not n or hit / n < 0.05, "start pieces overlap"
    print("ok layout: 150 puzzles, all start pieces visible and separate")
    # 11. pause menu
    def click_item(g, key):
        ya, yb = MENU_Y[[k for k, _ in MENU_ITEMS].index(key)]
        g.mouse_down(472, (ya + yb) / 2)
        g.mouse_up(472, (ya + yb) / 2)

    def texts(g):
        return [p[3] for p in g.scene() if p[0] == "text"]

    g = Game(data, seed=2)
    g.tick(1.0)
    t_play = g.elapsed
    assert t_play > 0 and g.state == "playing"
    g.key("p")
    assert g.state == "paused" and "pause.png" in g.static_scene()[0][3]
    g.tick(5.0)
    assert g.elapsed == t_play, "clock must stop while paused"
    assert all(label in texts(g) for _, label in MENU_ITEMS), texts(g)
    assert not any(p[0] == "poly" and p[2] == CYAN for p in g.scene()), "no pieces while paused"
    ya, yb = MENU_Y[0][1], MENU_Y[1][0]
    g.mouse_down(472, (ya + yb) / 2)                       # the gap between two buttons does nothing
    assert g.state == "paused"
    click_item(g, "mute_sound")
    assert g.sound_muted and "Unmute Sound" in texts(g) and "Mute Sound" not in texts(g)
    click_item(g, "mute_sound")
    assert not g.sound_muted and "Mute Sound" in texts(g)
    click_item(g, "mute_music")
    assert g.music_muted and "Unmute Music" in texts(g)
    click_item(g, "mute_music")
    assert not g.music_muted
    click_item(g, "howto")
    assert g.state == "howto" and "How To Play" in texts(g) and "wood.png" in g.static_scene()[0][3]
    g.mouse_down(300, 300)
    assert g.state == "paused"
    click_item(g, "howto")
    g.key("p")
    assert g.state == "paused"
    click_item(g, "resume")
    assert g.state == "playing" and "background.png" in g.static_scene()[0][3]
    g.key("escape")
    g.mouse_down(10, 10)                                   # clicking the 'Paused' tag resumes too
    assert g.state == "playing"
    g.mouse_down(*[(b[1] + b[3]) / 2 for b in Game.BUTTONS if b[0] == "pause"][0:1] * 2)   # pause button
    assert g.state == "paused"
    solve_perfectly_state = Game(data, seed=3)
    solve_perfectly(solve_perfectly_state)
    solve_perfectly_state.key("space")                     # trial 2 of 4
    solve_perfectly_state.key("p")
    assert solve_perfectly_state.trial == 2 and solve_perfectly_state.referee.total > 0
    click_item(solve_perfectly_state, "restart")
    assert solve_perfectly_state.state == "playing" and solve_perfectly_state.trial == 1
    assert solve_perfectly_state.referee.total == 0 and solve_perfectly_state.puzzle.moves == 0
    click_item(g, "quit")
    assert g.quit_requested
    sg = Game(data, seed=5)
    for _ in range(TRIALS_PER_GAME):
        solve_perfectly(sg)
        sg.key("space")
    assert sg.state == "summary" and "wood.png" in sg.static_scene()[0][3]
    print("ok pause menu: clock stops, every button works, restart/quit/mute/how-to, gaps ignored")
    # 12. sound events emitted by the game
    g = Game(data, seed=2)
    assert g.drain_events() == ["game_start"] and g.drain_events() == []
    pc = g.puzzle.pieces[0]
    cx, cy = inside_point(g.puzzle.draw_poly_of(pc))
    g.mouse_down(*g.w2p(cx, cy))
    g.mouse_up(*g.w2p(cx, cy))
    assert g.drain_events() == ["pickup", "drop"]
    g.key("q")
    assert g.drain_events() == ["rotate"]
    g.key("h")
    assert g.drain_events() == ["hint"]
    g.mouse_down(Game.CX, Game.BAR_Y - 5)                    # empty board: no piece there, so no sound
    assert g.drain_events() == []
    g.key("p")
    assert g.drain_events() == ["menu_open"]
    click_item(g, "resume")
    assert g.drain_events() == ["menu_close"]
    g.key("p")
    g.mouse_down(10, 10)                                     # the 'Paused' tag resumes
    assert g.drain_events() == ["menu_open", "menu_close"]
    g = Game(data, seed=7)
    g.drain_events()
    for trial in range(TRIALS_PER_GAME):
        solve_perfectly(g)
        ev = g.drain_events()
        assert ev.count("solved_" + g.last["rating"].lower()) == 1 and "solved_perfect" in ev, ev
        g.key("space")
        assert g.drain_events() == (["slide"] if trial < TRIALS_PER_GAME - 1 else ["game_end"])
    g = Game(data, seed=8)                                   # a sloppy trial must give the matching (non-perfect) chime
    g.drain_events()
    pc = g.puzzle.pieces[0]
    cx, cy = inside_point(g.puzzle.draw_poly_of(pc))
    g.mouse_down(*g.w2p(cx, cy))
    g.mouse_up(*g.w2p(cx, cy))
    for _ in range(9):
        g.key("q")
    solve_perfectly(g)
    ev = g.drain_events()
    assert g.last["rating"] != "PERFECT" and ("solved_" + g.last["rating"].lower()) in ev and "solved_perfect" not in ev, (g.last, ev)
    print("ok sound events: pickup/drop/rotate/hint/menu/slide/solved chimes/game_end")

    # 13. audio layer (with a fake backend: no sound card needed)
    import audio as A

    class FakeBackend:
        name = "fake"

        def __init__(self):
            self.loaded, self.played, self.stopped, self.closed = {}, [], [], False

        def load(self, n, p):
            self.loaded[n] = p

        def play(self, n):
            self.played.append(n)

        def stop(self, n):
            self.stopped.append(n)

        def close(self):
            self.closed = True

    needed = {c for cl in A.EVENT_CLIPS.values() for c in cl} | set(A.MUSIC_CLIPS)
    fb = FakeBackend()
    au = A.Audio(backend=fb, rng=random.Random(1))
    assert set(fb.loaded) == needed and all(0.1 < au.durations[n] < 10 for n in needed), set(needed) - set(fb.loaded)
    import wave
    for n in needed:
        with wave.open(fb.loaded[n]) as w:
            assert w.getsampwidth() == 2 and w.getframerate() == 44100
    import array
    peaks = {}
    for n in needed:
        with wave.open(fb.loaded[n]) as w:
            peaks[n] = max(abs(x) for x in array.array("h", w.readframes(w.getnframes())))
    assert all(1500 < p < 32000 for p in peaks.values()), peaks            # nothing silent, nothing clipped
    assert max(peaks[n] for n in A.MUSIC_CLIPS) < 0.5 * min(p for n, p in peaks.items() if n not in A.MUSIC_CLIPS)
    for ev_name, clip in (("solved_perfect", "chimes_AnswerPerfect"), ("solved_great", "chimes_AnswerExcellent"),
                          ("solved_ok", "chimes_AnswerCorrect"), ("menu_open", "popUpAppear"), ("menu_close", "popUpDisappear"),
                          ("game_start", "gameStart"), ("game_end", "gameEnd"), ("slide", "woodSlide"), ("hint", "hint"),
                          ("drop", "drop"), ("rotate", "tileRotate08")):
        fb.played.clear()
        au.handle([ev_name])
        assert fb.played == [clip], (ev_name, fb.played)
    fb.played.clear()
    au.handle(["pickup"] * 40)
    assert set(fb.played) == {"pickup0", "pickup1", "pickup2", "pickup3"}        # all four variants get used
    fb.played.clear()
    au.handle(["drop", "rotate"], sound_on=False)                                 # muted: nothing plays
    au.handle(["no_such_event"])
    assert fb.played == []
    # music: starts at once, waits while the clip plays, never repeats a clip back to back, stops when muted
    au.update(0.0, music_on=True)
    assert len(fb.played) == 1 and fb.played[0] in A.MUSIC_CLIPS
    au.update(0.5, music_on=True)
    assert len(fb.played) == 1
    seq = [fb.played[0]]
    for _ in range(60):
        au.update(20.0, music_on=True)
        seq.append(fb.played[-1])
    assert len(fb.played) == 61 and all(a != b for a, b in zip(seq, seq[1:])), seq[:6]
    n_before = len(fb.played)
    au.update(0.1, music_on=False)
    assert fb.stopped and fb.stopped[-1] in A.MUSIC_CLIPS
    au.update(500.0, music_on=False)
    assert len(fb.played) == n_before                                              # silent while music is off
    au.update(0.1, music_on=True)
    assert len(fb.played) == n_before + 1                                          # and resumes immediately
    au.close()
    assert fb.closed
    fb2 = FakeBackend()                                                            # missing clips must never crash the game
    au2 = A.Audio(folder="/no/such/folder", backend=fb2)
    au2.handle(["drop", "solved_perfect"])
    au2.update(1.0, True)
    assert fb2.played == [] and fb2.loaded == {}
    nb = A.NullBackend()
    A.Audio(backend=nb).handle(["drop"])
    b = A.make_backend()                                                           # picks something usable, never raises
    assert hasattr(b, "play") and b.name in ("pygame", "windows-mci", "system-player", "none")
    print("ok audio: mapping, mute, music scheduling, missing-file safety, backend fallback (here: %s)" % b.name)
    # 14. intro: the camera pans over the desk and lands on the board
    assert data.intro, "intro assets missing"
    x_end = data.intro["x_end"]
    g = Game(data, seed=12, intro=True)
    assert g.state == "intro" and g.drain_events() == ["game_start"]
    assert g.static_scene()[0][3].endswith("wood.png")                       # the wood stays fixed on screen
    dyn = g.dynamic_scene()
    imgs = [p for p in dyn if p[0] == "image"]
    assert imgs[0][3].endswith("intro_world.png") and imgs[0][1] == 0 and imgs[1][3].endswith("hud.png")
    txt = [p[3] for p in dyn if p[0] == "text"]
    assert "PUZZLE 1 of 4" in txt and "SCORE   0" in txt and "HINT" not in txt     # HUD yes, bottom bar not yet
    g.key("q")
    g.key("h")
    g.key("p")
    assert g.state == "intro" and g.puzzle.moves == 0 and g.puzzle.hints == 0       # other keys do nothing
    g.tick(INTRO_HOLD * 0.5)
    assert g.cam_x == 0 and g.elapsed == 0.0                                        # resting on the first frame
    ref = Game(data, seed=12)                                                       # same puzzle without intro
    p_intro = [p for p in g.dynamic_scene() if p[0] == "poly"]
    p_ref = [p for p in ref.dynamic_scene() if p[0] == "poly"][:len(p_intro)]
    for a_, b_ in zip(p_intro, p_ref):                                              # board items sit x_end px to the right
        assert all(abs(pa[0] - pb[0] - x_end) < 1e-6 and abs(pa[1] - pb[1]) < 1e-6 for pa, pb in zip(a_[1], b_[1]))
    events, prev, steps = [], -1.0, 0
    while g.state == "intro":
        g.tick(0.05)
        events += g.drain_events()
        steps += 1
        assert g.cam_x >= prev - 1e-9 and 0 <= g.view_dx <= x_end
        prev = g.cam_x
        assert steps < 400
    remaining = INTRO_HOLD + INTRO_PAN - INTRO_HOLD * 0.5
    assert remaining - 1e-6 <= steps * 0.05 < remaining + 0.06, steps      # the intro lasts INTRO_HOLD + INTRO_PAN
    assert g.state == "playing" and g.view_dx == 0 and g.elapsed == 0.0 and events.count("slide") == 1
    a_, b_ = [p for p in g.dynamic_scene() if p[0] != "image"], [p for p in ref.dynamic_scene() if p[0] != "image"]
    assert a_ == b_, "after the pan the screen must equal the normal game screen"
    assert g.static_scene()[0][3].endswith("background.png")
    for how in ("click", "space", "return", "escape"):                              # skipping
        g = Game(data, seed=3, intro=True)
        g.drain_events()
        g.tick(1.0)
        if how == "click":
            g.mouse_down(300, 300)
        else:
            g.key(how)
        assert g.state == "playing" and g.view_dx == 0 and g.puzzle.moves == 0, how
    g = Game(data, seed=3, intro=True)
    g.key("space")
    g.key("p")
    click_item(g, "restart")                                                        # restart does not replay the intro
    assert g.state == "playing"
    d2 = GameData()
    d2.intro = None
    assert Game(d2, seed=1, intro=True).state == "playing"                          # no intro assets: just play
    try:
        import numpy as np
        from PIL import Image
        world = np.array(Image.open(os.path.join(data.folder, "intro_world.png")).convert("RGBA"))
        bg = np.array(Image.open(os.path.join(data.folder, "background.png")).convert("RGB")).astype(int)
        hud = Image.open(os.path.join(data.folder, "hud.png"))
        assert world.shape == (720, data.intro["width"], 4) and x_end + 944 == data.intro["width"]
        assert hud.mode == "RGBA" and hud.size == (944, 720)
        bx0, by0, bx1, by1 = Game.BOARD_RECT
        end_view = world[:, x_end:x_end + 944, :3].astype(int)
        assert np.abs(end_view[by0:by1, bx0:bx1] - bg[by0:by1, bx0:bx1]).max() == 0, "last intro frame must equal the board screen"
        assert world[300, 100, 3] == 0 and world[:, :, 3].mean() > 20        # wood stays transparent, objects opaque
        print("ok intro assets: world strip ends exactly on the board screen; wood areas transparent")
    except ImportError:
        print("skip intro pixel checks (numpy/Pillow not installed)")
    print("ok intro: hold, pan, skip, restart, no-asset fallback, board items travel with the desk")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
