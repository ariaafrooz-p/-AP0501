import tkinter as tk
import math


WINDOW_TITLE = "Shape Shift"
BOARD_COLUMNS = 8
BOARD_ROWS = 7
BASE_SHAPES = (
	tuple((1 + math.cos(2 * math.pi * step / 48),
		   1 + math.sin(2 * math.pi * step / 48)) for step in range(48)),
	((0.8, 0), (3, 0), (2.2, 2), (0, 2)),
	((0, 0), (2.4, 0)) + tuple(
		(2.4 * math.cos(math.pi * step / 48), 2.4 * math.sin(math.pi * step / 48))
		for step in range(25)
	),
)
PUZZLE_POSES = (
	(((0, 2), 0), ((2, 2), 0), ((5, 4), 0)),
	(((0, 1), 0), ((4, 0), 1), ((5, 4), 0)),
	(((6, 0), 0), ((0, 4), 2), ((4, 1), 1)),
	(((3, 0), 0), ((0, 2), 3), ((5, 4), 3)),
)
PIECE_COLORS = ("#19c6dc", "#37d0dc", "#00b8cf")


def rotated_outline(points, turns):
	result = tuple(points)
	for _ in range(turns % 4):
		min_x = min(x for x, _ in result)
		min_y = min(y for _, y in result)
		max_y = max(y for _, y in result)
		result = tuple((max_y - y + min_x, x - min_x + min_y) for x, y in result)
	min_x = min(x for x, _ in result)
	min_y = min(y for _, y in result)
	return tuple((round(x - min_x, 5), round(y - min_y, 5)) for x, y in result)


def outline_size(points):
	return max(x for x, _ in points), max(y for _, y in points)


class ShapeShift:
	def __init__(self, root):
		self.root = root
		self.root.title(WINDOW_TITLE)
		self.root.geometry("1080x820")
		self.root.minsize(840, 720)
		self.canvas = tk.Canvas(root, highlightthickness=0, background="#f39a12")
		self.canvas.pack(fill="both", expand=True)

		self.puzzle = 0
		self.score = 1000
		self.moves = 0
		self.hints = 0
		self.paused = False
		self.won = False
		self.selected = None
		self.rotations = [0, 0, 0]
		self.placed = {}
		self.history = []
		self.hover_cell = None
		self.message = "Choose a piece, rotate it, then click a target cell."
		self.controls = {}
		self.goal_anchors = []
		self.goal_rotations = []
		self._load_puzzle()

		self.canvas.bind("<Configure>", self._draw)
		self.canvas.bind("<Button-1>", self._click)
		self.canvas.bind("<Motion>", self._motion)
		self.root.bind("<KeyPress-r>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-R>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-Left>", lambda _event: self._rotate(-1))
		self.root.bind("<KeyPress-Right>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-BackSpace>", lambda _event: self._undo())
		self.root.bind("<KeyPress-Escape>", lambda _event: self._toggle_pause())

	def _load_puzzle(self):
		poses = PUZZLE_POSES[self.puzzle]
		self.goal_anchors = [anchor for anchor, _ in poses]
		self.goal_rotations = [rotation for _, rotation in poses]

	def _layout(self):
		width = max(1, self.canvas.winfo_width())
		height = max(1, self.canvas.winfo_height())
		cell = min(66, (height - 330) / BOARD_ROWS, (width - 80) / BOARD_COLUMNS)
		cell = max(44, cell)
		board_width = cell * BOARD_COLUMNS
		board_height = cell * BOARD_ROWS
		board_x = (width - board_width) / 2
		board_y = 100
		tray_y = board_y + board_height + 20
		return width, height, cell, board_x, board_y, tray_y

	def _draw(self, _event=None):
		canvas = self.canvas
		canvas.delete("all")
		self.controls = {}
		width, height, cell, board_x, board_y, tray_y = self._layout()

		self._draw_background(width, height)
		self._draw_header(width)
		self._draw_board(cell, board_x, board_y)
		self._draw_tray(width, height, cell, tray_y)
		self._draw_footer(width, height)

		if self.paused or self.won:
			self._draw_overlay(width, height)

	def _draw_background(self, width, height):
		colors = ("#f39a12", "#f5a016", "#ed8d0c", "#f19a10")
		stripe_height = 24
		for y in range(0, height, stripe_height):
			color = colors[(y // stripe_height) % len(colors)]
			self.canvas.create_rectangle(0, y, width, y + stripe_height, fill=color, outline="")
		self.canvas.create_rectangle(0, height - 92, width, height, fill="#9b4d00", outline="")
		self.canvas.create_line(0, height - 92, width, height - 92, fill="#c16b05", width=3)

	def _draw_header(self, width):
		canvas = self.canvas
		canvas.create_rectangle(0, 0, width, 62, fill="#9c5107", outline="")
		canvas.create_text(26, 30, text="Ⅱ", fill="#19c6dc", font=("Segoe UI", 23, "bold"))
		canvas.create_text(72, 31, text="SHAPE SHIFT", anchor="w", fill="#fff1cb",
						   font=("Segoe UI", 16, "bold"))
		canvas.create_rectangle(width - 300, 0, width - 152, 62, fill="#f6c875", outline="#b66a13")
		canvas.create_text(width - 226, 31, text=f"PUZZLE  {self.puzzle + 1} / 4",
						   fill="#653800", font=("Segoe UI", 13, "bold"))
		canvas.create_rectangle(width - 152, 0, width, 62, fill="#f6c875", outline="#b66a13")
		canvas.create_text(width - 76, 17, text="SCORE", fill="#80501a", font=("Segoe UI", 10, "bold"))
		canvas.create_text(width - 76, 41, text=str(self.score), fill="#56320d",
						   font=("Segoe UI", 17, "bold"))
		self.controls["pause"] = (0, 0, 50, 62)

	def _draw_board(self, cell, board_x, board_y):
		canvas = self.canvas
		board_right = board_x + BOARD_COLUMNS * cell
		board_bottom = board_y + BOARD_ROWS * cell
		canvas.create_rectangle(board_x - 16, board_y - 18, board_right + 16, board_bottom + 18,
								fill="#965006", outline="#713900", width=2)
		canvas.create_rectangle(board_x - 7, board_y - 9, board_right + 7, board_bottom + 9,
								fill="#19244c", outline="#293d80", width=2)

		for row in range(BOARD_ROWS):
			for column in range(BOARD_COLUMNS):
				x1 = board_x + column * cell
				y1 = board_y + row * cell
				fill = "#263f91" if (row + column) % 2 else "#21377f"
				canvas.create_rectangle(x1, y1, x1 + cell, y1 + cell,
									fill=fill, outline="#1b2d6e", width=2)

		for index, (anchor, rotation) in enumerate(zip(self.goal_anchors, self.goal_rotations)):
			self._draw_shape(index, anchor, rotation, cell, board_x, board_y,
							 "#111a3a", outline="#5265a5", width=2)

		for index, (anchor, rotation) in self.placed.items():
			self._draw_shape(index, anchor, rotation, cell, board_x, board_y,
							 PIECE_COLORS[index], outline="#e7fbff", width=3)

		if self.selected is not None and self.hover_cell is not None and not self.won:
			index = self.selected
			anchor = self.hover_cell
			valid = self._pose_is_goal(index, anchor, self.rotations[index])
			self._draw_shape(index, anchor, self.rotations[index], cell, board_x, board_y,
							 "#40dfeb" if valid else "#e95747", outline="#e7fbff",
							 width=2, stipple="gray50")

	def _draw_shape(self, index, anchor, rotation, scale, origin_x, origin_y,
					 color, outline, width=2, stipple=None):
		points = rotated_outline(BASE_SHAPES[index], rotation)
		coordinates = []
		for x, y in points:
			coordinates.extend((origin_x + (anchor[0] + x) * scale,
								origin_y + (anchor[1] + y) * scale))
		options = {"fill": color, "outline": outline, "width": width}
		if stipple:
			options["stipple"] = stipple
		self.canvas.create_polygon(*coordinates, **options)

	def _pose_is_goal(self, index, anchor, rotation):
		if anchor != self.goal_anchors[index]:
			return False
		return index == 0 or rotation % 4 == self.goal_rotations[index]

	def _draw_tray(self, width, height, cell, tray_y):
		canvas = self.canvas
		canvas.create_text(width / 2, tray_y, text=self.message, fill="#fff0d0",
						   font=("Segoe UI", 11, "bold"))
		slot_top = tray_y + 18
		slot_bottom = min(slot_top + 91, height - 106)
		slot_width = min(178, (width - 60) / 3)
		gap = 12
		total = slot_width * 3 + gap * 2
		start_x = (width - total) / 2
		for index, _shape in enumerate(BASE_SHAPES):
			x1 = start_x + index * (slot_width + gap)
			x2 = x1 + slot_width
			selected = index == self.selected
			canvas.create_rectangle(x1, slot_top, x2, slot_bottom,
									fill="#803f08" if selected else "#a95705",
									outline="#f6c875" if selected else "#c57815", width=3 if selected else 2)
			if index in self.placed:
				canvas.create_text((x1 + x2) / 2, (slot_top + slot_bottom) / 2,
								   text="PLACED", fill="#d5b582", font=("Segoe UI", 11, "bold"))
			else:
				points = rotated_outline(BASE_SHAPES[index], self.rotations[index])
				shape_width, shape_height = outline_size(points)
				icon_scale = min(20, 58 / max(shape_width, shape_height))
				origin_x = (x1 + x2 - shape_width * icon_scale) / 2
				origin_y = (slot_top + slot_bottom - shape_height * icon_scale) / 2 - 4
				self._draw_shape(index, (0, 0), self.rotations[index], icon_scale,
							 origin_x, origin_y, PIECE_COLORS[index], outline="#e7fbff", width=2)
			canvas.create_text((x1 + x2) / 2, slot_bottom - 10, text=f"PIECE {index + 1}",
							   fill="#ffe1a8", font=("Segoe UI", 8, "bold"))
			self.controls[f"piece_{index}"] = (x1, slot_top, x2, slot_bottom)

	def _draw_footer(self, width, height):
		canvas = self.canvas
		canvas.create_text(36, height - 45, text=f"{len(self.placed)} of 3", anchor="w",
						   fill="#f4d29a", font=("Segoe UI", 16))
		labels = (("undo", "UNDO"), ("left", "ROTATE -"), ("right", "ROTATE +"), ("hint", "HINT"))
		button_width = 112
		button_gap = 10
		total = len(labels) * button_width + (len(labels) - 1) * button_gap
		start_x = (width - total) / 2
		top = height - 72
		for index, (key, label) in enumerate(labels):
			x1 = start_x + index * (button_width + button_gap)
			x2 = x1 + button_width
			enabled = key in ("undo", "hint") or self.selected is not None
			fill = "#a85808" if enabled else "#79420d"
			text_color = "#28c5dc" if key in ("left", "right", "hint") else "#f6d7a3"
			canvas.create_rectangle(x1, top, x2, height - 18, fill=fill, outline="#c97714", width=2)
			canvas.create_text((x1 + x2) / 2, (top + height - 18) / 2, text=label,
							   fill=text_color, font=("Segoe UI", 10, "bold"))
			self.controls[key] = (x1, top, x2, height - 18)

	def _draw_overlay(self, width, height):
		canvas = self.canvas
		canvas.create_rectangle(0, 62, width, height - 92, fill="#111a37", stipple="gray50", outline="")
		center_x = width / 2
		center_y = height / 2
		if self.paused:
			title, subtitle, button = "PAUSED", "Take a breath. The pieces will wait.", "RESUME"
		elif self.puzzle < 3:
			title, subtitle, button = "PUZZLE COMPLETE", "The whole shape is filled.", "NEXT PUZZLE"
		else:
			title, subtitle, button = "ALL FOUR COMPLETE", f"Final score: {self.score}", "PLAY AGAIN"
		canvas.create_text(center_x, center_y - 52, text=title, fill="#fff1cb",
						   font=("Segoe UI", 25, "bold"))
		canvas.create_text(center_x, center_y - 14, text=subtitle, fill="#a8dfe6",
						   font=("Segoe UI", 12))
		x1, y1, x2, y2 = center_x - 94, center_y + 18, center_x + 94, center_y + 64
		canvas.create_rectangle(x1, y1, x2, y2, fill="#0c9fb7", outline="#a9f6ff", width=2)
		canvas.create_text(center_x, (y1 + y2) / 2, text=button, fill="white",
						   font=("Segoe UI", 11, "bold"))
		self.controls["overlay"] = (x1, y1, x2, y2)

	def _cell_at(self, x, y):
		_, _, cell, board_x, board_y, _ = self._layout()
		column = int((x - board_x) // cell)
		row = int((y - board_y) // cell)
		if 0 <= column < BOARD_COLUMNS and 0 <= row < BOARD_ROWS:
			return column, row
		return None

	def _inside(self, point, bounds):
		x1, y1, x2, y2 = bounds
		return x1 <= point[0] <= x2 and y1 <= point[1] <= y2

	def _click(self, event):
		point = (event.x, event.y)
		if "overlay" in self.controls and self._inside(point, self.controls["overlay"]):
			if self.paused:
				self.paused = False
				self.message = "Choose a piece, rotate it, then click a target cell."
			elif self.puzzle == 3:
				self.puzzle = 0
				self.score = 1000
				self.moves = 0
				self.hints = 0
				self.won = False
				self._reset_puzzle()
			else:
				self.puzzle += 1
				self.won = False
				self._reset_puzzle()
			self._draw()
			return

		if self.paused or self.won:
			return
		if self._inside(point, self.controls["pause"]):
			self._toggle_pause()
			return
		for index in range(3):
			key = f"piece_{index}"
			if self._inside(point, self.controls[key]) and index not in self.placed:
				self.selected = index
				self.message = f"Piece {index + 1} selected. Rotate it, then choose its target position."
				self._draw()
				return
		for key, action in (("undo", self._undo), ("left", lambda: self._rotate(-1)),
							("right", lambda: self._rotate(1)), ("hint", self._hint)):
			if self._inside(point, self.controls[key]):
				action()
				return
		cell = self._cell_at(event.x, event.y)
		if cell is not None and self.selected is not None:
			self._place(self.selected, cell, self.rotations[self.selected])

	def _motion(self, event):
		self.hover_cell = self._cell_at(event.x, event.y)
		self._draw()

	def _rotate(self, direction):
		if self.selected is None or self.paused or self.won:
			return
		self.rotations[self.selected] = (self.rotations[self.selected] + direction) % 4
		self.message = f"Piece {self.selected + 1} rotated. Click a target cell to place it."
		self._draw()

	def _place(self, index, anchor, rotation, is_hint=False):
		if not self._pose_is_goal(index, anchor, rotation):
			self.message = "That shape does not match this target yet. Move or rotate its outline."
			self._draw()
			return False

		old_rotation = self.rotations[index]
		self.history.append((index, old_rotation))
		self.rotations[index] = rotation
		self.placed[index] = (anchor, rotation)
		self.selected = None
		self.moves += 1
		if is_hint:
			self.hints += 1
		self.score = max(0, 1000 - self.moves * 15 - self.hints * 100)
		if len(self.placed) == len(BASE_SHAPES):
			self.won = True
			self.message = "Puzzle complete!"
		else:
			self.message = "Piece placed. Choose another piece."
		self._draw()
		return True

	def _undo(self):
		if self.paused or self.won or not self.history:
			return
		index, old_rotation = self.history.pop()
		self.placed.pop(index, None)
		self.rotations[index] = old_rotation
		self.selected = index
		self.moves = max(0, self.moves - 1)
		self.message = f"Piece {index + 1} returned to the tray."
		self._draw()

	def _hint(self):
		if self.paused or self.won:
			return
		index = next((piece for piece in range(3) if piece not in self.placed), None)
		if index is None:
			return
		self._place(index, self.goal_anchors[index], self.goal_rotations[index], is_hint=True)

	def _toggle_pause(self):
		if self.won:
			return
		self.paused = not self.paused
		self._draw()

	def _reset_puzzle(self):
		self.selected = None
		self.rotations = [0, 0, 0]
		self.placed = {}
		self.history = []
		self.hover_cell = None
		self.message = "Choose a piece, rotate it, then click a target cell."
		self._load_puzzle()
		self._draw()


if __name__ == "__main__":
	window = tk.Tk()
	ShapeShift(window)
	window.mainloop()
