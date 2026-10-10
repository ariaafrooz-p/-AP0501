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
        self.folder = folder
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
# colours measured on screenshots of the original (and on its scene data: UI cyan = rgb(0.19, 0.74, 0.92))
CYAN = "#16cbe8"          # loose piece
CYAN_SEL = "#6fe3ff"      # piece being held
PLACED = "#3d5fd2"        # piece sitting in its slot
SILHOUETTE = "#202448"    # target shape (darker, more purple than the board tiles)
HUD_TEXT = "#9b6a38"
BAR_TEXT = "#a88c66"
UI_CYAN = "#30bdeb"       # rotate arrows, HINT, pause icon
HINT_YELLOW = "#ffd44a"   # hint_* sprites use rgb(1.0, 0.83, 0.29)
PANEL = "#fff7e6"
PANEL_EDGE = "#7b4306"
TITLE = "#c0562f"
BODY = "#5a4426"
PAUSE_TEXT = "#3f3831"

# pause menu (measured on a screenshot of the original, scaled to the 944x720 window)
MENU_ITEMS = [("resume", "Resume"), ("restart", "Restart"), ("mute_sound", "Mute Sound"),
              ("mute_music", "Mute Music"), ("quit", "Quit"), ("howto", "How To Play")]
MENU_X = (232, 709)
MENU_Y = [(87, 173), (179, 266), (271, 358), (364, 451), (455, 543), (549, 636)]
PAUSE_LABEL = (0, 0, 178, 60)
HOWTO_LINES = ["Drag each piece into the dark shape until the shape is completely filled.",
               "Tap a piece, then use the arrow buttons (or Q / E) to rotate it.",
               "Pieces snap into place when they are close enough.",
               "The fewer rotations you use, the more points you earn.",
               "Stuck? HINT (or H) shows where one piece belongs."]


def menu_icon(kind, cx, cy, color, slashed=False):
    """Little cyan icons for the pause menu, as drawing primitives."""
    out = []
    if kind == "resume":
        out.append(("poly", [(cx - 9, cy - 15), (cx - 9, cy + 15), (cx + 14, cy)], color, color, 1))
    elif kind == "restart":
        r, pts = 14.0, []
        for i in range(0, 291, 10):                                   # open circle, gap at the top right
            a = math.radians(45 + i)
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
        out.append(("line", pts, color, 3))
        ex, ey = pts[0]
        tx, ty = pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]          # direction the arrow head points
        n = math.hypot(tx, ty) or 1.0
        tx, ty = tx / n, ty / n
        nx, ny = -ty, tx
        out.append(("poly", [(ex + tx * 9, ey + ty * 9), (ex + nx * 7, ey + ny * 7), (ex - nx * 7, ey - ny * 7)],
                    color, color, 1))
    elif kind in ("mute_sound", "mute_music", "howto"):
        out.append(("oval", cx - 16, cy - 16, cx + 16, cy + 16, "", color, 2.5))
        if kind == "mute_sound":
            out.append(("poly", [(cx - 8, cy - 4), (cx - 3, cy - 4), (cx + 3, cy - 9), (cx + 3, cy + 9),
                                 (cx - 3, cy + 4), (cx - 8, cy + 4)], color, color, 1))
            out.append(("line", [(cx + 6, cy - 5), (cx + 8, cy), (cx + 6, cy + 5)], color, 2))
        elif kind == "mute_music":
            out.append(("oval", cx - 8, cy + 1, cx - 1, cy + 8, color, color, 1))
            out.append(("line", [(cx - 1, cy + 4), (cx - 1, cy - 8), (cx + 6, cy - 4)], color, 2.5))
        else:
            out.append(("text", cx, cy, "?", 15, color, "center", True))
    elif kind == "quit":
        out.append(("line", [(cx - 12, cy - 12), (cx + 12, cy + 12)], color, 3))
        out.append(("line", [(cx + 12, cy - 12), (cx - 12, cy + 12)], color, 3))
    if slashed:
        out.append(("line", [(cx - 15, cy + 15), (cx + 15, cy - 15)], color, 3))
    return out


class Game:
    W, H = 944, 720
    CX, CY = 472, 356
    BOARD_RECT = (120, 106, 815, 610)          # the blue board inside the brown border (matches background.png)
    BAR_Y = 647
    BUTTONS = [("rotl", 386, 647, 463, 720), ("rotr", 466, 647, 543, 720),
               ("hint", 547, 647, 944, 720), ("pause", 0, 0, 50, 50)]
    HINT_SECONDS = 3.0
    _static_cache = None

    def __init__(self, data=None, seed=None):
        self.data = data or GameData()
        self.seed = seed
        self.S = 1.0
        self.sound_muted = False          # the view reads these two flags (see audio.py)
        self.music_muted = False
        self.events = []                  # sound events for the view to play: "pickup", "drop", "rotate", ...
        self.quit_requested = False       # the view closes the window when this becomes True
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
        self._emit("game_start" if self.trial == 1 else "slide")

    def _check_done(self):
        if self.puzzle.is_solved():
            self.last = self.referee.score_trial(self.puzzle, self.elapsed, self.level_key)
            self.selected = None
            self.dragging = False
            self.state = "solved"
            self._emit("solved_" + self.last["rating"].lower())

    def _advance(self):
        if self.state == "solved":
            if self.trial >= TRIALS_PER_GAME:
                self.state = "summary"
                self._emit("game_end")
            else:
                self._start_trial()
        elif self.state == "summary":
            self.new_game()

    def _emit(self, name):
        self.events.append(name)

    def drain_events(self):
        """Sound events since the last call (the view plays them)."""
        ev, self.events = self.events, []
        return ev

    def _resume(self):
        self.state = "playing"
        self._emit("menu_close")

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
            self.dragging = False
            self._emit("menu_open")
        elif self.state == "paused":
            self._resume()
        elif self.state == "howto":
            self.state = "paused"

    # ---- pause menu
    def menu_label(self, key, text):
        if key == "mute_sound" and self.sound_muted:
            return "Unmute Sound"
        if key == "mute_music" and self.music_muted:
            return "Unmute Music"
        return text

    def menu_action(self, key):
        if key == "resume":
            self._resume()
        elif key == "restart":
            self.new_game()
        elif key == "mute_sound":
            self.sound_muted = not self.sound_muted
        elif key == "mute_music":
            self.music_muted = not self.music_muted
        elif key == "quit":
            self.quit_requested = True
        elif key == "howto":
            self.state = "howto"

    def _menu_click(self, px, py):
        x0, y0, x1, y1 = PAUSE_LABEL
        if x0 <= px <= x1 and y0 <= py <= y1:          # the 'Paused' tag in the corner resumes, like the pause button
            self._resume()
            return
        for (key, _), (ya, yb) in zip(MENU_ITEMS, MENU_Y):
            if MENU_X[0] <= px <= MENU_X[1] and ya <= py <= yb:
                self.menu_action(key)
                return

    # ---- input
    def mouse_down(self, px, py):
        if self.state in ("solved", "summary"):
            self._advance()
            return
        if self.state == "howto":
            self.state = "paused"
            return
        if self.state == "paused":
            self._menu_click(px, py)
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
            self._emit("pickup")
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
            self._emit("drop")
            self._check_done()

    def action(self, name):
        if name == "pause":
            self.toggle_pause()
            return
        if self.state != "playing":
            return
        if name in ("rotl", "rotr") and self.selected is not None:
            self.puzzle.rotate(self.selected, 1 if name == "rotl" else -1)
            self._emit("rotate")
            self._check_done()
        elif name == "hint":
            if self.puzzle.hint() is not None:
                self.hint_until = self.elapsed + self.HINT_SECONDS
                self._emit("hint")

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
        """The baked wood table + framed board + translucent HUD boxes and bottom bar (data/background.png).
        Never changes, so a view can draw it once."""
        name = {"paused": "pause.png", "howto": "wood.png", "summary": "wood.png"}.get(self.state, "background.png")
        return [("image", 0, 0, os.path.join(self.data.folder, name))]

    def dynamic_scene(self):
        out = []
        P = self.w2p

        def pts(poly):
            return [P(x, y) for x, y in poly]

        if self.state in ("playing", "solved"):
            pz = self.puzzle
            for sl in pz.slots:
                out.append(("poly", pts(sl.draw), SILHOUETTE, SILHOUETTE, 2))
            if pz.hint_slot is not None:
                out.append(("poly", pts(pz.hint_slot.draw), "", HINT_YELLOW, 4))
            for p in pz.order:
                if p is self.selected:
                    fill, ol, w = CYAN_SEL, "#ffffff", 7
                elif p is pz.hint_piece:
                    fill, ol, w = CYAN, HINT_YELLOW, 7
                elif p.slot is not None:
                    fill, ol, w = PLACED, "#2e4aa8", 1
                else:
                    fill, ol, w = CYAN, "#ffffff", 6
                out.append(("poly", pts(pz.draw_poly_of(p)), fill, ol, w))
            # HUD texts (boxes are baked into the background, so the wood shows through them like in the original)
            out.append(("text", 669, 25, "PUZZLE %d of %d" % (self.trial, TRIALS_PER_GAME), 12, HUD_TEXT, "center", True))
            out.append(("text", 828, 25, "SCORE   %d" % self.referee.total, 12, HUD_TEXT, "center", True))
            out.append(("rect", 17, 14, 24, 36, UI_CYAN, UI_CYAN))                       # pause icon
            out.append(("rect", 28, 14, 35, 36, UI_CYAN, UI_CYAN))
            # bottom bar: counter | rotate left | rotate right | HINT
            out.append(("text", 190, 684, "%d of %d" % (pz.moves, pz.budget), 17, BAR_TEXT, "center", False))
            arrow = self.data.arrow
            aw = max(p[0] for p in arrow)
            for cx, mirror in ((428, True), (507, False)):
                h = 36.0
                pp = [((cx + (((aw - x) if mirror else x) - aw / 2) * h), 684 + (y - 0.5) * h) for x, y in arrow]
                out.append(("poly", pp, UI_CYAN, UI_CYAN, 1))
            out.append(("text", 735, 684, "HINT", 17, UI_CYAN, "center", True))
        if self.state in ("paused", "howto"):
            out.append(("rect", 17, 20, 23, 40, PAUSE_TEXT, PAUSE_TEXT))                  # pause icon + 'Paused' tag
            out.append(("rect", 30, 20, 36, 40, PAUSE_TEXT, PAUSE_TEXT))
            out.append(("text", 63, 30, "Paused", 15, PAUSE_TEXT, "w", False))
        if self.state == "paused":
            for (key, text), (ya, yb) in zip(MENU_ITEMS, MENU_Y):
                cy = (ya + yb) / 2.0
                muted = (key == "mute_sound" and self.sound_muted) or (key == "mute_music" and self.music_muted)
                out.extend(menu_icon(key, 273, cy, UI_CYAN, muted))
                out.append(("text", 313, cy, self.menu_label(key, text), 26, UI_CYAN, "w", False))
        if self.state == "howto":
            out.append(("rect", 150, 130, 794, 590, PANEL, PANEL_EDGE))
            out.append(("text", 472, 190, "How To Play", 28, TITLE, "center", True))
            y = 270
            for line in HOWTO_LINES:
                out.append(("text", 472, y, line, 13, BODY, "center", False))
                y += 48
            out.append(("text", 472, 555, "Click or press P to go back", 12, HUD_TEXT, "center", False))
        if self.state == "solved":
            r = self.last
            out.append(("rect", 222, 503, 722, 607, PANEL, PANEL_EDGE))        # below the silhouette, which stays in the middle half
            out.append(("text", 472, 528, "%s!   +%d points" % (r["rating"], r["points"]), 20, TITLE, "center", True))
            out.append(("text", 472, 559, "Rotations %d (perfect = %d)   Hints %d" % (r["moves"], r["budget"], r["hints"]),
                        11, HUD_TEXT, "center", False))
            more = "Click or press Space to continue" if self.trial < TRIALS_PER_GAME else "Click or press Space for results"
            out.append(("text", 472, 586, more, 11, HUD_TEXT, "center", False))
        if self.state == "summary":
            out.append(("rect", 150, 60, 794, 640, PANEL, PANEL_EDGE))
            out.append(("text", 472, 125, "Game over", 34, TITLE, "center", True))
            out.append(("text", 472, 190, "Total score: %d" % self.referee.total, 24, BODY, "center", True))
            y = 270
            for i, r in enumerate(self.referee.results, 1):
                out.append(("text", 472, y, "Puzzle %d:  %d pieces   rotations %d / %d   %s   +%d" %
                            (i, r["pieces"], r["moves"], r["budget"], r["rating"], r["points"]),
                            13, BODY, "center", False))
                y += 40
            out.append(("text", 472, y + 50, "Click or press Space to play again", 14, HUD_TEXT, "center", False))
        return out

    def scene(self):
        """Everything, in draw order (used by tests and the PNG preview)."""
        return self.static_scene() + self.dynamic_scene()
