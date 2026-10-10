import json
import math
import random
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox


DATA_DIR = Path(__file__).parent / "extraction" / "extract"
PUZZLE_FILE = DATA_DIR / "text_23_silhouettes_csv.txt"
SHAPE_FILE = DATA_DIR / "piece_colliders.json"
BACKGROUND_FILE = DATA_DIR.parent / "media" / "scene" / "textures" / "MasterPieceBG_293.png"
AUDIO_DIR = DATA_DIR.parent / "media" / "scene" / "audio"
SESSION_LENGTH = 4

AUDIO_ALIASES = {
	"Pickup0": ("pickup0", "Pickup0"),
	"Pickup1": ("pickup1", "Pickup1"),
	"Pickup2": ("pickup2", "Pickup2"),
	"Pickup3": ("pickup3", "Pickup3"),
	"Rotation": ("tileRotate08", "Rotation"),
	"Slide": ("woodSlide", "Slide"),
	"Drop": ("drop", "Drop"),
	"Hint": ("hint", "Hint"),
	"AnswerCorrect": ("chimes_AnswerCorrect", "AnswerCorrect"),
	"AnswerExcellent": ("chimes_AnswerExcellent", "AnswerExcellent"),
	"AnswerPerfect": ("chimes_AnswerPerfect", "AnswerPerfect"),
	"Bg1": ("ambient_WindChimes1", "ambient_WindChimes_short", "Bg1"),
	"Bg2": ("ambient_WindChimes2", "Bg2"),
	"Bg3": ("ambient_WindChimes_short", "Bg3"),
}

BACKGROUND = "#e9e8e7"
WINDOW_BG = "#1b1d23"
BOARD_WOOD = "#c88a38"
BOARD_WOOD_DARK = "#9d6828"
BOARD_INNER = "#1f2c5c"
INK = "#2e2e36"
MUTED = "#5b6474"
ACCENT = "#32c4ff"
TARGET = "#0d1c48"
PIECE_COLORS = ("#4fbfe1",)
SCENE_HOME_POSITIONS = {
	"Parallelogram": (0.0, -177.0),
	"Square": (-79.0, 168.0),
	"Triangle1": (101.0, -4.0),
	"Triangle11": (-101.0, -189.0),
	"Triangle20": (149.0, 106.0),
	"Triangle40": (14.0, 162.0),
	"Triangle41": (128.0, -149.0),
	"Monarc0": (41.0, 224.0),
	"Monarc1": (-36.2, 198.0),
	"Diarc0": (129.0, -189.0),
	"Diarc1": (133.0, 185.0),
	"Diarc2": (9.0, -213.0),
	"Diarc3": (-138.0, 179.0),
	"Diarc4": (132.0, -29.0),
	"Diarc5": (-143.0, 6.0),
	"Diarc6": (-96.0, -190.0),
	"Polyiamond40": (-121.0, 194.0),
	"Polyiamond41": (1.0, 171.0),
	"Polyiamond42": (125.0, 180.0),
	"Polyiamond50": (98.0, -127.0),
	"Polyiamond51": (-2.0, -219.0),
	"Polyiamond52": (-127.0, -207.0),
	"Polyiamond53": (112.2, 34.0),
}
TUTORIAL_STEPS = (
	("Study the silhouette", "Fit every gray piece into the dark target shape."),
	("Move a piece", "Drag one of the scattered pieces toward its matching place."),
	("Turn to fit", "Select a piece and rotate it in 45-degree steps."),
	("Finish with fewer turns", "Use Hint if needed. Fewer rotations and hints preserve your score."),
)


@dataclass
class Piece:
	name: str
	solution_angle: float
	solution_x: float
	solution_y: float
	index: int
	x: float = 0.0
	y: float = 0.0
	angle: float = 0.0
	solved: bool = False
	hinted: bool = False
	home_x: float = 0.0
	home_y: float = 0.0
	at_home: bool = True


@dataclass
class PuzzleDefinition:
	difficulty: int
	pieces: list[tuple[str, float, float, float]]


class GameAudio:
	def __init__(self) -> None:
		self.effects = None
		self.ambient = None
		self._pythoncom = None
		self._ambient_name: str | None = None
		self.muted = False
		try:
			import pythoncom
			import win32com.client

			pythoncom.CoInitialize()
			self._pythoncom = pythoncom
			self.effects = win32com.client.Dispatch("WMPlayer.OCX")
			self.ambient = win32com.client.Dispatch("WMPlayer.OCX")
			self.effects.settings.volume = 45
			self.ambient.settings.volume = 24
			try:
				self.ambient.settings.setMode("loop", True)
			except Exception:
				pass
		except Exception:
			self.effects = None
			self.ambient = None
			if self._pythoncom is not None:
				self._pythoncom.CoUninitialize()
				self._pythoncom = None

	@staticmethod
	def _resolve_clip_name(clip_name: str) -> str | None:
		candidates = AUDIO_ALIASES.get(clip_name, ())
		if not candidates:
			candidates = (clip_name,)
		resolved = [candidate for candidate in candidates if (AUDIO_DIR / f"{candidate}.m4a").is_file()]
		if resolved:
			return resolved[0]
		for path in AUDIO_DIR.glob("*.m4a"):
			name = path.stem.lower()
			if clip_name.lower() == name or clip_name.lower() in name:
				return path.stem
		return None

	def play_effect(self, clip_name: str) -> None:
		resolved = self._resolve_clip_name(clip_name)
		if self.muted or self.effects is None or resolved is None:
			return
		path = AUDIO_DIR / f"{resolved}.m4a"
		try:
			self.effects.URL = str(path)
			self.effects.controls.play()
		except Exception:
			pass

	def play_ambient(self, clip_name: str) -> None:
		self._ambient_name = clip_name
		resolved = self._resolve_clip_name(clip_name)
		if self.muted or self.ambient is None or resolved is None:
			return
		path = AUDIO_DIR / f"{resolved}.m4a"
		try:
			self.ambient.URL = str(path)
			self.ambient.controls.play()
		except Exception:
			pass

	def toggle_mute(self) -> bool:
		self.muted = not self.muted
		if self.muted:
			for player in (self.effects, self.ambient):
				if player is not None:
					try:
						player.controls.stop()
					except Exception:
						pass
		elif self._ambient_name is not None:
			self.play_ambient(self._ambient_name)
		return self.muted

	def close(self) -> None:
		for player in (self.effects, self.ambient):
			if player is not None:
				try:
					player.controls.stop()
				except Exception:
					pass
		self.effects = None
		self.ambient = None
		if self._pythoncom is not None:
			self._pythoncom.CoUninitialize()
			self._pythoncom = None


class MasterpieceGame:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("Masterpiece | Spatial Reasoning")
		self.root.geometry("1365x768")
		self.root.minsize(1180, 700)
		self.root.configure(bg="#d9d8d5")

		try:
			self.shapes = json.loads(SHAPE_FILE.read_text(encoding="utf-8"))
			self.puzzles = self._load_puzzles()
		except (OSError, json.JSONDecodeError, ValueError) as error:
			messagebox.showerror("Masterpiece data not found", str(error))
			root.destroy()
			return

		self.session_round = 0
		self.session_length = SESSION_LENGTH
		self.session_puzzles: list[PuzzleDefinition] = []
		self.score = 0
		self.rotation_count = 0
		self.hints_used = 0
		self.pieces: list[Piece] = []
		self.selected: Piece | None = None
		self.drag_offset = (0.0, 0.0)
		self.dragging = False
		self.finished = False
		self.hint_piece: Piece | None = None
		self.tutorial_window: tk.Toplevel | None = None
		self.audio = GameAudio()
		self.drag_audio_played = False

		self._build_ui()
		self._bind_events()
		self.root.protocol("WM_DELETE_WINDOW", self._on_close)
		self._new_puzzle()
		self.root.after(150, self._show_tutorial)

	def _load_puzzles(self) -> list[PuzzleDefinition]:
		puzzles = []
		for row in PUZZLE_FILE.read_text(encoding="utf-8").splitlines():
			difficulty, encoded_pieces = row.split(",", 1)
			pieces = []
			for item in encoded_pieces.split(";"):
				name, angle, x, y = item.split(":")
				if name not in self.shapes:
					raise ValueError(f"The collider data is missing {name}.")
				pieces.append((name, float(angle), float(x), float(y)))
			puzzles.append(PuzzleDefinition(int(difficulty), pieces))
		if not puzzles:
			raise ValueError("No puzzles were found in the extracted catalog.")
		return puzzles

	def _build_ui(self) -> None:
		header = tk.Frame(self.root, bg=WINDOW_BG, padx=18, pady=10)
		header.pack(fill="x")

		title = tk.Label(
			header, text="MASTERPIECE", bg=WINDOW_BG, fg="#f3f3f3",
			font=("Segoe UI", 16, "bold"),
		)
		title.pack(side="left")
		self.round_label = tk.Label(
			header, bg=WINDOW_BG, fg="#f0f0f0", font=("Segoe UI", 9, "bold"),
		)
		self.round_label.pack(side="left", padx=(16, 0), pady=(4, 0))
		self.score_label = tk.Label(
			header, bg=WINDOW_BG, fg="#f7f7f7", font=("Segoe UI", 10, "bold"),
		)
		self.score_label.pack(side="right", padx=(12, 0))
		self.moves_label = tk.Label(
			header, bg=WINDOW_BG, fg="#dbe8f7", font=("Segoe UI", 9),
		)
		self.moves_label.pack(side="right")
		self._button(header, "Pause", self._show_pause).pack(side="right", padx=(8, 0))
		self.sound_button = self._button(header, "Sound on", self._toggle_sound)
		self.sound_button.pack(side="right", padx=(8, 0))

		self.background_image = None
		if BACKGROUND_FILE.is_file():
			try:
				self.background_image = tk.PhotoImage(file=str(BACKGROUND_FILE))
			except tk.TclError:
				self.background_image = None

		self.canvas = tk.Canvas(
			self.root, bg="#d9d8d5", highlightthickness=0,
			cursor="hand2", width=980, height=560,
		)
		self.canvas.pack(fill="both", expand=True, padx=16, pady=(8, 10))

		controls = tk.Frame(self.root, bg=BACKGROUND, padx=12, pady=4)
		controls.pack(fill="x")
		self.mode_var = tk.StringVar(value="normal")
		for label, value in (("Normal (4)", "normal"), ("Short (1)", "short")):
			tk_button = tk.Radiobutton(
				controls, text=label, variable=self.mode_var, value=value,
				command=self._change_mode, indicatoron=False, relief="flat", bd=0,
				bg="#e7e7e4", fg=INK, selectcolor="#ffffff",
				activebackground="#dce8f7", padx=12, pady=8,
				font=("Segoe UI", 9, "bold"), cursor="hand2",
			)
			tk_button.pack(side="left", padx=(0, 4))
		self._button(controls, "Rotate left", lambda: self._rotate(45)).pack(side="left")
		self._button(controls, "Rotate right", lambda: self._rotate(-45)).pack(side="left", padx=8)
		self._button(controls, "Hint", self._show_hint, accent=True).pack(side="left", padx=(8, 0))
		self.next_button = self._button(controls, "Next puzzle", self._advance)
		self.next_button.pack(side="right")
		self.next_button.configure(state="disabled")
		self._button(controls, "How to play", self._show_tutorial).pack(side="right", padx=8)
		self.status_label = tk.Label(
			self.root, text="Drag the gray pieces into the shaded silhouette. Right-click or use Rotate to turn one.",
			bg="#d9d8d5", fg=INK, anchor="w", padx=18, pady=8,
			font=("Segoe UI", 10),
		)
		self.status_label.pack(fill="x")

	def _button(self, parent: tk.Widget, text: str, command, accent: bool = False) -> tk.Button:
		background = ACCENT if accent else "#ffffff"
		foreground = "#ffffff" if accent else INK
		return tk.Button(
			parent, text=text, command=command, bg=background, fg=foreground,
			activebackground=ACCENT if accent else "#e7e7e4",
			activeforeground="#ffffff" if accent else INK,
			relief="flat", bd=0, padx=14, pady=8,
			font=("Segoe UI", 9, "bold"), cursor="hand2",
		)

	def _bind_events(self) -> None:
		self.canvas.bind("<Configure>", lambda _event: self._draw())
		self.canvas.bind("<ButtonPress-1>", self._on_press)
		self.canvas.bind("<B1-Motion>", self._on_drag)
		self.canvas.bind("<ButtonRelease-1>", self._on_release)
		self.canvas.bind("<Button-3>", lambda _event: self._rotate(-45))
		self.root.bind("r", lambda _event: self._rotate(-45))
		self.root.bind("R", lambda _event: self._rotate(-45))
		self.root.bind("h", lambda _event: self._show_hint())
		self.root.bind("n", lambda _event: self._advance())
		self.root.bind("<Escape>", lambda _event: self._show_pause())

	def _on_close(self) -> None:
		self.audio.close()
		self.root.destroy()

	def _toggle_sound(self) -> None:
		muted = self.audio.toggle_mute()
		self.sound_button.configure(text="Sound off" if muted else "Sound on")

	def _show_pause(self) -> None:
		window = tk.Toplevel(self.root)
		window.title("Paused")
		window.geometry("300x330")
		window.resizable(False, False)
		window.configure(bg=BACKGROUND)
		window.transient(self.root)
		window.protocol("WM_DELETE_WINDOW", lambda: self._close_pause(window))
		window.grab_set()
		tk.Label(window, text="PAUSED", bg=BACKGROUND, fg=INK,
				 font=("Segoe UI", 16, "bold")).pack(pady=(24, 18))
		self._button(window, "Resume", lambda: self._close_pause(window), accent=True).pack(fill="x", padx=32, pady=5)
		self._button(
			window, "Restart trial",
			lambda: self._restart_from_pause(window),
		).pack(fill="x", padx=32, pady=5)
		sound_button = self._button(
			window, "Sound off" if self.audio.muted else "Sound on",
			lambda: None,
		)
		sound_button.configure(command=lambda: self._toggle_pause_sound(sound_button))
		sound_button.pack(fill="x", padx=32, pady=5)
		self._button(window, "Quit", self._on_close).pack(fill="x", padx=32, pady=(5, 20))

	def _toggle_pause_sound(self, button: tk.Button) -> None:
		self._toggle_sound()
		button.configure(text="Sound off" if self.audio.muted else "Sound on")

	def _close_pause(self, window: tk.Toplevel) -> None:
		if window.winfo_exists():
			window.grab_release()
			window.destroy()

	def _restart_from_pause(self, window: tk.Toplevel) -> None:
		self._close_pause(window)
		if self.current_puzzle is not None:
			self.session_round -= 1
			self.session_puzzles.insert(0, self.current_puzzle)
			self._new_puzzle()

	def _show_tutorial(self) -> None:
		if self.tutorial_window is not None and self.tutorial_window.winfo_exists():
			self.tutorial_window.lift()
			return
		self.tutorial_index = 0
		window = tk.Toplevel(self.root)
		self.tutorial_window = window
		window.title("How to play")
		window.geometry("470x280")
		window.resizable(False, False)
		window.configure(bg=BACKGROUND)
		window.transient(self.root)
		window.protocol("WM_DELETE_WINDOW", self._close_tutorial)
		window.grab_set()

		tk.Label(window, text="MASTERPIECE", bg=BACKGROUND, fg=ACCENT,
				 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=28, pady=(24, 8))
		self.tutorial_title = tk.Label(
			window, bg=BACKGROUND, fg=INK, font=("Segoe UI", 17, "bold"), anchor="w",
		)
		self.tutorial_title.pack(fill="x", padx=28)
		self.tutorial_body = tk.Label(
			window, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 11),
			anchor="w", justify="left", wraplength=410,
		)
		self.tutorial_body.pack(fill="x", padx=28, pady=(10, 18))
		self.tutorial_progress = tk.Label(
			window, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 9),
		)
		self.tutorial_progress.pack(side="left", padx=28)
		buttons = tk.Frame(window, bg=BACKGROUND)
		buttons.pack(side="right", padx=24, pady=(0, 18))
		self._button(buttons, "Skip", self._close_tutorial).pack(side="left", padx=(0, 8))
		self._button(buttons, "Back", self._previous_tutorial).pack(side="left", padx=(0, 8))
		self._button(buttons, "Continue", self._next_tutorial, accent=True).pack(side="left")
		self._update_tutorial()

	def _update_tutorial(self) -> None:
		title, body = TUTORIAL_STEPS[self.tutorial_index]
		self.tutorial_title.configure(text=title)
		self.tutorial_body.configure(text=body)
		self.tutorial_progress.configure(text=f"{self.tutorial_index + 1} / {len(TUTORIAL_STEPS)}")

	def _previous_tutorial(self) -> None:
		self.tutorial_index = max(0, self.tutorial_index - 1)
		self._update_tutorial()

	def _next_tutorial(self) -> None:
		if self.tutorial_index == len(TUTORIAL_STEPS) - 1:
			self._close_tutorial()
			return
		self.tutorial_index += 1
		self._update_tutorial()

	def _close_tutorial(self) -> None:
		if self.tutorial_window is not None and self.tutorial_window.winfo_exists():
			self.tutorial_window.grab_release()
			self.tutorial_window.destroy()
		self.tutorial_window = None

	def _new_puzzle(self) -> None:
		self.session_round += 1
		if not self.session_puzzles:
			groups = sorted({puzzle.difficulty for puzzle in self.puzzles})
			if self.session_length == 1:
				group_indexes = [len(groups) // 2]
			else:
				group_indexes = [
					round((index + 1) * (len(groups) - 1) / self.session_length)
					for index in range(self.session_length)
				]
			self.session_puzzles = [
				random.choice([puzzle for puzzle in self.puzzles if puzzle.difficulty == groups[group_index]])
				for group_index in group_indexes
			]
		source = self.session_puzzles.pop(0)
		self.current_puzzle = source
		self.current_difficulty = source.difficulty
		self.pieces = [
			Piece(
				name, angle, x, y, index,
				home_x=SCENE_HOME_POSITIONS[name][0],
				home_y=SCENE_HOME_POSITIONS[name][1],
			)
			for index, (name, angle, x, y) in enumerate(source.pieces)
		]
		self.rotation_count = 0
		self.hints_used = 0
		self.selected = None
		self.hint_piece = None
		self.finished = False
		self.next_button.configure(state="disabled", text="Next puzzle")
		self.status_label.configure(
			text="Drag the gray pieces into the shaded silhouette. Right-click or use Rotate to turn one."
		)
		self.audio.play_ambient("Bg3" if self.session_length == 1 else "Bg1")
		self._update_labels()
		self._draw()

	def _advance(self) -> None:
		if not self.finished:
			return
		if self.session_round >= self.session_length:
			self.session_round = 0
			self.score = 0
			self.session_puzzles.clear()
			self._new_puzzle()
			self.status_label.configure(text="New session. Build the silhouette using every piece.")
			return
		self._new_puzzle()

	def _change_mode(self) -> None:
		self.session_length = 1 if self.mode_var.get() == "short" else SESSION_LENGTH
		self.session_round = 0
		self.score = 0
		self.session_puzzles.clear()
		self._new_puzzle()
		mode_name = "Short game" if self.session_length == 1 else "Normal game"
		self.status_label.configure(text=f"{mode_name} started. Build the silhouette using every piece.")

	def _update_labels(self) -> None:
		self.round_label.configure(
			text=f"TRIAL {self.session_round} / {self.session_length}   LEVEL {self.current_difficulty}"
		)
		self.score_label.configure(text=f"SCORE  {self.score:,}")
		self.moves_label.configure(text=f"ROTATIONS  {self.rotation_count}")

	def _board_geometry(self) -> tuple[float, float, float]:
		width = max(self.canvas.winfo_width(), 600)
		height = max(self.canvas.winfo_height(), 700)
		points = [point for piece in self.pieces for point in self._world_points(piece)]
		for piece in self.pieces:
			for polygon in self.shapes[piece.name]:
				points.extend((piece.home_x + x, piece.home_y + y) for x, y in polygon)
		min_x = min(point[0] for point in points)
		max_x = max(point[0] for point in points)
		min_y = min(point[1] for point in points)
		max_y = max(point[1] for point in points)
		board_width = width - 48
		board_height = height - 72
		scale = min(1.2, board_width / max(max_x - min_x, 1), board_height / max(max_y - min_y, 1))
		center_x = width / 2
		center_y = height / 2
		return scale, center_x, center_y

	def _world_points(self, piece: Piece) -> list[tuple[float, float]]:
		angle = math.radians(piece.solution_angle)
		cos_a, sin_a = math.cos(angle), math.sin(angle)
		points = []
		for polygon in self.shapes[piece.name]:
			for x, y in polygon:
				points.append((piece.solution_x + x * cos_a - y * sin_a,
							   piece.solution_y + x * sin_a + y * cos_a))
		return points

	def _screen_point(self, x: float, y: float, scale: float, center_x: float, center_y: float) -> tuple[float, float]:
		origin_x, origin_y = self._display_origin
		return center_x + (x - origin_x) * scale, center_y - (y - origin_y) * scale

	def _draw(self) -> None:
		if not hasattr(self, "canvas") or not self.pieces:
			return
		self.canvas.delete("all")
		width = max(self.canvas.winfo_width(), 600)
		height = max(self.canvas.winfo_height(), 500)
		self.canvas.create_rectangle(0, 0, width, height, fill=BACKGROUND, outline="")

		board_left = max(80, (width - 720) / 2)
		board_top = max(10, (height - 430) / 2)
		board_right = board_left + 720
		board_bottom = board_top + 430
		self.canvas.create_rectangle(board_left - 18, board_top - 18,
								 board_right + 18, board_bottom + 18,
								 fill="#8a4d11", outline="#8a4d11", width=2)
		self.canvas.create_rectangle(board_left, board_top,
								 board_right, board_bottom,
								 fill=BOARD_WOOD, outline="#8a4d11", width=3)
		self.canvas.create_rectangle(board_left + 12, board_top + 12,
								 board_right - 12, board_bottom - 12,
								 fill=BOARD_INNER, outline="#2a3b70", width=2)
		if self.background_image is not None:
			image_width = self.background_image.width()
			image_height = self.background_image.height()
			for y in range(int(board_top), int(board_bottom), max(16, image_height)):
				for x in range(int(board_left), int(board_right), max(16, image_width)):
					self.canvas.create_image(x, y, image=self.background_image, anchor="nw")
		scale, center_x, center_y = self._board_geometry()
		all_points = [point for piece in self.pieces for point in self._world_points(piece)]
		min_x = min(point[0] for point in all_points)
		max_x = max(point[0] for point in all_points)
		min_y = min(point[1] for point in all_points)
		max_y = max(point[1] for point in all_points)
		self._display_origin = ((min_x + max_x) / 2, (min_y + max_y) / 2)

		self._draw_target(scale, center_x, center_y)
		for piece in self.pieces:
			if piece.solved:
				self._draw_piece(piece, scale, center_x, center_y,
								 PIECE_COLORS[0], "#1f5c7a", 1,
								 solution=True)
		if self.hint_piece is not None:
			self._draw_piece(self.hint_piece, scale, center_x, center_y, "", ACCENT, 5, solution=True)

		for piece in self.pieces:
			if piece.solved or piece is self.selected:
				continue
			if piece.at_home:
				piece.x, piece.y = self._screen_point(
					piece.home_x, piece.home_y, scale, center_x, center_y
				)
			self._draw_piece(piece, scale, center_x, center_y,
							 PIECE_COLORS[0], "#1b7e9b", 1)

		if self.selected is not None and not self.selected.solved:
			self._draw_piece(self.selected, scale, center_x, center_y,
							 "#64d8f7", "#246f8d", 2)
			radius = max(5, 7 * scale)
			self.canvas.create_oval(
				self.selected.x - radius, self.selected.y - radius,
				self.selected.x + radius, self.selected.y + radius,
				fill="#eeeeee", outline=INK, width=1,
			)

	def _draw_target(self, scale: float, center_x: float, center_y: float) -> None:
		for piece in self.pieces:
			for polygon in self.shapes[piece.name]:
				coords = []
				angle = math.radians(piece.solution_angle)
				for x, y in polygon:
					world_x = piece.solution_x + x * math.cos(angle) - y * math.sin(angle)
					world_y = piece.solution_y + x * math.sin(angle) + y * math.cos(angle)
					screen_x, screen_y = self._screen_point(world_x, world_y, scale, center_x, center_y)
					coords.extend((screen_x, screen_y))
				self.canvas.create_polygon(coords, fill=TARGET, outline=TARGET, width=1)

	def _draw_piece(self, piece: Piece, scale: float, center_x: float, center_y: float,
					fill: str, outline: str, line_width: int, solution: bool = False,
					tray_scale: float = 1.0) -> None:
		if solution:
			draw_x, draw_y, angle = piece.solution_x, piece.solution_y, piece.solution_angle
		else:
			draw_x, draw_y, angle = piece.x, piece.y, piece.angle
		angle_radians = math.radians(angle)
		cos_a, sin_a = math.cos(angle_radians), math.sin(angle_radians)
		for polygon in self.shapes[piece.name]:
			coords = []
			for x, y in polygon:
				local_x = x * cos_a - y * sin_a
				local_y = x * sin_a + y * cos_a
				if solution:
					world_x = draw_x + local_x
					world_y = draw_y + local_y
					screen_x, screen_y = self._screen_point(
						world_x, world_y, scale, center_x, center_y
					)
				else:
					screen_x = draw_x + local_x * scale * tray_scale
					screen_y = draw_y - local_y * scale * tray_scale
				coords.extend((screen_x, screen_y))
			self.canvas.create_polygon(
				coords, fill=fill, outline=outline,
				width=line_width, dash=(5, 3) if solution else (),
			)

	def _canvas_scale(self) -> tuple[float, float, float]:
		scale, center_x, center_y = self._board_geometry()
		return scale, center_x, center_y

	def _piece_screen_polygons(self, piece: Piece, tray_scale: float = 1.0) -> list[list[tuple[float, float]]]:
		scale, _, _ = self._canvas_scale()
		angle = math.radians(piece.angle)
		polygons = []
		for polygon in self.shapes[piece.name]:
			converted = []
			for x, y in polygon:
				local_x = x * math.cos(angle) - y * math.sin(angle)
				local_y = x * math.sin(angle) + y * math.cos(angle)
				converted.append((piece.x + local_x * scale * tray_scale,
								  piece.y - local_y * scale * tray_scale))
			polygons.append(converted)
		return polygons

	@staticmethod
	def _contains(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
		x, y = point
		inside = False
		previous = polygon[-1]
		for current in polygon:
			x1, y1 = current
			x2, y2 = previous
			if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
				inside = not inside
			previous = current
		return inside

	def _on_press(self, event: tk.Event) -> None:
		for piece in reversed(self.pieces):
			if piece.solved:
				continue
			if any(self._contains((event.x, event.y), polygon)
				   for polygon in self._piece_screen_polygons(piece)):
				self.selected = piece
				piece.at_home = False
				self.dragging = True
				self.drag_audio_played = False
				self.audio.play_effect(f"Pickup{random.randrange(4)}")
				self.drag_offset = (piece.x - event.x, piece.y - event.y)
				self.hint_piece = None
				self._draw()
				return
		self.selected = None
		self._draw()

	def _on_drag(self, event: tk.Event) -> None:
		if self.selected is None or not self.dragging:
			return
		if not self.drag_audio_played:
			self.audio.play_effect("Slide")
			self.drag_audio_played = True
		self.selected.x = event.x + self.drag_offset[0]
		self.selected.y = event.y + self.drag_offset[1]
		self._draw()

	def _on_release(self, _event: tk.Event) -> None:
		if self.selected is None:
			self.dragging = False
			return
		self.dragging = False
		self.audio.play_effect("Drop")
		piece = self.selected
		scale, center_x, center_y = self._canvas_scale()
		solution_x, solution_y = self._screen_point(
			piece.solution_x, piece.solution_y, scale, center_x, center_y
		)
		tolerance = max(18, 23 * scale)
		position_error = math.hypot(piece.x - solution_x, piece.y - solution_y)
		angle_error = abs((piece.angle - piece.solution_angle + 180) % 360 - 180)
		if position_error <= tolerance and angle_error <= 22.5:
			piece.x = solution_x
			piece.y = solution_y
			piece.angle = piece.solution_angle
			piece.solved = True
			self.selected = None
			self.hint_piece = None
			self.status_label.configure(text=f"{piece.name} placed.")
			if all(item.solved for item in self.pieces):
				self._complete_puzzle()
		else:
			self.status_label.configure(text="Keep adjusting: line up the piece with its place in the silhouette.")
		self._update_labels()
		self._draw()

	def _rotate(self, degrees: float) -> None:
		if self.selected is None or self.selected.solved:
			return
		self.selected.angle = (self.selected.angle + degrees) % 360
		self.rotation_count += 1
		self.audio.play_effect("Rotation")
		self._update_labels()
		self._draw()

	def _show_hint(self) -> None:
		if self.finished:
			return
		piece = next((item for item in self.pieces if not item.solved), None)
		if piece is None:
			return
		self.hints_used += 1
		self.hint_piece = piece
		self.audio.play_effect("Hint")
		self.status_label.configure(text="Hint: the outlined shape shows one piece's target position.")
		self._draw()
		self.root.after(1800, self._clear_hint)

	def _clear_hint(self) -> None:
		self.hint_piece = None
		self._draw()

	def _complete_puzzle(self) -> None:
		self.finished = True
		points = max(80, 300 - self.rotation_count * 8 - self.hints_used * 35)
		self.score += points
		self._update_labels()
		feedback = "PERFECT" if self.rotation_count == 0 and self.hints_used == 0 else "GREAT"
		self.audio.play_effect(
			"AnswerPerfect" if feedback == "PERFECT" else "AnswerExcellent"
		)
		if self.session_round >= self.session_length:
			self.status_label.configure(text=f"{feedback}! Session complete. +{points} points. Final score: {self.score:,}.")
			self.next_button.configure(text="New session", state="normal")
		else:
			self.status_label.configure(text=f"{feedback}! Silhouette complete. +{points} points. {self.session_length - self.session_round} puzzles remain.")
			self.next_button.configure(state="normal")


def main() -> None:
	root = tk.Tk()
	MasterpieceGame(root)
	root.mainloop()


if __name__ == "__main__":
	main()
