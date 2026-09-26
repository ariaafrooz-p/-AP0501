import tkinter as tk
import math
import random
from collections import deque


WINDOW_TITLE = "Shape Shift"
BOARD_COLUMNS = 8
BOARD_ROWS = 7
PIECE_COLORS = ("#19c6dc", "#39d4df", "#09b9cc", "#f5c451", "#f17660", "#80d99c")


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


def make_target_outline(piece_count):
	vertex_count = max(16, piece_count * 5)
	center_x = BOARD_COLUMNS / 2
	center_y = BOARD_ROWS / 2
	radius_x = random.uniform(2.05, 2.55)
	radius_y = random.uniform(1.9, 2.65)
	phase = random.uniform(0, 2 * math.pi)
	points = []
	for index in range(vertex_count):
		angle = phase + 2 * math.pi * index / vertex_count
		radius = random.uniform(0.68, 1.0)
		points.append((
			round(center_x + radius_x * radius * math.cos(angle), 5),
			round(center_y + radius_y * radius * math.sin(angle), 5),
		))
	return tuple(points)


def polygon_area(points):
	return sum(
		points[index][0] * points[(index + 1) % len(points)][1]
		- points[(index + 1) % len(points)][0] * points[index][1]
		for index in range(len(points))
	) / 2


def cross_product(origin, first, second):
	return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])


def point_in_triangle(point, first, second, third):
	return all(
		cross_product(start, end, point) >= -1e-8
		for start, end in ((first, second), (second, third), (third, first))
	)


def triangulate_polygon(points):
	vertices = list(points)
	if polygon_area(vertices) < 0:
		vertices.reverse()
	remaining = list(range(len(vertices)))
	triangles = []
	while len(remaining) > 3:
		for position, current in enumerate(remaining):
			previous = remaining[position - 1]
			following = remaining[(position + 1) % len(remaining)]
			triangle = (vertices[previous], vertices[current], vertices[following])
			if cross_product(*triangle) <= 1e-8:
				continue
			if any(
				point_in_triangle(vertices[other], *triangle)
				for other in remaining
				if other not in (previous, current, following)
			):
				continue
			triangles.append(triangle)
			remaining.pop(position)
			break
		else:
			raise ValueError("Could not slice the target outline into triangles")
	triangles.append(tuple(vertices[index] for index in remaining))
	return triangles


def refine_long_edges(triangles, maximum_length):
	if not any(
		math.dist(triangle[index], triangle[(index + 1) % 3]) > maximum_length
		for triangle in triangles
		for index in range(3)
	):
		return list(triangles)

	segments = 3
	refined = []
	for first, second, third in triangles:
		def lattice_point(row, offset):
			second_weight = offset / segments
			third_weight = row / segments
			return (
				round(first[0] * (1 - second_weight - third_weight)
					  + second[0] * second_weight + third[0] * third_weight, 10),
				round(first[1] * (1 - second_weight - third_weight)
					  + second[1] * second_weight + third[1] * third_weight, 10),
			)

		for row in range(segments):
			for offset in range(segments - row):
				upper_left = lattice_point(row, offset)
				upper_right = lattice_point(row, offset + 1)
				lower_left = lattice_point(row + 1, offset)
				refined.append((upper_left, upper_right, lower_left))
				if offset < segments - row - 1:
					lower_right = lattice_point(row + 1, offset + 1)
					refined.append((upper_right, lower_right, lower_left))
	return refined


def mesh_diameter(triangles):
	vertices = {point for triangle in triangles for point in triangle}
	return max(
		(math.dist(first, second) for first in vertices for second in vertices),
		default=0,
	)


def mesh_span(triangles):
	vertices = {point for triangle in triangles for point in triangle}
	width = max(x for x, _ in vertices) - min(x for x, _ in vertices)
	height = max(y for _, y in vertices) - min(y for _, y in vertices)
	return max(width, height)


def triangles_share_side(first_triangle, second_triangle):
	for first_index, first_start in enumerate(first_triangle):
		first_end = first_triangle[(first_index + 1) % 3]
		first_dx = first_end[0] - first_start[0]
		first_dy = first_end[1] - first_start[1]
		first_length = math.hypot(first_dx, first_dy)
		for second_index, second_start in enumerate(second_triangle):
			second_end = second_triangle[(second_index + 1) % 3]
			if abs(cross_product(first_start, first_end, second_start)) > 1e-7:
				continue
			if abs(cross_product(first_start, first_end, second_end)) > 1e-7:
				continue
			if abs(first_dx) >= abs(first_dy):
				first_interval = sorted((first_start[0], first_end[0]))
				second_interval = sorted((second_start[0], second_end[0]))
			else:
				first_interval = sorted((first_start[1], first_end[1]))
				second_interval = sorted((second_start[1], second_end[1]))
			if min(first_interval[1], second_interval[1]) - max(first_interval[0], second_interval[0]) > 1e-7:
				return True
	return False


def graph_articulation_points(adjacency, members):
	discovery = {}
	low = {}
	parent = {}
	articulation_points = set()
	time = 0

	def visit(node):
		nonlocal time
		discovery[node] = low[node] = time
		time += 1
		children = 0
		for neighbor in adjacency[node] & members:
			if neighbor not in discovery:
				parent[neighbor] = node
				children += 1
				visit(neighbor)
				low[node] = min(low[node], low[neighbor])
				if node not in parent and children > 1:
					articulation_points.add(node)
				elif node in parent and low[neighbor] >= discovery[node]:
					articulation_points.add(node)
			elif parent.get(node) != neighbor:
				low[node] = min(low[node], discovery[neighbor])

	if members:
		visit(next(iter(members)))
	return articulation_points


def slice_into_pieces(triangles, piece_count, minimum_area, corner_index=0):
	adjacency = [set() for _ in triangles]
	edge_owners = {}
	for triangle_index, triangle in enumerate(triangles):
		for edge_index, start in enumerate(triangle):
			end = triangle[(edge_index + 1) % 3]
			key = tuple(sorted((start, end)))
			for neighbor in edge_owners.get(key, ()):
				adjacency[triangle_index].add(neighbor)
				adjacency[neighbor].add(triangle_index)
			edge_owners.setdefault(key, []).append(triangle_index)
	if any(not neighbors for neighbors in adjacency):
		raise ValueError("Target mesh contains an isolated triangle")

	triangle_areas = [abs(polygon_area(triangle)) for triangle in triangles]
	total_area = sum(triangle_areas)
	maximum_area = total_area / piece_count * 1.8
	average_area = total_area / piece_count
	balance_tolerance = average_area * 0.2
	if piece_count == 2:
		centers = [
			(sum(x for x, _ in triangle) / 3, sum(y for _, y in triangle) / 3)
			for triangle in triangles
		]
		if random.random() < 0.2:
			corner_candidates = [
				min(range(len(centers)), key=lambda index: centers[index][0] + centers[index][1]),
				max(range(len(centers)), key=lambda index: centers[index][0] - centers[index][1]),
				max(range(len(centers)), key=lambda index: centers[index][0] + centers[index][1]),
				min(range(len(centers)), key=lambda index: centers[index][0] - centers[index][1]),
			]
			first_seed = corner_candidates[corner_index % len(corner_candidates)]
		else:
			first_seed = random.randrange(len(triangles))
		distances = sorted(
			(
				(math.dist(centers[index], centers[first_seed]), index)
				for index in range(len(triangles)) if index != first_seed
			),
			reverse=True,
		)
		first_middle = len(distances) // 5
		last_middle = max(first_middle + 1, len(distances) * 4 // 5)
		partner_pool = distances[first_middle:last_middle]
		second_seed = random.choice(partner_pool)[1]
		seeds = [first_seed, second_seed]
	else:
		seeds = random.sample(range(len(triangles)), piece_count)
	owners = {seed: group for group, seed in enumerate(seeds)}
	frontier = deque(seeds)
	while frontier:
		triangle_index = frontier.popleft()
		neighbors = list(adjacency[triangle_index])
		random.shuffle(neighbors)
		for neighbor in neighbors:
			if neighbor not in owners:
				owners[neighbor] = owners[triangle_index]
				frontier.append(neighbor)

	group_members = [set() for _ in range(piece_count)]
	group_areas = [0.0] * piece_count
	for triangle_index, group in owners.items():
		group_members[group].add(triangle_index)
		group_areas[group] += triangle_areas[triangle_index]

	for _ in range(len(triangles) * piece_count):
		if all(
			minimum_area <= area <= maximum_area
			and abs(area - average_area) <= balance_tolerance
			for area in group_areas
		):
			break
		articulation_by_group = [
			graph_articulation_points(adjacency, members)
			for members in group_members
		]
		best_move = None
		for donor in range(piece_count):
			for triangle_index in group_members[donor]:
				for neighbor in adjacency[triangle_index]:
					receiver = owners[neighbor]
					if receiver == donor:
						continue
					new_donor_area = group_areas[donor] - triangle_areas[triangle_index]
					new_receiver_area = group_areas[receiver] + triangle_areas[triangle_index]
					if new_donor_area < minimum_area or new_receiver_area > maximum_area:
						continue
					old_error = ((group_areas[donor] - average_area) ** 2
								 + (group_areas[receiver] - average_area) ** 2)
					new_error = ((new_donor_area - average_area) ** 2
								 + (new_receiver_area - average_area) ** 2)
					improvement = old_error - new_error
					if improvement <= 0 or triangle_index in articulation_by_group[donor]:
						continue
					score = improvement + random.random() * average_area ** 2 * 0.01
					if best_move is None or score > best_move[0]:
						best_move = (score, triangle_index, donor, receiver,
									 new_donor_area, new_receiver_area)
		if best_move is None:
			return None
		_, triangle_index, donor, receiver, donor_area, receiver_area = best_move
		owners[triangle_index] = receiver
		group_members[donor].remove(triangle_index)
		group_members[receiver].add(triangle_index)
		group_areas[donor] = donor_area
		group_areas[receiver] = receiver_area
	else:
		return None
	if any(
		area < minimum_area or area > maximum_area
		or abs(area - average_area) > balance_tolerance
		for area in group_areas
	):
		return None

	pieces = [[] for _ in range(piece_count)]
	for triangle_index, triangle in enumerate(triangles):
		pieces[owners[triangle_index]].append(triangle)
	return pieces


def slice_hierarchically(triangles, piece_count, minimum_area):
	groups = [triangles]
	corner_offset = random.randrange(4)
	split_index = 0
	while len(groups) < piece_count:
		splittable = sorted(
			(
				(sum(abs(polygon_area(triangle)) for triangle in group), group)
				for group in groups
				if sum(abs(polygon_area(triangle)) for triangle in group) >= minimum_area * 2
			),
			key=lambda item: item[0],
			reverse=True,
		)
		if not splittable:
			return None
		largest_area = splittable[0][0]
		near_largest = [group for area, group in splittable if area >= largest_area * 0.97]
		candidate = random.choice(near_largest)
		split_result = None
		for attempt in range(100):
			corner = (corner_offset + split_index + attempt) % 4
			children = slice_into_pieces(candidate, 2, minimum_area, corner)
			if children is None:
				continue
			child_areas = [
				sum(abs(polygon_area(triangle)) for triangle in child)
				for child in children
			]
			if all(area >= minimum_area for area in child_areas):
				split_result = children
				break
		if split_result is None:
			return None
		groups.remove(candidate)
		groups.extend(split_result)
		split_index += 1
	return groups


def mesh_boundary_edges(triangles, all_vertices):
	edge_counts = {}
	edge_points = {}
	for triangle in triangles:
		for edge_index, start in enumerate(triangle):
			end = triangle[(edge_index + 1) % 3]
			dx = end[0] - start[0]
			dy = end[1] - start[1]
			length_squared = dx * dx + dy * dy
			points = []
			for point in all_vertices:
				cross = dx * (point[1] - start[1]) - dy * (point[0] - start[0])
				if abs(cross) > 1e-6 * max(1, math.sqrt(length_squared)):
					continue
				parameter = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
				if -1e-7 <= parameter <= 1 + 1e-7:
					points.append((parameter, point))
			points.sort(key=lambda item: item[0])
			for (_, first), (_, second) in zip(points, points[1:]):
				if math.dist(first, second) < 1e-7:
					continue
				key = tuple(sorted((tuple(round(value, 7) for value in first),
									 tuple(round(value, 7) for value in second))))
				edge_counts[key] = edge_counts.get(key, 0) + 1
				edge_points[key] = (first, second)
	return [edge_points[key] for key, count in edge_counts.items() if count == 1]


def partition_signature(groups):
	canonical_groups = []
	for group in groups:
		canonical_triangles = [
			tuple(sorted((round(x, 7), round(y, 7)) for x, y in triangle))
			for triangle in group
		]
		canonical_groups.append(tuple(sorted(canonical_triangles)))
	return tuple(sorted(canonical_groups))


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
		self.mouse_position = (0, 0)
		self.message = "Choose a piece, rotate it, then click a target cell."
		self.controls = {}
		self.goal_anchors = []
		self.goal_rotations = []
		self.last_cut_signature = None
		self._load_puzzle()

		self.canvas.bind("<Configure>", self._draw)
		self.canvas.bind("<Button-1>", self._click)
		self.canvas.bind("<Motion>", self._motion)
		self.canvas.bind("<MouseWheel>", self._on_mousewheel)
		self.canvas.bind("<Button-4>", lambda _event: self._rotate_from_scroll(1))
		self.canvas.bind("<Button-5>", lambda _event: self._rotate_from_scroll(-1))
		self.root.bind("<KeyPress-r>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-R>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-Left>", lambda _event: self._rotate(-1))
		self.root.bind("<KeyPress-Right>", lambda _event: self._rotate(1))
		self.root.bind("<KeyPress-BackSpace>", lambda _event: self._undo())
		self.root.bind("<KeyPress-Escape>", lambda _event: self._toggle_pause())

	def _load_puzzle(self):
		piece_count = self.puzzle + 3
		self.target_outline = make_target_outline(piece_count)
		self.target_triangles = refine_long_edges(
			triangulate_polygon(self.target_outline), maximum_length=2.5
		)
		mesh_vertices = {point for triangle in self.target_triangles for point in triangle}
		target_area = abs(polygon_area(self.target_outline))
		average_piece_area = target_area / piece_count
		minimum_piece_area = average_piece_area * 0.4
		maximum_piece_area = average_piece_area * 1.8
		for _ in range(300):
			triangle_groups = slice_hierarchically(
				self.target_triangles, piece_count, minimum_piece_area
			)
			if triangle_groups is None:
				continue
			piece_areas = [
				sum(abs(polygon_area(triangle)) for triangle in group)
				for group in triangle_groups
			]
			piece_diameters = [mesh_diameter(group) for group in triangle_groups]
			piece_spans = [mesh_span(group) for group in triangle_groups]
			signature = partition_signature(triangle_groups)
			if (signature != self.last_cut_signature
					and all(minimum_piece_area <= area <= maximum_piece_area for area in piece_areas)
					and all(
						diameter <= max(1.5, 4.1 * math.sqrt(area))
						for diameter, area in zip(piece_diameters, piece_areas)
					)
					and all(
						span <= max(1.8, 3.6 * math.sqrt(area))
						for span, area in zip(piece_spans, piece_areas)
					)):
				self.last_cut_signature = signature
				break
		else:
			raise RuntimeError("Could not generate a balanced connected piece layout")
		self.pieces = []
		self.goal_anchors = []
		self.goal_rotations = []
		for group in triangle_groups:
			vertices = [point for triangle in group for point in triangle]
			min_x = min(x for x, _ in vertices)
			min_y = min(y for _, y in vertices)
			local_triangles = [
				tuple((round(x - min_x, 7), round(y - min_y, 7)) for x, y in triangle)
				for triangle in group
			]
			local_vertices = {
				(round(x - min_x, 7), round(y - min_y, 7))
				for x, y in mesh_vertices
			}
			self.pieces.append({
				"triangles": local_triangles,
				"boundary": mesh_boundary_edges(local_triangles, local_vertices),
				"size": (max(x for x, _ in vertices) - min_x,
						 max(y for _, y in vertices) - min_y),
			})
			self.goal_anchors.append((min_x, min_y))
			self.goal_rotations.append(0)
		self.rotations = [random.randint(1, 3) for _ in self.pieces]

	def _layout(self):
		width = max(1, self.canvas.winfo_width())
		height = max(1, self.canvas.winfo_height())
		cell = min(82, (height - 190) / BOARD_ROWS, (width - 24) / 12.4)
		cell = max(48, cell)
		board_width = cell * BOARD_COLUMNS
		board_height = cell * BOARD_ROWS
		board_x = (width - board_width) / 2
		board_y = 70
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
		self._draw_tray(width, height, cell, board_x, board_y)
		self._draw_footer(width, height)

		if self.selected is not None and not self.paused and not self.won:
			self._draw_selected_preview(cell, board_x, board_y)

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
		canvas.create_text(width - 226, 31, text=f"PUZZLE  {self.puzzle + 1}",
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

		self._draw_outline(self.target_outline, cell, board_x, board_y,
						"#111a3a", outline="#111a3a")

		for index, (anchor, rotation) in self.placed.items():
			self._draw_piece(index, anchor, rotation, cell, board_x, board_y,
						  PIECE_COLORS[index % len(PIECE_COLORS)], "#e7fbff")

	def _cursor_anchor(self, index):
		_, _, cell, board_x, board_y, _ = self._layout()
		piece_width, piece_height = self.pieces[index]["size"]
		if self.rotations[index] % 2:
			piece_width, piece_height = piece_height, piece_width
		mouse_x, mouse_y = self.mouse_position
		return (
			(mouse_x - board_x) / cell - piece_width / 2,
			(mouse_y - board_y) / cell - piece_height / 2,
		)

	def _draw_selected_preview(self, cell, board_x, board_y):
		index = self.selected
		anchor = self._preview_anchor(index, self._cursor_anchor(index))
		valid = self._pose_is_goal(index, anchor, self.rotations[index])
		self._draw_piece(index, anchor, self.rotations[index], cell, board_x, board_y,
					  "#40dfeb" if valid else "#e95747", "#e7fbff", stipple="gray50")

	def _transform_point(self, index, point, anchor, rotation):
		x, y = point
		width, height = self.pieces[index]["size"]
		for _ in range(rotation % 4):
			x, y = height - y, x
			width, height = height, width
		return anchor[0] + x, anchor[1] + y

	def _draw_piece(self, index, anchor, rotation, scale, origin_x, origin_y,
					 color, outline, stipple=None):
		piece = self.pieces[index]
		for triangle in piece["triangles"]:
			coordinates = []
			for point in triangle:
				x, y = self._transform_point(index, point, anchor, rotation)
				coordinates.extend((origin_x + x * scale, origin_y + y * scale))
			options = {"fill": color, "outline": color, "width": 1}
			if stipple:
				options["stipple"] = stipple
			self.canvas.create_polygon(*coordinates, **options)
		for start, end in piece["boundary"]:
			first = self._transform_point(index, start, anchor, rotation)
			second = self._transform_point(index, end, anchor, rotation)
			self.canvas.create_line(
				origin_x + first[0] * scale, origin_y + first[1] * scale,
				origin_x + second[0] * scale, origin_y + second[1] * scale,
				fill=outline, width=3, capstyle=tk.ROUND,
			)

	def _preview_anchor(self, index, anchor):
		goal = self.goal_anchors[index]
		if (abs(anchor[0] - goal[0]) <= 0.45 and abs(anchor[1] - goal[1]) <= 0.45
				and self.rotations[index] % 4 == self.goal_rotations[index]):
			return goal
		return anchor

	def _draw_outline(self, points, scale, origin_x, origin_y, color, outline):
		coordinates = []
		for x, y in points:
			coordinates.extend((origin_x + x * scale, origin_y + y * scale))
		self.canvas.create_polygon(*coordinates, fill=color, outline=outline, width=1)

	def _pose_is_goal(self, index, anchor, rotation):
		goal = self.goal_anchors[index]
		return (
			abs(anchor[0] - goal[0]) <= 0.45
			and abs(anchor[1] - goal[1]) <= 0.45
			and rotation % 4 == self.goal_rotations[index]
		)

	def _draw_tray(self, width, height, cell, board_x, board_y):
		canvas = self.canvas
		board_right = board_x + BOARD_COLUMNS * cell
		remaining = [index for index in range(len(self.pieces)) if index not in self.placed]
		columns = (remaining[::2], remaining[1::2])
		for side, indexes in enumerate(columns):
			if not indexes:
				continue
			slot_height = BOARD_ROWS * cell / len(indexes)
			margin_width = board_x - 22 if side == 0 else width - board_right - 22
			for slot, index in enumerate(indexes):
				piece = self.pieces[index]
				piece_width, piece_height = piece["size"]
				if self.rotations[index] % 2:
					piece_width, piece_height = piece_height, piece_width
				display_scale = min(
					cell,
					max(20, margin_width - 12) / max(piece_width, 0.1),
					(slot_height - 12) / max(piece_height, 0.1),
				)
				shape_width = piece_width * display_scale
				shape_height = piece_height * display_scale
				origin_x = board_x - 10 - shape_width if side == 0 else board_right + 10
				origin_y = board_y + slot * slot_height + (slot_height - shape_height) / 2
				self._draw_piece(index, (0, 0), self.rotations[index], display_scale,
							 origin_x, origin_y, PIECE_COLORS[index % len(PIECE_COLORS)], "#f4fbff")
				self.controls[f"piece_{index}"] = (
					origin_x, origin_y, origin_x + shape_width, origin_y + shape_height,
				)
		canvas.create_text(width / 2, height - 101, text=self.message, fill="#fff0d0",
						   font=("Segoe UI", 10, "bold"))

	def _draw_footer(self, width, height):
		canvas = self.canvas
		canvas.create_text(36, height - 45, text=f"{len(self.placed)} of {len(self.pieces)}", anchor="w",
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
		else:
			title, subtitle, button = "PUZZLE COMPLETE", "Same silhouette. Pieces are shuffled again.", "NEXT ROUND"
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
		column = (x - board_x) / cell
		row = (y - board_y) / cell
		if 0 <= column < BOARD_COLUMNS and 0 <= row < BOARD_ROWS:
			return column, row
		return None

	def _inside(self, point, bounds):
		x1, y1, x2, y2 = bounds
		return x1 <= point[0] <= x2 and y1 <= point[1] <= y2

	def _click(self, event):
		point = (event.x, event.y)
		self.mouse_position = point
		if "overlay" in self.controls and self._inside(point, self.controls["overlay"]):
			if self.paused:
				self.paused = False
				self.message = "Choose a piece, rotate it, then click a target cell."
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
		for index in range(len(self.pieces)):
			key = f"piece_{index}"
			if index not in self.placed and key in self.controls and self._inside(point, self.controls[key]):
				self.selected = index
				self.message = f"Piece {index + 1} selected. Move it over the target and rotate to fit."
				self._draw()
				return
		for key, action in (("undo", self._undo), ("left", lambda: self._rotate(-1)),
							("right", lambda: self._rotate(1)), ("hint", self._hint)):
			if self._inside(point, self.controls[key]):
				action()
				return
		cell = self._cell_at(event.x, event.y)
		if cell is not None and self.selected is not None:
			anchor = self._preview_anchor(self.selected, self._cursor_anchor(self.selected))
			self._place(self.selected, anchor, self.rotations[self.selected])

	def _motion(self, event):
		self.mouse_position = (event.x, event.y)
		self._draw()

	def _on_mousewheel(self, event):
		if event.delta:
			self._rotate_from_scroll(1 if event.delta > 0 else -1)
			return "break"
		return None

	def _rotate_from_scroll(self, direction):
		if self.selected is not None:
			self._rotate(direction)

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
		anchor = self.goal_anchors[index]
		rotation = self.goal_rotations[index]
		self.rotations[index] = rotation
		self.placed[index] = (anchor, rotation)
		self.selected = None
		self.moves += 1
		if is_hint:
			self.hints += 1
		self.score = max(0, 1000 - self.moves * 15 - self.hints * 100)
		if len(self.placed) == len(self.pieces):
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
		index = next((piece for piece in range(len(self.pieces)) if piece not in self.placed), None)
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
		self.placed = {}
		self.history = []
		self.mouse_position = (0, 0)
		self.message = "Choose a piece, rotate it, then click a target cell."
		self._load_puzzle()
		self._draw()


if __name__ == "__main__":
	window = tk.Tk()
	ShapeShift(window)
	window.mainloop()
