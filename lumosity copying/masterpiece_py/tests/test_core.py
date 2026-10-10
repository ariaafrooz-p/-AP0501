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
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
