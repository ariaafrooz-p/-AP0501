"""Masterpiece - a spatial-reasoning puzzle (pure-Python game core).

No UI dependencies. `Game.scene()` returns drawing primitives that any view can
render (main.py draws them with Tkinter; tests/preview.py renders them with PIL).

Data files (extracted from the original build):
  data/piece_colliders.json  - polygon outline of each of the 23 piece types
  data/silhouettes_csv.txt   - 5151 puzzles: "level,Piece:rot:x:y;Piece:rot:x:y;..."

Rules that come from the decompiled game code (see PSEUDOCODE.md):
  * over-budget rotation penalty        -> penalty()
  * round points up to a multiple of 10 -> round_up_to_ten()
  * adaptive level smoothing            -> Referee.next_score_level()
Numbers the code does not reveal (base points, bonus size, hint cost, timing
thresholds, damping constants) are my own choices and are marked CHOICE below.
"""
import json
import math
import os
import random

# ----------------------------------------------------------------- constants
SNAP_RADIUS = 45.0                 # how close (world units) a piece must be to snap
MATCH_TOL = 12.0
TRIALS_PER_GAME = 4                # from the game's session settings (1 for the short game)
MIN_LEVEL, MAX_LEVEL = 0.0, 38.0

# CHOICE: values the original code keeps in config, not recoverable from the wasm
BASE_POINTS = 500                  # scaled so the decoded penalty (up to ~1000 pts) is meaningful
POINTS_PER_PIECE = 50
PERFECT_BONUS_FRACTION = 0.25
HINT_COST_FRACTION = 0.20
SECONDS_AT_MIN_LEVEL = 20.0
SECONDS_AT_MAX_LEVEL = 60.0
LEVEL_DAMPING = 2.0
LEVEL_RATE = 0.5
START_LEVEL = 8.0


# ------------------------------------------------------------------ geometry
def step_for(cls):
    """Rotation step in degrees: the triangle-grid 'Polyiamond' pieces turn in 60 degree
    steps, every other piece in 45 degree steps (verified against the puzzle data)."""
    return 60 if cls.startswith("Polyiamond") else 45


def xform(poly, rot, x=0.0, y=0.0):
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return [(px * c - py * s + x, px * s + py * c + y) for px, py in poly]


def centroid(poly):
    n = len(poly)
    return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)


def poly_match(a, b, tol=MATCH_TOL):
    """True if two polygons have the same vertex set (order independent)."""
    if len(a) != len(b):
        return False
    t2 = tol * tol

    def has(p, q):
        return any((p[0] - r[0]) ** 2 + (p[1] - r[1]) ** 2 <= t2 for r in q)

    return all(has(p, b) for p in a) and all(has(p, a) for p in b)


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def bbox(polys):
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------- data
class GameData:
    def __init__(self, folder=None):
        folder = folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        with open(os.path.join(folder, "piece_colliders.json")) as f:
            raw = json.load(f)
        self.shapes = {name: [tuple(p) for p in paths[0]] for name, paths in raw.items()}   # logic (collider)
        with open(os.path.join(folder, "piece_outlines.json")) as f:                         # looks (smooth)
            self.outlines = {k: [tuple(p) for p in v] for k, v in json.load(f).items()}
        with open(os.path.join(folder, "rotate_arrow.json")) as f:
            self.arrow = [tuple(p) for p in json.load(f)]
        self.class_names = sorted(self.shapes)
        self.levels = {}
        with open(os.path.join(folder, "silhouettes_csv.txt")) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                level, rest = line.split(",", 1)
                pieces = []
                for part in rest.split(";"):
                    cls, rot, x, y = part.split(":")
                    pieces.append((cls, float(rot), float(x), float(y)))
                self.levels.setdefault(int(level), []).append(pieces)
        self.level_keys = sorted(self.levels)


# -------------------------------------------------------------------- scoring
def round_up_to_ten(v):
    """Referee.RoundUpToTen: (int)(ceil(v * 0.1) * 10)"""
    return int(math.ceil(v * 0.1) * 10)


def penalty(score, moves, budget, enabled=True):
    """SpatialReasoningReferee.Penalty (decoded from wasm func 115725).
    Each rotation over the budget costs 10*(100//budget) points, for at most `budget`
    extra rotations; the penalty can never take more than the current score."""
    if not enabled or moves <= budget or budget <= 0:
        return 0
    per = int((100 // budget) * 10.0)
    pen = per * (budget - min(moves, 2 * budget))
    return max(-score, pen)


# --------------------------------------------------------------------- puzzle
class Slot:
    def __init__(self, cls, rot, x, y, shape, outline):
        self.cls, self.rot, self.x, self.y = cls, rot % 360, x, y
        self.poly = xform(shape, rot, x, y)          # collider: used for logic
        self.draw = xform(outline, rot, x, y)        # smooth outline: used for drawing
        self.piece = None


class Piece:
    def __init__(self, pid, cls, rot):
        self.id, self.cls, self.rot = pid, cls, rot % 360
        self.x = self.y = 0.0
        self.slot = None


class Puzzle:
    """`view` (optional) = dict(board=(x0,y0,x1,y1) px, center=(cx,cy) px, max_scale=px per unit).
    With a view the puzzle picks its own scale so the silhouette fits the board, and the pieces start
    scattered on a ring around the board edge, like the original."""

    def __init__(self, data, silhouette, rng, view=None):
        self.data, self.rng = data, rng
        raw = [xform(data.shapes[c], r, x, y) for c, r, x, y in silhouette]
        bx0, by0, bx1, by1 = bbox(raw)
        ox, oy = -(bx0 + bx1) / 2, -(by0 + by1) / 2           # centre the silhouette on the origin
        self.slots = [Slot(c, r, x + ox, y + oy, data.shapes[c], data.outlines[c]) for c, r, x, y in silhouette]
        self.sil_w, self.sil_h = bx1 - bx0, by1 - by0
        self.moves = 0
        self.hints = 0
        for _ in range(30):                       # scramble until at least one rotation is needed
            self.pieces = []
            self.budget = 0
            for i, s in enumerate(self.slots):
                st = step_for(s.cls)
                k = rng.randrange(360 // st)
                p = Piece(i, s.cls, s.rot + k * st)
                self.budget += self.steps_needed(p.cls, p.rot, s.rot)
                self.pieces.append(p)
            if self.budget >= 1:
                break
        self.order = list(self.pieces)            # z-order, last = on top
        if view:
            bx0p, by0p, bx1p, by1p = view["board"]
            cx, cy = view["center"]
            self.S = min(view.get("max_scale", 1.36), 0.50 * (by1p - by0p) / self.sil_h, 0.55 * (bx1p - bx0p) / self.sil_w)
            inset = 38
            ring = ((bx0p + inset - cx) / self.S, (cy - (by1p - inset)) / self.S,
                    (bx1p - inset - cx) / self.S, (cy - (by0p + inset)) / self.S)
        else:
            self.S = 1.0
            ring = (-300.0, -260.0, 300.0, 260.0)
        self.snap_radius = max(SNAP_RADIUS, 42.0 / self.S)
        self._play = None
        if view and view.get("play"):                 # pieces must stay fully visible inside this px rectangle
            qx0, qy0, qx1, qy1 = view["play"]
            self._play = ((qx0 - cx) / self.S, (cy - qy1) / self.S, (qx1 - cx) / self.S, (cy - qy0) / self.S)
        self._layout_ring(ring)
        self._sample = self._silhouette_samples()
        self.hint_slot = None
        self.hint_piece = None

    # ---- construction helpers
    def steps_needed(self, cls, start, target):
        shape = self.data.shapes[cls]
        st = step_for(cls)
        n = 360 // st
        tp = xform(shape, target)
        best = n
        for j in range(n):
            if poly_match(xform(shape, start + j * st), tp, 1.0):
                best = min(best, j, n - j)
        return best

    def _layout_ring(self, ring):
        """Spread the pieces evenly around the rectangle `ring` (world units), in random order."""
        x0, y0, x1, y1 = ring
        w, h = x1 - x0, y1 - y0
        per = 2 * (w + h)
        order = list(self.pieces)
        self.rng.shuffle(order)
        start = self.rng.random() * per
        for i, p in enumerate(order):
            d = (start + per * i / len(order)) % per
            if d < w:
                p.x, p.y = x0 + d, y1
            elif d < w + h:
                p.x, p.y = x1, y1 - (d - w)
            elif d < 2 * w + h:
                p.x, p.y = x1 - (d - w - h), y0
            else:
                p.x, p.y = x0, y0 + (d - 2 * w - h)
            r = 0.12 * min(w, h)                    # a little jitter so it does not look machine-made
            p.x += self.rng.uniform(-r, r)
            p.y += self.rng.uniform(-r, r)
        self._separate(ring)

    def _separate(self, ring, iterations=120):
        """Push overlapping starting pieces apart (bounding-circle repulsion) and keep them near the ring."""
        x0, y0, x1, y1 = ring
        pad = 0.18 * min(x1 - x0, y1 - y0)
        for _ in range(iterations):
            moved = False
            info = []
            for p in self.pieces:
                poly = self.draw_poly_of(p)
                c = centroid(poly)
                info.append((p, c, max(math.hypot(v[0] - c[0], v[1] - c[1]) for v in poly)))
            for i in range(len(info)):
                for j in range(i + 1, len(info)):
                    pi, ci, ri = info[i]
                    pj, cj, rj = info[j]
                    dx, dy = cj[0] - ci[0], cj[1] - ci[1]
                    d = math.hypot(dx, dy)
                    need = 0.80 * (ri + rj)
                    if d < need:
                        if d < 1e-6:
                            dx, dy, d = self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), 1.0
                        k = (need - d) / 2 / d
                        pi.x -= dx * k; pi.y -= dy * k
                        pj.x += dx * k; pj.y += dy * k
                        moved = True
            for p in self.pieces:                    # stay in a band around the ring ...
                p.x = max(x0 - pad, min(x1 + pad, p.x))
                p.y = max(y0 - pad, min(y1 + pad, p.y))
                if self._play:                       # ... and fully inside the visible play area
                    qx0, qy0, qx1, qy1 = self._play
                    bx0, by0, bx1, by1 = bbox([self.draw_poly_of(p)])
                    p.x += max(0.0, qx0 - bx0) - max(0.0, bx1 - qx1)
                    p.y += max(0.0, qy0 - by0) - max(0.0, by1 - qy1)
            if not moved:
                break

    def _silhouette_samples(self, step=7.0):
        x0, y0, x1, y1 = bbox([s.poly for s in self.slots])
        self._ebox = (x0 - 30, y0 - 30, x1 + 30, y1 + 30)
        inside, outside = [], []
        ex0, ey0, ex1, ey1 = self._ebox
        y = ey0 + 0.3719          # off-grid so samples avoid shared piece edges
        while y <= ey1:
            x = ex0 + 0.2131
            while x <= ex1:
                (inside if any(point_in_poly((x, y), s.poly) for s in self.slots) else outside).append((x, y))
                x += step
            y += step
        return inside, outside

    # ---- geometry
    def poly_of(self, piece):
        """collider polygon (logic)"""
        return xform(self.data.shapes[piece.cls], piece.rot, piece.x, piece.y)

    def draw_poly_of(self, piece):
        """smooth outline (what the player sees and clicks)"""
        return xform(self.data.outlines[piece.cls], piece.rot, piece.x, piece.y)

    def hit_test(self, x, y):
        for p in reversed(self.order):
            if point_in_poly((x, y), self.draw_poly_of(p)):
                return p
        return None

    # ---- interaction
    def _release(self, piece):
        if piece.slot is not None:
            piece.slot.piece = None
            piece.slot = None

    def pick(self, piece):
        self._release(piece)
        self.order.remove(piece)
        self.order.append(piece)
        self.hint_slot = self.hint_piece = None

    def try_snap(self, piece):
        shape = self.data.shapes[piece.cls]
        mine0 = xform(shape, piece.rot)
        poly = self.poly_of(piece)
        c = centroid(poly)
        best, bd = None, self.snap_radius
        for s in self.slots:
            if s.piece is not None or s.cls != piece.cls:
                continue
            if not poly_match(mine0, xform(shape, s.rot), 1.0):
                continue
            sc = centroid(s.poly)
            d = math.hypot(sc[0] - c[0], sc[1] - c[1])
            if d < bd:
                best, bd = s, d
        if best is None:
            return None
        sc = centroid(best.poly)
        piece.x += sc[0] - c[0]
        piece.y += sc[1] - c[1]
        best.piece, piece.slot = piece, best
        self.order.remove(piece)                 # placed pieces sit under loose ones, so loose ones stay grabbable
        self.order.insert(0, piece)
        return best

    def drop(self, piece):
        self.try_snap(piece)
        self.hint_slot = self.hint_piece = None

    def rotate(self, piece, direction):
        """direction +1 = counter-clockwise, -1 = clockwise (one step)."""
        self._release(piece)
        piece.rot = (piece.rot + direction * step_for(piece.cls)) % 360
        self.moves += 1
        self.try_snap(piece)

    def hint(self):
        empty = [s for s in self.slots if s.piece is None]
        if not empty:
            return None
        s = self.rng.choice(empty)
        self.hint_slot = s
        self.hint_piece = next((p for p in self.pieces if p.slot is None and p.cls == s.cls), None)
        self.hints += 1
        return s

    # ---- completion
    def coverage(self):
        inside, outside = self._sample
        polys = [self.poly_of(p) for p in self.pieces]
        cov = over = 0
        for pt in inside:
            n = sum(point_in_poly(pt, q) for q in polys)
            if n >= 1:
                cov += 1
            if n >= 2:
                over += 1
        out = sum(1 for pt in outside if any(point_in_poly(pt, q) for q in polys))
        t = float(len(inside))
        return cov / t, over / t, out / t

    def is_solved(self):
        if all(s.piece is not None for s in self.slots):
            return True
        cov, over, out = self.coverage()       # also accepts a different tiling of the same shape
        return cov >= 0.97 and over <= 0.03 and out <= 0.03


# -------------------------------------------------------------------- referee
class Referee:
    def __init__(self, data, rng):
        self.data, self.rng = data, rng
        self.level = START_LEVEL
        self.total = 0
        self.results = []

    @staticmethod
    def next_score_level(current, target, minimum=MIN_LEVEL, damping=LEVEL_DAMPING, rate=LEVEL_RATE):
        """Referee.NextScoreLevel (wasm func 115427): move toward `target`, slower when
        coming down, exponentially smoothed, never below `minimum`."""
        t = current + (target - current) / damping if current > target else target
        return max(current + (t - current) * rate, minimum)

    def response_seconds(self):
        """Referee.InterpolateResponseTime idea: time allowed grows with level."""
        f = (self.level - MIN_LEVEL) / (MAX_LEVEL - MIN_LEVEL)
        return SECONDS_AT_MIN_LEVEL + f * (SECONDS_AT_MAX_LEVEL - SECONDS_AT_MIN_LEVEL)

    def pick_silhouette(self):
        key = min(self.data.level_keys, key=lambda k: (abs(k - self.level), k))
        return key, self.rng.choice(self.data.levels[key])

    def score_trial(self, puzzle, seconds, level_key):
        n = len(puzzle.slots)
        base = BASE_POINTS + POINTS_PER_PIECE * n
        perfect = puzzle.moves <= puzzle.budget
        pen = penalty(base, puzzle.moves, puzzle.budget)
        bonus = round(PERFECT_BONUS_FRACTION * base) if perfect else 0
        hint_cost = HINT_COST_FRACTION * base * puzzle.hints
        pts = round_up_to_ten(max(0.0, base + pen + bonus - hint_cost))
        fast = seconds <= self.response_seconds()
        if perfect and puzzle.hints == 0:
            rating = "PERFECT"
        elif puzzle.moves <= max(puzzle.budget * 1.5, puzzle.budget + 1):
            rating = "GREAT"
        else:
            rating = "OK"
        if perfect and fast:
            target = self.level + 8
        elif perfect or (fast and puzzle.moves <= puzzle.budget * 1.5):
            target = self.level + 4
        elif puzzle.moves <= puzzle.budget * 2:
            target = self.level
        else:
            target = self.level - 4
        self.level = self.next_score_level(self.level, min(MAX_LEVEL, target))
        self.total += pts
        res = dict(level=level_key, pieces=n, moves=puzzle.moves, budget=puzzle.budget, hints=puzzle.hints,
                   seconds=seconds, points=pts, rating=rating)
        self.results.append(res)
        return res


# ----------------------------------------------------------------------- game
CYAN = "#19c6ea"          # loose piece
CYAN_SEL = "#6fe3ff"      # piece being held
PLACED = "#3d5fd2"        # piece sitting in its slot
BOARD = "#2a3b8c"
BOARD_LINE = "#222f78"
SILHOUETTE = "#18235f"
FRAME = "#a35a06"
FRAME_DARK = "#7b4306"
HUD_BOX = "#f6c982"
HUD_TEXT = "#8a6a3e"
BAR = "#8a4b0a"
BAR_LINE = "#6b3a07"
BAR_TEXT = "#e0a458"
HINT_YELLOW = "#ffd54a"

# decorative tangram pattern on the board (normalised board coordinates 0..1)
BOARD_PATTERN = [
    ([(0.00, 0.36), (0.00, 1.00), (0.30, 0.70)], "#2f45a0"),
    ([(0.00, 0.36), (0.30, 0.70), (0.30, 0.36)], "#26378a"),
    ([(0.30, 0.04), (0.30, 0.36), (0.48, 0.36), (0.48, 0.04)], "#2f45a0"),
    ([(0.48, 0.00), (0.66, 0.00), (0.66, 0.36), (0.48, 0.36)], "#33499f"),
    ([(0.66, 0.00), (1.00, 0.00), (1.00, 0.33), (0.66, 0.33)], "#2c3f94"),
    ([(0.82, 0.33), (1.00, 0.33), (1.00, 0.66), (0.82, 0.66)], "#3a52b0"),
    ([(0.00, 1.00), (0.30, 0.70), (0.55, 1.00)], "#2f45a0"),
    ([(0.55, 1.00), (0.55, 0.62), (0.80, 0.62), (0.80, 1.00)], "#27398c"),
    ([(0.30, 0.70), (0.55, 0.62), (0.55, 1.00)], "#324aa6"),
    ([(0.80, 0.66), (1.00, 0.66), (1.00, 1.00), (0.80, 1.00)], "#2d4198"),
    ([(0.48, 0.36), (0.66, 0.36), (0.82, 0.62), (0.55, 0.62)], "#35509f"),
]


def _wood(w, h):
    rng = random.Random(7)
    out, y = [], 0
    lo, hi = (236, 134, 34), (255, 176, 62)
    while y < h:
        th = rng.randint(2, 6)
        v = 0.5 + 0.28 * math.sin(y * 0.05) + 0.17 * math.sin(y * 0.21 + 1.3) + rng.uniform(-0.08, 0.08)
        v = max(0.0, min(1.0, v))
        col = "#%02x%02x%02x" % tuple(int(lo[i] + (hi[i] - lo[i]) * v) for i in range(3))
        out.append(("rect", 0, y, w, y + th, col, col))
        y += th
    for _ in range(150):                                   # darker grain streaks
        x0 = rng.randint(-50, w - 60)
        yy = rng.randint(0, h)
        out.append(("rect", x0, yy, x0 + rng.randint(80, 420), yy + 1, "#d9791c", "#d9791c"))
    return out


class Game:
    W, H = 944, 720
    CX, CY = 472, 356
    FRAME_RECT = (99, 83, 842, 629)
    BOARD_RECT = (117, 101, 824, 611)
    BAR_Y = 644
    BUTTONS = [("rotl", 387, 644, 468, 720), ("rotr", 468, 644, 546, 720),
               ("hint", 546, 644, 944, 720), ("pause", 0, 0, 46, 46)]
    HINT_SECONDS = 3.0
    _static_cache = None

    def __init__(self, data=None, seed=None):
        self.data = data or GameData()
        self.seed = seed
        self.S = 1.0
        self.new_game()

    # ---- coordinates
    def w2p(self, x, y):
        return self.CX + x * self.S, self.CY - y * self.S

    def p2w(self, px, py):
        return (px - self.CX) / self.S, (self.CY - py) / self.S

    # ---- flow
    def new_game(self):
        self.rng = random.Random(self.seed)
        self.referee = Referee(self.data, self.rng)
        self.trial = 0
        self.selected = None
        self.dragging = False
        self.state = "playing"
        self.last = None
        self._start_trial()

    def _start_trial(self):
        self.trial += 1
        self.level_key, sil = self.referee.pick_silhouette()
        view = dict(board=self.BOARD_RECT, center=(self.CX, self.CY), max_scale=1.36,
                    play=(8, 52, self.W - 8, self.BAR_Y - 8))
        self.puzzle = Puzzle(self.data, sil, self.rng, view)
        self.S = self.puzzle.S
        self.elapsed = 0.0
        self.selected = None
        self.dragging = False
        self.hint_until = 0.0
        self.state = "playing"

    def _check_done(self):
        if self.puzzle.is_solved():
            self.last = self.referee.score_trial(self.puzzle, self.elapsed, self.level_key)
            self.selected = None
            self.dragging = False
            self.state = "solved"

    def _advance(self):
        if self.state == "solved":
            if self.trial >= TRIALS_PER_GAME:
                self.state = "summary"
            else:
                self._start_trial()
        elif self.state == "summary":
            self.new_game()

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
            self.dragging = False
        elif self.state == "paused":
            self.state = "playing"

    # ---- input
    def mouse_down(self, px, py):
        if self.state in ("solved", "summary"):
            self._advance()
            return
        if self.state == "paused":
            self.toggle_pause()
            return
        for name, x0, y0, x1, y1 in self.BUTTONS:
            if x0 <= px <= x1 and y0 <= py <= y1:
                self.action(name)
                return
        x, y = self.p2w(px, py)
        p = self.puzzle.hit_test(x, y)
        self.selected = p
        if p is not None:
            self.puzzle.pick(p)
            self.drag_off = (p.x - x, p.y - y)
            self.dragging = True

    def mouse_move(self, px, py):
        if self.state == "playing" and self.dragging and self.selected is not None:
            x, y = self.p2w(px, py)
            self.selected.x = x + self.drag_off[0]
            self.selected.y = y + self.drag_off[1]

    def mouse_up(self, px, py):
        if self.state == "playing" and self.dragging and self.selected is not None:
            self.dragging = False
            self.puzzle.drop(self.selected)
            self._check_done()

    def action(self, name):
        if name == "pause":
            self.toggle_pause()
            return
        if self.state != "playing":
            return
        if name in ("rotl", "rotr") and self.selected is not None:
            self.puzzle.rotate(self.selected, 1 if name == "rotl" else -1)
            self._check_done()
        elif name == "hint":
            if self.puzzle.hint() is not None:
                self.hint_until = self.elapsed + self.HINT_SECONDS

    def key(self, k):
        k = k.lower()
        if k in ("q", "left"):
            self.action("rotl")
        elif k in ("e", "right"):
            self.action("rotr")
        elif k == "h":
            self.action("hint")
        elif k in ("p", "escape"):
            self.toggle_pause()
        elif k in ("space", "return"):
            if self.state in ("solved", "summary"):
                self._advance()
            elif self.state == "paused":
                self.toggle_pause()

    def tick(self, dt):
        if self.state == "playing":
            self.elapsed += dt
            if self.puzzle.hint_slot is not None and self.elapsed > self.hint_until:
                self.puzzle.hint_slot = self.puzzle.hint_piece = None

    # ---- drawing
    def static_scene(self):
        """Wood table + framed board with the decorative pattern. Never changes, so a view can draw it once."""
        if Game._static_cache is None:
            out = _wood(self.W, self.H)
            fx0, fy0, fx1, fy1 = self.FRAME_RECT
            out.append(("rect", fx0 + 6, fy0 + 8, fx1 + 6, fy1 + 8, "#c06f14", "#c06f14"))       # soft shadow
            out.append(("rect", fx0, fy0, fx1, fy1, FRAME, FRAME_DARK))
            bx0, by0, bx1, by1 = self.BOARD_RECT
            out.append(("rect", bx0, by0, bx1, by1, BOARD, BOARD_LINE))
            bw, bh = bx1 - bx0, by1 - by0
            for poly, col in BOARD_PATTERN:
                out.append(("poly", [(bx0 + u * bw, by0 + v * bh) for u, v in poly], col, BOARD_LINE, 3))
            Game._static_cache = out
        return Game._static_cache

    def dynamic_scene(self):
        out = []
        P = self.w2p

        def pts(poly):
            return [P(x, y) for x, y in poly]

        if self.state in ("playing", "paused", "solved"):
            pz = self.puzzle
            for sl in pz.slots:
                out.append(("poly", pts(sl.draw), SILHOUETTE, SILHOUETTE, 2))
            if pz.hint_slot is not None:
                out.append(("poly", pts(pz.hint_slot.draw), "", HINT_YELLOW, 4))
            for p in pz.order:
                if p is self.selected:
                    fill, ol, w = CYAN_SEL, "#ffffff", 5
                elif p is pz.hint_piece:
                    fill, ol, w = CYAN, HINT_YELLOW, 5
                elif p.slot is not None:
                    fill, ol, w = PLACED, "#2e4aa8", 1
                else:
                    fill, ol, w = CYAN, "#ffffff", 4
                out.append(("poly", pts(pz.draw_poly_of(p)), fill, ol, w))
            # HUD (top right) and pause button (top left)
            out.append(("rect", 590, 0, self.W, 44, HUD_BOX, HUD_BOX))
            out.append(("text", 690, 22, "PUZZLE %d of %d" % (self.trial, TRIALS_PER_GAME), 12, HUD_TEXT, "center", True))
            out.append(("text", 850, 22, "SCORE   %d" % self.referee.total, 12, HUD_TEXT, "center", True))
            out.append(("rect", 0, 0, 46, 46, "#b4670d", "#b4670d"))
            out.append(("rect", 15, 13, 21, 33, CYAN, CYAN))
            out.append(("rect", 26, 13, 32, 33, CYAN, CYAN))
            # bottom bar: counter | rotate left | rotate right | HINT
            out.append(("rect", 0, self.BAR_Y, self.W, self.H, BAR, BAR))
            for x in (387, 468, 546):
                out.append(("rect", x - 1, self.BAR_Y + 4, x + 1, self.H - 4, BAR_LINE, BAR_LINE))
            out.append(("text", 190, 682, "%d of %d" % (pz.moves, pz.budget), 17, BAR_TEXT, "center", False))
            arrow = self.data.arrow
            aw = max(p[0] for p in arrow)
            for cx, mirror in ((427, True), (507, False)):
                h = 36.0
                pp = [((cx + (( (aw - x) if mirror else x) - aw / 2) * h), 682 + (y - 0.5) * h) for x, y in arrow]
                out.append(("poly", pp, CYAN, CYAN, 1))
            out.append(("text", 745, 682, "HINT", 17, CYAN, "center", True))
        if self.state == "paused":
            out.append(("rect", 232, 280, 712, 440, "#fff7e6", FRAME_DARK))
            out.append(("text", 472, 335, "Paused", 28, "#c0562f", "center", True))
            out.append(("text", 472, 395, "Click or press P to resume", 13, HUD_TEXT, "center", False))
        if self.state == "solved":
            r = self.last
            out.append(("rect", 212, 230, 732, 430, "#fff7e6", FRAME_DARK))
            out.append(("text", 472, 285, r["rating"] + "!", 32, "#c0562f", "center", True))
            out.append(("text", 472, 335, "+%d points" % r["points"], 20, "#5a4426", "center", True))
            out.append(("text", 472, 370, "Rotations %d (perfect = %d)   Hints %d" % (r["moves"], r["budget"], r["hints"]),
                        12, HUD_TEXT, "center", False))
            more = "Click or press Space to continue" if self.trial < TRIALS_PER_GAME else "Click or press Space for results"
            out.append(("text", 472, 405, more, 12, HUD_TEXT, "center", False))
        if self.state == "summary":
            out.append(("rect", 0, 0, self.W, self.H, "#f39a2c", "#f39a2c"))
            out.append(("rect", 150, 60, 794, 640, "#fff7e6", FRAME_DARK))
            out.append(("text", 472, 125, "Game over", 34, "#c0562f", "center", True))
            out.append(("text", 472, 190, "Total score: %d" % self.referee.total, 24, "#5a4426", "center", True))
            y = 270
            for i, r in enumerate(self.referee.results, 1):
                out.append(("text", 472, y, "Puzzle %d:  %d pieces   rotations %d / %d   %s   +%d" %
                            (i, r["pieces"], r["moves"], r["budget"], r["rating"], r["points"]),
                            13, "#5a4426", "center", False))
                y += 40
            out.append(("text", 472, y + 50, "Click or press Space to play again", 14, HUD_TEXT, "center", False))
        return out

    def scene(self):
        """Everything, in draw order (used by tests and the PNG preview)."""
        if self.state == "summary":
            return self.dynamic_scene()
        return self.static_scene() + self.dynamic_scene()
