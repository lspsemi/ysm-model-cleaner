import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


DEFAULT_MIN_CUBES = 1000
DEFAULT_MIN_RATIO = 0.25
ANTI_PARSER_EXACT_NAMES = {"anti_parser_dummy", "anti-parser-dummy", "antiparserdummy"}
ANTI_PARSER_KEYWORDS = ("anti", "parser", "dummy")
BATCH_LOG_LEVELS = ("简洁", "正常", "详细", "调试")
BATCH_ANTI_ACTIONS = ("保留 anti-parser 垃圾数据", "删除 anti-parser 垃圾数据")
DEFAULT_HIDE_NONE = "不处理默认隐藏"
DEFAULT_HIDE_WRITE = "2.5档：按默认状态写入隐藏动画"
DEFAULT_HIDE_BAKE = "2.5档：烘焙编辑器隐藏几何"
DEFAULT_HIDE_DELETE = "2.5档：按默认状态删除隐藏部件"
DEFAULT_HIDE_ACTIONS = (DEFAULT_HIDE_NONE, DEFAULT_HIDE_WRITE, DEFAULT_HIDE_BAKE, DEFAULT_HIDE_DELETE)
LEGACY_DEFAULT_HIDE_WRITE = "按默认逻辑写入隐藏动画"
LEGACY_DEFAULT_HIDE_DELETE = "按默认逻辑删除隐藏部件"
UNKNOWN = object()


class YsmProject:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.ysm_json_path = self.folder / "ysm.json"
        self.main_model_rel = Path("models/main.json")
        self.main_model_path = self.folder / self.main_model_rel
        self.animation_rels = []
        self.model_data = None
        self.bones = []
        self.bone_by_name = {}
        self.children = defaultdict(list)
        self.subtree_cache = {}
        self.animation_refs = defaultdict(lambda: {"scale_zero": 0, "scale_nonzero": 0, "other": 0, "files": set()})

    def load(self):
        if not self.folder.is_dir():
            raise ValueError("请选择一个解包后的 YSM 模型文件夹。")

        if self.ysm_json_path.is_file():
            with self.ysm_json_path.open("r", encoding="utf-8") as f:
                ysm = json.load(f)
            player = ysm.get("files", {}).get("player", {})
            model = player.get("model", {})
            if isinstance(model, dict) and model.get("main"):
                self.main_model_rel = Path(model["main"])
                self.main_model_path = self.folder / self.main_model_rel

            animation = player.get("animation", {})
            if isinstance(animation, dict):
                self.animation_rels = [Path(v) for v in animation.values() if isinstance(v, str)]
            elif isinstance(animation, list):
                self.animation_rels = [Path(v) for v in animation if isinstance(v, str)]

        if not self.main_model_path.is_file():
            raise FileNotFoundError(f"找不到主模型文件：{self.main_model_path}")

        with self.main_model_path.open("r", encoding="utf-8") as f:
            self.model_data = json.load(f)

        geometry = self._geometry()
        self.bones = geometry.get("bones", [])
        self.bone_by_name = {bone.get("name", ""): bone for bone in self.bones if bone.get("name")}
        self.children = defaultdict(list)
        for bone in self.bones:
            name = bone.get("name", "")
            parent = bone.get("parent", "")
            if name:
                self.children[parent].append(name)

        self._load_animation_refs()

    def _geometry(self):
        geometries = self.model_data.get("minecraft:geometry")
        if not isinstance(geometries, list) or not geometries:
            raise ValueError("主模型没有 minecraft:geometry[0]。")
        return geometries[0]

    def _load_animation_refs(self):
        paths = []
        if self.animation_rels:
            paths.extend(self.folder / rel for rel in self.animation_rels)
        animations_dir = self.folder / "animations"
        if animations_dir.is_dir():
            paths.extend(animations_dir.rglob("*.json"))

        seen = set()
        for path in paths:
            path = path.resolve()
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            rel = str(path.relative_to(self.folder))
            for animation in (data.get("animations") or {}).values():
                bones = animation.get("bones") if isinstance(animation, dict) else None
                if not isinstance(bones, dict):
                    continue
                for bone_name, channels in bones.items():
                    ref = self.animation_refs[bone_name]
                    ref["files"].add(rel)
                    if not isinstance(channels, dict):
                        ref["other"] += 1
                        continue
                    if "scale" in channels:
                        scale_values = flatten_keyframes(channels["scale"])
                        if scale_values and all(is_zero_scale(value) for value in scale_values):
                            ref["scale_zero"] += 1
                        elif scale_values:
                            ref["scale_nonzero"] += 1
                    if any(key in channels for key in ("rotation", "position")):
                        ref["other"] += 1

    def total_cubes(self):
        return sum(len(bone.get("cubes") or []) for bone in self.bones)

    def subtree_stats(self, root):
        if root in self.subtree_cache:
            return self.subtree_cache[root]
        nodes = []
        cubes = 0
        stack = [root]
        while stack:
            name = stack.pop()
            if name not in self.bone_by_name:
                continue
            nodes.append(name)
            cubes += len(self.bone_by_name[name].get("cubes") or [])
            stack.extend(self.children.get(name, []))
        result = (nodes, cubes)
        self.subtree_cache[root] = result
        return result

    def find_candidates(self, min_cubes=DEFAULT_MIN_CUBES, min_ratio=DEFAULT_MIN_RATIO):
        total = max(1, self.total_cubes())
        candidates = []
        for name, bone in self.bone_by_name.items():
            nodes, cubes = self.subtree_stats(name)
            if cubes < min_cubes:
                continue
            ratio = cubes / total
            if ratio < min_ratio:
                continue
            ref = self.animation_refs.get(name)
            hidden_by_scale = ref and ref["scale_zero"] > 0 and ref["scale_nonzero"] == 0 and ref["other"] == 0
            aux_like = name.startswith(("aux_", "bb_"))
            root_like = not bone.get("parent")
            if hidden_by_scale or (aux_like and root_like):
                candidates.append({
                    "name": name,
                    "parent": bone.get("parent", ""),
                    "nodes": len(nodes),
                    "cubes": cubes,
                    "ratio": ratio,
                    "hidden_by_scale": bool(hidden_by_scale),
                    "files": sorted(ref["files"]) if ref else [],
                })
        candidates.sort(key=lambda item: item["cubes"], reverse=True)
        return remove_nested_candidates(candidates, self)

    def save_clean_copy(self, selected_roots, output_folder):
        selected_roots = list(selected_roots)
        if not selected_roots:
            raise ValueError("没有选择要删除的骨骼。")

        output_folder = Path(output_folder)
        if output_folder.exists():
            shutil.rmtree(output_folder)
        shutil.copytree(self.folder, output_folder)

        remove = set()
        for root in selected_roots:
            nodes, _ = self.subtree_stats(root)
            remove.update(nodes)

        copied_model_path = output_folder / self.main_model_rel
        with copied_model_path.open("r", encoding="utf-8") as f:
            copied_model = json.load(f)
        geometry = copied_model["minecraft:geometry"][0]
        original_bones = geometry.get("bones", [])
        original_cubes = sum(len(bone.get("cubes") or []) for bone in original_bones)
        geometry["bones"] = [bone for bone in original_bones if bone.get("name", "") not in remove]
        cleaned_cubes = sum(len(bone.get("cubes") or []) for bone in geometry["bones"])

        with copied_model_path.open("w", encoding="utf-8") as f:
            json.dump(copied_model, f, ensure_ascii=False, separators=(",", ":"))

        cleaned_refs = clean_animation_refs(output_folder, remove)
        report_path = output_folder / "ysm_garbage_cleaner_report.txt"
        with report_path.open("w", encoding="utf-8") as f:
            f.write("YSM garbage cleaner report\n")
            f.write(f"Source: {self.folder}\n")
            f.write(f"Output: {output_folder}\n")
            f.write(f"Removed roots: {', '.join(selected_roots)}\n")
            f.write(f"Removed bones: {len(remove)}\n")
            f.write(f"Bones: {len(original_bones)} -> {len(geometry['bones'])}\n")
            f.write(f"Cubes: {original_cubes} -> {cleaned_cubes}\n")
            f.write(f"Animation references removed: {cleaned_refs}\n")

        return {
            "output_folder": output_folder,
            "report_path": report_path,
            "removed_bones": len(remove),
            "old_bones": len(original_bones),
            "new_bones": len(geometry["bones"]),
            "old_cubes": original_cubes,
            "new_cubes": cleaned_cubes,
            "cleaned_refs": cleaned_refs,
            "bytes": copied_model_path.stat().st_size,
        }


def flatten_keyframes(value):
    if isinstance(value, dict):
        values = []
        for item in value.values():
            if isinstance(item, dict):
                values.extend(v for v in (item.get("pre"), item.get("post"), item.get("vector")) if v is not None)
            else:
                values.append(item)
        return values
    return [value]


def is_zero_scale(value):
    if isinstance(value, (int, float)):
        return abs(float(value)) < 1e-9
    if isinstance(value, list) and len(value) >= 3:
        return all(isinstance(item, (int, float)) and abs(float(item)) < 1e-9 for item in value[:3])
    return False


def remove_nested_candidates(candidates, project):
    kept = []
    covered = set()
    for candidate in candidates:
        name = candidate["name"]
        if name in covered:
            continue
        kept.append(candidate)
        nodes, _ = project.subtree_stats(name)
        covered.update(nodes)
    return kept


def clean_animation_refs(output_folder, removed_bones):
    count = 0
    animations_dir = Path(output_folder) / "animations"
    if not animations_dir.is_dir():
        return count

    for path in animations_dir.rglob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        changed = False
        for animation in (data.get("animations") or {}).values():
            bones = animation.get("bones") if isinstance(animation, dict) else None
            if not isinstance(bones, dict):
                continue
            for bone_name in list(bones.keys()):
                if bone_name in removed_bones:
                    del bones[bone_name]
                    count += 1
                    changed = True

        if changed:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return count


def collect_anti_parser_bones(project_path):
    diagnostics_path = Path(project_path) / "_ysm_parser_diagnostics.json"
    if not diagnostics_path.is_file():
        return set()

    try:
        with diagnostics_path.open("r", encoding="utf-8") as f:
            diagnostics = json.load(f)
    except Exception:
        return set()

    bones = set()
    for event in diagnostics.get("events", []):
        if event.get("category") != "anti_parser":
            continue
        context = str(event.get("context") or "")
        if context.startswith("model_bone:"):
            bone_name = context.split(":", 1)[1].strip()
            if bone_name:
                bones.add(bone_name)
    return bones


def expand_bone_descendants(bones, roots):
    by_name = {bone.get("name"): bone for bone in bones if isinstance(bone, dict) and bone.get("name")}
    children = defaultdict(list)
    for bone in bones:
        if not isinstance(bone, dict):
            continue
        name = bone.get("name")
        parent = bone.get("parent")
        if name:
            children[parent].append(name)

    remove = set()
    stack = [name for name in roots if name in by_name]
    while stack:
        name = stack.pop()
        if name in remove:
            continue
        remove.add(name)
        stack.extend(children.get(name, []))
    return remove


def remove_bones_from_model_json(model_path, root_bones):
    try:
        with Path(model_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set(), 0, 0

    geometries = data.get("minecraft:geometry")
    if not isinstance(geometries, list):
        return set(), 0, 0

    removed = set()
    old_count = 0
    new_count = 0
    changed = False
    for geometry in geometries:
        if not isinstance(geometry, dict):
            continue
        bones = geometry.get("bones")
        if not isinstance(bones, list):
            continue
        old_count += len(bones)
        remove = expand_bone_descendants(bones, root_bones)
        if remove:
            geometry["bones"] = [bone for bone in bones if bone.get("name") not in remove]
            removed.update(remove)
            changed = True
        new_count += len(geometry.get("bones") or [])

    if changed:
        with Path(model_path).open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return removed, old_count, new_count


def clear_hidden_geometry_from_model_json(model_path, root_bones):
    try:
        with Path(model_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set(), 0, 0, 0

    geometries = data.get("minecraft:geometry")
    if not isinstance(geometries, list):
        return set(), 0, 0, 0

    changed_bones = set()
    total_bones = 0
    old_cubes = 0
    new_cubes = 0
    changed = False
    for geometry in geometries:
        if not isinstance(geometry, dict):
            continue
        bones = geometry.get("bones")
        if not isinstance(bones, list):
            continue
        total_bones += len(bones)
        hide = expand_bone_descendants(bones, root_bones)
        for bone in bones:
            cubes = bone.get("cubes")
            if isinstance(cubes, list):
                old_cubes += len(cubes)
            name = bone.get("name")
            if name in hide and isinstance(cubes, list) and cubes:
                bone["cubes"] = []
                changed_bones.add(name)
                changed = True
            cubes_after = bone.get("cubes")
            if isinstance(cubes_after, list):
                new_cubes += len(cubes_after)

    if changed:
        with Path(model_path).open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return changed_bones, total_bones, old_cubes, new_cubes


def clean_anti_parser_garbage(project_path):
    project_path = Path(project_path)
    roots = collect_anti_parser_bones(project_path)
    if not roots:
        return {
            "roots": set(),
            "removed_bones": set(),
            "model_files": 0,
            "old_bones": 0,
            "new_bones": 0,
            "cleaned_refs": 0,
            "report_path": None,
        }

    removed_bones = set()
    old_bones = 0
    new_bones = 0
    model_files = 0
    models_dir = project_path / "models"
    model_paths = sorted(models_dir.rglob("*.json")) if models_dir.is_dir() else []
    for model_path in model_paths:
        removed, old_count, new_count = remove_bones_from_model_json(model_path, roots)
        if old_count or new_count:
            model_files += 1
        old_bones += old_count
        new_bones += new_count
        removed_bones.update(removed)

    cleaned_refs = clean_animation_refs(project_path, removed_bones) if removed_bones else 0
    report_path = project_path / "ysm_antiparser_clean_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("YSM anti-parser cleaner report\n")
        f.write(f"Project: {project_path}\n")
        f.write(f"Detected roots: {', '.join(sorted(roots))}\n")
        f.write(f"Removed bones: {len(removed_bones)}\n")
        f.write(f"Model files scanned: {model_files}\n")
        f.write(f"Bones: {old_bones} -> {new_bones}\n")
        f.write(f"Animation references removed: {cleaned_refs}\n")

    return {
        "roots": roots,
        "removed_bones": removed_bones,
        "model_files": model_files,
        "old_bones": old_bones,
        "new_bones": new_bones,
        "cleaned_refs": cleaned_refs,
        "report_path": report_path,
    }


def load_json_file(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def read_player_file_map(project_path):
    ysm_path = Path(project_path) / "ysm.json"
    if not ysm_path.is_file():
        return {}, [], {}
    ysm = load_json_file(ysm_path)
    player = ((ysm.get("files") or {}).get("player") or {})
    animations = player.get("animation") or {}
    controllers = player.get("animation_controllers") or []
    models = player.get("model") or {}
    return animations if isinstance(animations, dict) else {}, controllers if isinstance(controllers, list) else [], models if isinstance(models, dict) else {}


def read_ysm_file_map(project_path):
    ysm_path = Path(project_path) / "ysm.json"
    if not ysm_path.is_file():
        return {}
    try:
        ysm = load_json_file(ysm_path)
    except Exception:
        return {}
    files = ysm.get("files") or {}
    return files if isinstance(files, dict) else {}


def collect_animation_definitions(project_path):
    project_path = Path(project_path)
    animation_map, _, _ = read_player_file_map(project_path)
    files = set()
    for rel in animation_map.values():
        if isinstance(rel, str):
            files.add(project_path / rel)
    animations_dir = project_path / "animations"
    if animations_dir.is_dir():
        files.update(animations_dir.rglob("*.json"))

    definitions = {}
    for path in sorted(files):
        if not path.is_file():
            continue
        try:
            data = load_json_file(path)
        except Exception:
            continue
        for name, animation in (data.get("animations") or {}).items():
            if isinstance(animation, dict):
                definitions[name] = {"path": path, "animation": animation}
    return definitions


def controller_unconditional_default_animations(project_path):
    project_path = Path(project_path)
    _, controller_rels, _ = read_player_file_map(project_path)
    controller_files = []
    for rel in controller_rels:
        if isinstance(rel, str):
            controller_files.append(project_path / rel)
    controller_dir = project_path / "controller"
    if controller_dir.is_dir():
        controller_files.extend(controller_dir.rglob("*.json"))

    names = set()
    skipped_conditional = 0
    seen = set()
    for path in controller_files:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = load_json_file(path)
        except Exception:
            continue
        for controller in (data.get("animation_controllers") or {}).values():
            if not isinstance(controller, dict):
                continue
            states = controller.get("states") or {}
            initial = controller.get("initial_state") or "default"
            state = states.get(initial) or states.get("default") or {}
            animations = state.get("animations") or []
            if isinstance(animations, str):
                animations = [animations]
            if not isinstance(animations, list):
                continue
            for item in animations:
                if isinstance(item, str):
                    name = item.strip()
                    if name:
                        names.add(name)
                elif isinstance(item, dict):
                    skipped_conditional += len(item)
    return names, skipped_conditional


def normalize_condition_text(expr):
    return str(expr).strip().replace("&&", " and ").replace("||", " or ")


def default_symbol_value(name):
    name = name.strip()
    true_names = {
        "ctrl.idle",
        "q.is_on_ground",
        "query.is_on_ground",
    }
    false_prefixes = (
        "ctrl.hold(",
        "ctrl.use(",
        "q.is_item_name_any(",
        "query.is_item_name_any(",
        "ysm.relative_block_name_any(",
    )
    false_names = {
        "ctrl.playing_extra_animation",
        "ctrl.walk",
        "ctrl.run",
        "ctrl.jump",
        "ctrl.sneak",
        "ctrl.sneaking",
        "ctrl.climb",
        "ctrl.climbing",
        "ctrl.fly",
        "ctrl.elytra_fly",
        "ctrl.swim",
        "ctrl.ladder_up",
        "ctrl.ladder_down",
        "ctrl.ladder_stillness",
        "ctrl.tac_hold_gun",
        "ctrl.carryon_is_princess",
        "tlm.is_sitting",
        "tlm.is_statue",
        "tlm.is_garage_kit",
        "ysm.has_offhand",
        "ysm.mainhand_charged_crossbow",
        "ysm.offhand_charged_crossbow",
        "q.all_animations_finished",
        "query.all_animations_finished",
        "q.is_in_water",
        "query.is_in_water",
    }
    zero_names = {
        "ysm.input_vertical",
        "ysm.ground_speed2",
        "ysm.arrow_count",
        "q.ground_speed",
        "query.ground_speed",
        "q.vertical_speed",
        "query.vertical_speed",
    }
    empty_string_names = {
        "ctrl.parcool_state",
        "ctrl.slashblade_animation",
        "ysm.shoot_item_id",
    }

    if name in true_names:
        return True
    if name in false_names:
        return False
    if name in zero_names:
        return 0
    if name in empty_string_names:
        return ""
    if any(name.startswith(prefix) for prefix in false_prefixes):
        return False
    if name.startswith("v.") or name.startswith("variable."):
        return 0
    return UNKNOWN


def split_top_level(expr, operator):
    parts = []
    depth = 0
    quote = None
    start = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and expr.startswith(operator, i):
            parts.append(expr[start:i].strip())
            i += len(operator)
            start = i
            continue
        i += 1
    if parts:
        parts.append(expr[start:].strip())
    return parts


def strip_outer_parens(expr):
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        valid = True
        quote = None
        for i, ch in enumerate(expr):
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    valid = False
                    break
        if not valid:
            break
        expr = expr[1:-1].strip()
    return expr


def parse_literal(text):
    text = text.strip()
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        return text[1:-1]
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return UNKNOWN


def compare_values(left, op, right):
    if left is UNKNOWN or right is UNKNOWN:
        return UNKNOWN
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    try:
        left_num = float(left)
        right_num = float(right)
    except (TypeError, ValueError):
        return UNKNOWN
    if op == ">=":
        return left_num >= right_num
    if op == "<=":
        return left_num <= right_num
    if op == ">":
        return left_num > right_num
    if op == "<":
        return left_num < right_num
    return UNKNOWN


def eval_default_condition(expr):
    expr = strip_outer_parens(normalize_condition_text(expr))
    if not expr:
        return UNKNOWN

    parts = split_top_level(expr, " or ")
    if parts:
        saw_unknown = False
        for part in parts:
            value = eval_default_condition(part)
            if value is True:
                return True
            if value is UNKNOWN:
                saw_unknown = True
        return UNKNOWN if saw_unknown else False

    parts = split_top_level(expr, " and ")
    if parts:
        saw_unknown = False
        for part in parts:
            value = eval_default_condition(part)
            if value is False:
                return False
            if value is UNKNOWN:
                saw_unknown = True
        return UNKNOWN if saw_unknown else True

    if expr.startswith("!"):
        value = eval_default_condition(expr[1:])
        return UNKNOWN if value is UNKNOWN else not bool(value)

    for op in ("==", "!=", ">=", "<=", ">", "<"):
        parts = split_top_level(expr, op)
        if parts and len(parts) == 2:
            left = default_symbol_value(parts[0])
            right = parse_literal(parts[1])
            return compare_values(left, op, right)

    value = default_symbol_value(expr)
    if value is UNKNOWN:
        return UNKNOWN
    return bool(value)


def controller_default_state_animations(project_path):
    project_path = Path(project_path)
    _, controller_rels, _ = read_player_file_map(project_path)
    controller_files = []
    for rel in controller_rels:
        if isinstance(rel, str):
            controller_files.append(project_path / rel)
    controller_dir = project_path / "controller"
    if controller_dir.is_dir():
        controller_files.extend(controller_dir.rglob("*.json"))

    names = set()
    skipped_unknown = 0
    skipped_false = 0
    seen = set()
    for path in controller_files:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = load_json_file(path)
        except Exception:
            continue
        for controller in (data.get("animation_controllers") or {}).values():
            if not isinstance(controller, dict):
                continue
            states = controller.get("states") or {}
            initial = controller.get("initial_state") or "default"
            state = states.get(initial) or states.get("default") or {}
            animations = state.get("animations") or []
            if isinstance(animations, str):
                animations = [animations]
            if not isinstance(animations, list):
                continue
            for item in animations:
                if isinstance(item, str):
                    name = item.strip()
                    if name:
                        names.add(name)
                elif isinstance(item, dict):
                    for name, condition in item.items():
                        result = eval_default_condition(condition)
                        if result is True and str(name).strip():
                            names.add(str(name).strip())
                        elif result is UNKNOWN:
                            skipped_unknown += 1
                        else:
                            skipped_false += 1
    return names, skipped_unknown, skipped_false


def is_static_zero_scale(value):
    if isinstance(value, (int, float)):
        return abs(float(value)) < 1e-9
    if isinstance(value, list):
        return len(value) >= 3 and all(isinstance(item, (int, float)) and abs(float(item)) < 1e-9 for item in value[:3])
    if isinstance(value, dict):
        flattened = flatten_keyframes(value)
        return bool(flattened) and all(is_zero_scale(item) for item in flattened)
    return False


def is_default_zero_scale(value):
    if isinstance(value, (int, float)):
        return abs(float(value)) < 1e-9
    if isinstance(value, list):
        return len(value) >= 3 and all(is_default_zero_scale(item) for item in value[:3])
    if isinstance(value, dict):
        flattened = flatten_keyframes(value)
        return bool(flattened) and all(is_default_zero_scale(item) for item in flattened)
    if isinstance(value, str):
        text = value.strip()
        literal = parse_literal(text)
        if isinstance(literal, (int, float)):
            return abs(float(literal)) < 1e-9
        if any(token in text for token in ("==", "!=", ">=", "<=", ">", "<", "&&", "||", " and ", " or ", "!")):
            result = eval_default_condition(text)
            return result is False
    return False


def collect_model_bone_names(model_path):
    try:
        data = load_json_file(model_path)
    except Exception:
        return set()
    names = set()
    geometries = data.get("minecraft:geometry")
    if not isinstance(geometries, list):
        return names
    for geometry in geometries:
        if not isinstance(geometry, dict):
            continue
        for bone in geometry.get("bones") or []:
            if isinstance(bone, dict) and bone.get("name"):
                names.add(str(bone["name"]))
    return names


def collect_player_model_bone_names(project_path):
    project_path = Path(project_path)
    _, _, models = read_player_file_map(project_path)
    names = set()
    for rel in models.values():
        if isinstance(rel, str):
            names.update(collect_model_bone_names(project_path / rel))
    return names


def collect_projectile_default_hidden_bones(project_path):
    project_path = Path(project_path)
    files = read_ysm_file_map(project_path)
    projectiles = files.get("projectiles") or {}
    if not isinstance(projectiles, dict):
        return set(), set(), set()

    hidden = set()
    skipped_collisions = set()
    model_paths = set()
    player_bones = collect_player_model_bone_names(project_path)
    for projectile in projectiles.values():
        if not isinstance(projectile, dict):
            continue
        model_rel = projectile.get("model")
        if isinstance(model_rel, str) and model_rel:
            model_paths.add(project_path / model_rel)

    for model_path in model_paths:
        if not model_path.is_file():
            continue
        for name in collect_model_bone_names(model_path):
            if name in player_bones:
                skipped_collisions.add(name)
            else:
                hidden.add(name)

    return hidden, model_paths, skipped_collisions


def collect_default_hidden_bones(project_path):
    animation_names, skipped_unknown, skipped_false = controller_default_state_animations(project_path)
    definitions = collect_animation_definitions(project_path)
    hidden = set()
    used_animations = set()
    unresolved = set()

    for name in sorted(animation_names):
        animation_info = definitions.get(name)
        if not animation_info:
            unresolved.add(name)
            continue
        animation = animation_info["animation"]
        bones = animation.get("bones") or {}
        if not isinstance(bones, dict):
            continue
        used_animations.add(name)
        for bone_name, channels in bones.items():
            if not isinstance(channels, dict) or "scale" not in channels:
                continue
            if is_default_zero_scale(channels["scale"]):
                hidden.add(bone_name)

    projectile_hidden, projectile_models, projectile_collisions = collect_projectile_default_hidden_bones(project_path)
    hidden.update(projectile_hidden)

    return {
        "hidden_bones": hidden,
        "animations": used_animations,
        "unresolved": unresolved,
        "skipped_conditional": skipped_unknown,
        "skipped_false": skipped_false,
        "projectile_hidden_bones": projectile_hidden,
        "projectile_models": projectile_models,
        "projectile_name_collisions": projectile_collisions,
    }


def is_default_hide_write_mode(mode):
    return mode in (DEFAULT_HIDE_WRITE, LEGACY_DEFAULT_HIDE_WRITE)


def is_default_hide_bake_mode(mode):
    return mode == DEFAULT_HIDE_BAKE


def is_default_hide_delete_mode(mode):
    return mode in (DEFAULT_HIDE_DELETE, LEGACY_DEFAULT_HIDE_DELETE)


def write_default_hidden_animation(project_path, hidden_bones):
    project_path = Path(project_path)
    if not hidden_bones:
        return None
    animations_dir = project_path / "animations"
    animations_dir.mkdir(parents=True, exist_ok=True)
    path = animations_dir / "ysm_cleaner.default_hidden.animation.json"
    data = {
        "format_version": "1.8.0",
        "animations": {
            "ysm_cleaner.default_hidden": {
                "loop": True,
                "bones": {name: {"scale": [0, 0, 0]} for name in sorted(hidden_bones)}
            }
        }
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    ysm_path = project_path / "ysm.json"
    if ysm_path.is_file():
        try:
            ysm = load_json_file(ysm_path)
            player = ysm.setdefault("files", {}).setdefault("player", {})
            animations = player.setdefault("animation", {})
            if isinstance(animations, dict):
                animations["ysm_cleaner_default_hidden"] = "animations/ysm_cleaner.default_hidden.animation.json"
                with ysm_path.open("w", encoding="utf-8") as f:
                    json.dump(ysm, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass

    _, controller_rels, _ = read_player_file_map(project_path)
    controller_files = []
    for rel in controller_rels:
        if isinstance(rel, str):
            controller_files.append(project_path / rel)
    controller_dir = project_path / "controller"
    if controller_dir.is_dir():
        controller_files.extend(controller_dir.rglob("*.json"))

    seen = set()
    for controller_path in controller_files:
        if controller_path in seen or not controller_path.is_file():
            continue
        seen.add(controller_path)
        try:
            data = load_json_file(controller_path)
        except Exception:
            continue
        changed = False
        for controller in (data.get("animation_controllers") or {}).values():
            if not isinstance(controller, dict):
                continue
            states = controller.get("states") or {}
            initial = controller.get("initial_state") or "default"
            state = states.get(initial) or states.get("default")
            if not isinstance(state, dict):
                continue
            animations = state.setdefault("animations", [])
            if isinstance(animations, str):
                animations = [animations]
                state["animations"] = animations
            if isinstance(animations, list) and "ysm_cleaner.default_hidden" not in animations:
                animations.append("ysm_cleaner.default_hidden")
                changed = True
        if changed:
            with controller_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return path


def delete_default_hidden_bones(project_path, hidden_bones):
    project_path = Path(project_path)
    _, _, models = read_player_file_map(project_path)
    model_paths = []
    for rel in models.values():
        if isinstance(rel, str):
            model_paths.append(project_path / rel)
    models_dir = project_path / "models"
    if models_dir.is_dir():
        model_paths.extend(models_dir.rglob("*.json"))

    removed_bones = set()
    old_bones = 0
    new_bones = 0
    seen = set()
    for model_path in model_paths:
        if model_path in seen or not model_path.is_file():
            continue
        seen.add(model_path)
        removed, old_count, new_count = remove_bones_from_model_json(model_path, hidden_bones)
        removed_bones.update(removed)
        old_bones += old_count
        new_bones += new_count
    cleaned_refs = clean_animation_refs(project_path, removed_bones) if removed_bones else 0
    return removed_bones, old_bones, new_bones, cleaned_refs


def bake_default_hidden_geometry(project_path, hidden_bones):
    project_path = Path(project_path)
    _, _, models = read_player_file_map(project_path)
    model_paths = []
    for rel in models.values():
        if isinstance(rel, str):
            model_paths.append(project_path / rel)
    models_dir = project_path / "models"
    if models_dir.is_dir():
        model_paths.extend(models_dir.rglob("*.json"))

    changed_bones = set()
    total_bones = 0
    old_cubes = 0
    new_cubes = 0
    seen = set()
    for model_path in model_paths:
        if model_path in seen or not model_path.is_file():
            continue
        seen.add(model_path)
        changed, bone_count, old_count, new_count = clear_hidden_geometry_from_model_json(model_path, hidden_bones)
        changed_bones.update(changed)
        total_bones += bone_count
        old_cubes += old_count
        new_cubes += new_count
    return changed_bones, total_bones, old_cubes, new_cubes


def apply_default_hidden_logic(project_path, mode):
    analysis = collect_default_hidden_bones(project_path)
    hidden = analysis["hidden_bones"]
    report_path = Path(project_path) / "ysm_default_hidden_report.txt"
    animation_path = None
    removed_bones = set()
    old_bones = 0
    new_bones = 0
    cleaned_refs = 0
    baked_bones = set()
    old_cubes = 0
    new_cubes = 0

    if is_default_hide_write_mode(mode) and hidden:
        animation_path = write_default_hidden_animation(project_path, hidden)
    elif is_default_hide_bake_mode(mode) and hidden:
        animation_path = write_default_hidden_animation(project_path, hidden)
        baked_bones, old_bones, old_cubes, new_cubes = bake_default_hidden_geometry(project_path, hidden)
    elif is_default_hide_delete_mode(mode) and hidden:
        removed_bones, old_bones, new_bones, cleaned_refs = delete_default_hidden_bones(project_path, hidden)

    with report_path.open("w", encoding="utf-8") as f:
        f.write("YSM default hidden logic report\n")
        f.write(f"Project: {project_path}\n")
        f.write(f"Mode: {mode}\n")
        f.write("Default state profile: standing, idle, empty hands, no offhand, not sitting, not swimming, not using item\n")
        f.write(f"Default-state animations parsed: {len(analysis['animations'])}\n")
        f.write(f"Conditional animation entries skipped as default-false: {analysis['skipped_false']}\n")
        f.write(f"Conditional animation entries skipped as unknown: {analysis['skipped_conditional']}\n")
        f.write(f"Default-hidden projectile/extra asset bones: {len(analysis['projectile_hidden_bones'])}\n")
        f.write(f"Projectile/extra asset bones skipped by player-name collision: {', '.join(sorted(analysis['projectile_name_collisions']))}\n")
        f.write(f"Default-hidden projectile/extra model files: {', '.join(str(path) for path in sorted(analysis['projectile_models']))}\n")
        f.write(f"Unresolved animation names: {', '.join(sorted(analysis['unresolved']))}\n")
        f.write(f"Default hidden bones: {len(hidden)}\n")
        f.write(f"Hidden bones: {', '.join(sorted(hidden))}\n")
        if animation_path:
            f.write(f"Generated hidden animation: {animation_path}\n")
        if baked_bones:
            f.write(f"Baked editor-hidden bones: {len(baked_bones)}\n")
            f.write(f"Cubes: {old_cubes} -> {new_cubes}\n")
        if removed_bones:
            f.write(f"Removed bones: {len(removed_bones)}\n")
            f.write(f"Bones: {old_bones} -> {new_bones}\n")
            f.write(f"Animation references removed: {cleaned_refs}\n")

    return {
        "hidden_bones": hidden,
        "animation_path": animation_path,
        "removed_bones": removed_bones,
        "old_bones": old_bones,
        "new_bones": new_bones,
        "baked_bones": baked_bones,
        "old_cubes": old_cubes,
        "new_cubes": new_cubes,
        "cleaned_refs": cleaned_refs,
        "report_path": report_path,
        "skipped_conditional": analysis["skipped_conditional"],
        "skipped_false": analysis["skipped_false"],
        "projectile_hidden_bones": analysis["projectile_hidden_bones"],
        "projectile_models": analysis["projectile_models"],
        "projectile_name_collisions": analysis["projectile_name_collisions"],
        "unresolved": analysis["unresolved"],
    }


def normalize_probe_name(value):
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def looks_like_anti_parser_name(value):
    raw = str(value).lower()
    compact = normalize_probe_name(value)
    if raw in ANTI_PARSER_EXACT_NAMES or compact in ANTI_PARSER_EXACT_NAMES:
        return True
    return all(keyword in raw or keyword in compact for keyword in ANTI_PARSER_KEYWORDS)


def iter_json_strings(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from iter_json_strings(key, f"{path}.<key>")
            yield from iter_json_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_json_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def scan_json_for_anti_parser(path):
    findings = []
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return [{"severity": "warn", "file": str(path), "where": "JSON", "detail": f"无法读取 JSON：{exc}"}]

    rel = str(path)
    geometries = data.get("minecraft:geometry")
    if isinstance(geometries, list):
        for geo_index, geometry in enumerate(geometries):
            for bone_index, bone in enumerate((geometry or {}).get("bones") or []):
                if not isinstance(bone, dict):
                    continue
                for field in ("name", "parent"):
                    value = bone.get(field)
                    if isinstance(value, str) and looks_like_anti_parser_name(value):
                        findings.append({
                            "severity": "warn",
                            "file": rel,
                            "where": f"minecraft:geometry[{geo_index}].bones[{bone_index}].{field}",
                            "detail": f"辅助线索：发现疑似 anti-parser 名字字段 {value}",
                        })

    animations = data.get("animations")
    if isinstance(animations, dict):
        for animation_name, animation in animations.items():
            bones = animation.get("bones") if isinstance(animation, dict) else None
            if not isinstance(bones, dict):
                continue
            for bone_name in bones:
                if looks_like_anti_parser_name(bone_name):
                    findings.append({
                        "severity": "warn",
                        "file": rel,
                        "where": f"animations.{animation_name}.bones",
                        "detail": f"辅助线索：发现疑似 anti-parser 动画骨骼名 {bone_name}",
                    })

    for json_path, text in iter_json_strings(data):
        lower = text.lower()
        if "anti_parser_dummy" in lower or "anti-parser-dummy" in lower:
            findings.append({
                "severity": "warn",
                "file": rel,
                "where": json_path,
                "detail": f"辅助线索：发现 anti_parser_Dummy 明文 {text}",
            })

    return findings


def scan_ysm_binary_for_anti_parser(path):
    path = Path(path)
    data = path.read_bytes()
    patterns = [
        b"anti_parser_Dummy",
        b"anti_parser_dummy",
        b"anti-parser-Dummy",
        "anti_parser_Dummy".encode("utf-16le"),
        "anti_parser_dummy".encode("utf-16le"),
    ]
    findings = []
    for pattern in patterns:
        offset = data.find(pattern)
        if offset != -1:
            findings.append({
                "severity": "warn",
                "file": str(path),
                "where": f"binary offset 0x{offset:X}",
                "detail": "辅助线索：发现 anti_parser_Dummy 明文特征",
            })
    if not findings:
        findings.append({
            "severity": "info",
            "file": str(path),
            "where": ".ysm binary",
            "detail": ".ysm 通常经过加密/压缩；未发现明文 anti_parser_Dummy。若要完全确认，请用 0.3.6 解包后对输出工程再检测。",
        })
    return findings


def scan_parser_diagnostics(project_path):
    diagnostics_path = Path(project_path) / "_ysm_parser_diagnostics.json"
    if not diagnostics_path.is_file():
        return []

    try:
        with diagnostics_path.open("r", encoding="utf-8") as f:
            diagnostics = json.load(f)
    except Exception as exc:
        return [{
            "severity": "warn",
            "file": str(diagnostics_path),
            "where": "parser diagnostics",
            "detail": f"无法读取 parser 内部诊断文件：{exc}",
        }]

    findings = []
    for event in diagnostics.get("events", []):
        if event.get("category") != "anti_parser":
            continue
        offset = event.get("offset_hex") or event.get("offset")
        value = event.get("value")
        context = event.get("context") or "unknown"
        code = event.get("code") or "unknown"
        findings.append({
            "severity": "high",
            "file": str(diagnostics_path),
            "where": f"{context} @ {offset}",
            "detail": f"YSMParser 0.3.6 内部检测到 anti-parser 异常字段：{code}, value={value}",
        })
    return findings


def detect_anti_parser_payload(target):
    target = Path(target)
    if not target.exists():
        raise FileNotFoundError(f"路径不存在：{target}")

    findings = []
    scanned_files = 0
    if target.is_file():
        if target.suffix.lower() == ".ysm":
            scanned_files += 1
            findings.extend(scan_ysm_binary_for_anti_parser(target))
        elif target.suffix.lower() == ".json":
            scanned_files += 1
            findings.extend(scan_json_for_anti_parser(target))
        else:
            raise ValueError("请选择解包工程文件夹、.ysm 文件或 JSON 文件。")
    else:
        findings.extend(scan_parser_diagnostics(target))

        json_roots = [target / "models", target / "animations", target / "controller"]
        json_files = []
        for root in json_roots:
            if root.is_dir():
                json_files.extend(root.rglob("*.json"))
        if (target / "ysm.json").is_file():
            json_files.append(target / "ysm.json")
        if not json_files:
            json_files = list(target.rglob("*.json"))

        for path in sorted(set(json_files)):
            scanned_files += 1
            findings.extend(scan_json_for_anti_parser(path))

        for path in sorted(target.rglob("*.ysm")):
            scanned_files += 1
            findings.extend(scan_ysm_binary_for_anti_parser(path))

    deduped = []
    seen = set()
    for item in findings:
        key = (item["severity"], item["file"], item.get("where", ""), item["detail"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    findings = deduped

    high_count = sum(1 for item in findings if item["severity"] == "high")
    warn_count = sum(1 for item in findings if item["severity"] == "warn")
    return {
        "target": target,
        "scanned_files": scanned_files,
        "findings": findings,
        "high_count": high_count,
        "warn_count": warn_count,
    }


def app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_default_parser_exe():
    base = app_base_dir()
    candidates = [
        base / "YSMParser.exe",
        base / "YSMParser-0.3.6.exe",
        base / "YSMParser-main0.3.6" / "out" / "install" / "x64-release" / "bin" / "YSMParser.exe",
        base / "YSMParser-main0.3.6" / "out" / "build" / "x64-release" / "YSMParser" / "YSMParser.exe",
        base / "YSMParser-main0.3.6" / "out" / "build" / "x64-release" / "YSMParser.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def run_parser_to_temp_project(parser_exe, ysm_file, log=None):
    parser_exe = Path(parser_exe)
    ysm_file = Path(ysm_file)
    if not parser_exe.is_file():
        raise FileNotFoundError(f"找不到 YSMParser.exe：{parser_exe}")
    if not ysm_file.is_file() or ysm_file.suffix.lower() != ".ysm":
        raise ValueError("深度检测需要选择一个 .ysm 文件。")

    temp_root = Path(tempfile.mkdtemp(prefix="ysm_parser_scan_"))
    input_dir = temp_root / "input"
    output_dir = temp_root / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    copied_ysm = input_dir / ysm_file.name
    shutil.copy2(ysm_file, copied_ysm)

    command = [str(parser_exe), "-i", str(input_dir), "-o", str(output_dir), "-j", "1"]
    if log:
        log("调用 YSMParser 0.3.6 解包到临时目录...")
        log("命令：" + " ".join(f'"{part}"' if " " in part else part for part in command))

    try:
        completed = subprocess.run(
            command,
            cwd=str(parser_exe.parent),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        parser_output = completed.stdout.strip()
        if parser_output and log:
            for line in parser_output.splitlines()[-80:]:
                log("[YSMParser] " + line)
        if completed.returncode != 0:
            raise RuntimeError(f"YSMParser 返回错误码 {completed.returncode}")

        project_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
        if not project_dirs:
            project_dirs = [output_dir]
        return temp_root, project_dirs[0]
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def collect_ysm_files(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("请选择包含 .ysm 文件的目录。")
    return sorted(path for path in folder.rglob("*.ysm") if path.is_file())


def run_parser_batch(parser_exe, input_dir, output_dir, log_level="正常", log=None):
    parser_exe = Path(parser_exe)
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    if not parser_exe.is_file():
        raise FileNotFoundError(f"找不到 YSMParser.exe：{parser_exe}")
    if not input_dir.is_dir():
        raise ValueError(f"输入目录不存在：{input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_files = collect_ysm_files(input_dir)
    if not source_files:
        return []

    staging_root = Path(tempfile.mkdtemp(prefix="ysm_batch_unpack_"))
    staging_input = staging_root / "input"
    staging_output = staging_root / "output"
    staging_input.mkdir(parents=True, exist_ok=True)
    staging_output.mkdir(parents=True, exist_ok=True)

    copied_to_target = {}
    used_target_names = set()
    try:
        for index, source in enumerate(source_files, start=1):
            copied_name = f"{index:04d}.ysm"
            shutil.copy2(source, staging_input / copied_name)

            target_name = source.stem
            if target_name in used_target_names:
                target_name = f"{index:04d}_{target_name}"
            used_target_names.add(target_name)
            copied_to_target[Path(copied_name).stem] = target_name

        command = [str(parser_exe), "-i", str(staging_input), "-o", str(staging_output), "-j", "1"]
        if log_level == "调试":
            command.extend(["-v", "-d"])

        if log and log_level in ("详细", "调试"):
            log("批量解包命令：" + " ".join(f'"{part}"' if " " in part else part for part in command))

        completed = subprocess.run(
            command,
            cwd=str(parser_exe.parent),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        parser_output = completed.stdout or ""
        if log and parser_output:
            lines = parser_output.strip().splitlines()
            if log_level == "正常":
                lines = lines[-20:]
            elif log_level == "详细":
                lines = lines[-120:]
            elif log_level == "调试":
                lines = lines[-500:]
            else:
                lines = []
            for line in lines:
                log("[YSMParser] " + line)

        if completed.returncode != 0:
            raise RuntimeError(f"YSMParser 返回错误码 {completed.returncode}")

        projects = []
        for project in sorted(path for path in staging_output.iterdir() if path.is_dir()):
            target_name = copied_to_target.get(project.name, project.name)
            target_project = output_dir / target_name
            if target_project.exists():
                shutil.rmtree(target_project)
            shutil.copytree(project, target_project)
            projects.append(target_project)
        return projects
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


class CleanerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.main_thread = threading.current_thread()
        self.title("YSM 解包模型垃圾清理工具")
        self.geometry("1080x780")
        self.minsize(980, 680)
        self.project = None
        self.candidates = []
        self.selected_vars = {}

        self.folder_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.parser_var = tk.StringVar(value=find_default_parser_exe())
        self.batch_input_var = tk.StringVar()
        self.batch_output_var = tk.StringVar()
        self.batch_log_level_var = tk.StringVar(value="正常")
        self.batch_anti_action_var = tk.StringVar(value="保留 anti-parser 垃圾数据")
        self.default_hide_action_var = tk.StringVar(value=DEFAULT_HIDE_NONE)
        self.min_cubes_var = tk.IntVar(value=DEFAULT_MIN_CUBES)
        self.min_ratio_var = tk.DoubleVar(value=DEFAULT_MIN_RATIO)

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="YSM 工程或文件").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(top, textvariable=self.folder_var).grid(row=0, column=1, sticky=tk.EW, padx=8)
        ttk.Button(top, text="选择文件夹", command=self.choose_folder).grid(row=0, column=2)
        ttk.Button(top, text="选择 .ysm", command=self.choose_ysm_file).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(top, text="分析垃圾", command=self.analyze).grid(row=0, column=4, padx=(8, 0))
        ttk.Button(top, text="检测 anti-parser", command=self.detect_anti_parser).grid(row=0, column=5, padx=(8, 0))
        ttk.Button(top, text="保存日志", command=self.save_log).grid(row=0, column=6, padx=(8, 0))

        ttk.Label(top, text="输出文件夹").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(top, textvariable=self.output_var).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=(8, 0))
        ttk.Button(top, text="选择", command=self.choose_output).grid(row=1, column=2, pady=(8, 0))
        ttk.Button(top, text="保存清理副本", command=self.save).grid(row=1, column=3, padx=(8, 0), pady=(8, 0), columnspan=2, sticky=tk.EW)

        ttk.Label(top, text="YSMParser 0.3.6").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(top, textvariable=self.parser_var).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=(8, 0))
        ttk.Button(top, text="选择 Parser", command=self.choose_parser).grid(row=2, column=2, pady=(8, 0))

        ttk.Label(top, text="最小 cubes").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Spinbox(top, from_=1, to=1000000, textvariable=self.min_cubes_var, width=12).grid(row=3, column=1, sticky=tk.W, padx=8, pady=(8, 0))
        ttk.Label(top, text="最小占比").grid(row=3, column=1, sticky=tk.W, padx=(140, 0), pady=(8, 0))
        ttk.Spinbox(top, from_=0.01, to=1.0, increment=0.01, textvariable=self.min_ratio_var, width=8).grid(row=3, column=1, sticky=tk.W, padx=(210, 0), pady=(8, 0))

        top.columnconfigure(1, weight=1)

        batch = ttk.LabelFrame(self, text="批量解包", padding=10)
        batch.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Label(batch, text="输入目录").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(batch, textvariable=self.batch_input_var).grid(row=0, column=1, sticky=tk.EW, padx=8)
        ttk.Button(batch, text="选择", command=self.choose_batch_input).grid(row=0, column=2)

        ttk.Label(batch, text="输出目录").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(batch, textvariable=self.batch_output_var).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=(8, 0))
        ttk.Button(batch, text="选择", command=self.choose_batch_output).grid(row=1, column=2, pady=(8, 0))

        ttk.Label(batch, text="日志等级").grid(row=0, column=3, sticky=tk.W, padx=(12, 0))
        ttk.Combobox(batch, textvariable=self.batch_log_level_var, values=BATCH_LOG_LEVELS, state="readonly", width=8).grid(row=0, column=4, padx=8)
        ttk.Label(batch, text="anti-parser").grid(row=1, column=3, sticky=tk.W, padx=(12, 0), pady=(8, 0))
        ttk.Combobox(batch, textvariable=self.batch_anti_action_var, values=BATCH_ANTI_ACTIONS, state="readonly", width=24).grid(row=1, column=4, padx=8, pady=(8, 0))
        ttk.Label(batch, text="默认隐藏").grid(row=2, column=3, sticky=tk.W, padx=(12, 0), pady=(8, 0))
        ttk.Combobox(batch, textvariable=self.default_hide_action_var, values=DEFAULT_HIDE_ACTIONS, state="readonly", width=24).grid(row=2, column=4, padx=8, pady=(8, 0))
        ttk.Button(batch, text="一键批量解包", command=self.batch_unpack).grid(row=0, column=5, rowspan=3, sticky=tk.NSEW, padx=(8, 0))

        batch.columnconfigure(1, weight=1)

        middle = ttk.PanedWindow(self, orient=tk.VERTICAL)
        middle.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        candidate_frame = ttk.LabelFrame(middle, text="候选垃圾骨骼")
        middle.add(candidate_frame, weight=2)
        self.tree = ttk.Treeview(candidate_frame, columns=("select", "bones", "cubes", "ratio", "reason", "files"), show="headings", height=9)
        for col, text, width in (
            ("select", "删除", 60),
            ("bones", "骨骼数", 80),
            ("cubes", "Cubes", 100),
            ("ratio", "占比", 80),
            ("reason", "原因", 160),
            ("files", "动画引用", 360),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(candidate_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<ButtonRelease-1>", self.toggle_candidate)

        log_frame = ttk.LabelFrame(middle, text="日志")
        middle.add(log_frame, weight=3)
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=14)
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def choose_folder(self):
        folder = filedialog.askdirectory(title="选择解包后的 YSM 模型文件夹")
        if folder:
            self.folder_var.set(folder)
            self.output_var.set(str(Path(folder).with_name(Path(folder).name + "_bb_safe")))

    def choose_ysm_file(self):
        file_path = filedialog.askopenfilename(
            title="选择 .ysm 或 JSON 文件",
            filetypes=(("YSM/JSON", "*.ysm *.json"), ("YSM", "*.ysm"), ("JSON", "*.json"), ("All files", "*.*")),
        )
        if file_path:
            self.folder_var.set(file_path)
            self.output_var.set("")

    def choose_output(self):
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_var.set(folder)

    def choose_batch_input(self):
        folder = filedialog.askdirectory(title="选择包含 .ysm 文件的目录")
        if folder:
            self.batch_input_var.set(folder)
            if not self.batch_output_var.get().strip():
                self.batch_output_var.set(str(Path(folder).with_name(Path(folder).name + "_unpacked")))

    def choose_batch_output(self):
        folder = filedialog.askdirectory(title="选择批量解包输出目录")
        if folder:
            self.batch_output_var.set(folder)

    def choose_parser(self):
        file_path = filedialog.askopenfilename(
            title="选择 YSMParser 0.3.6 的 YSMParser.exe",
            filetypes=(("YSMParser", "YSMParser.exe"), ("Executable", "*.exe"), ("All files", "*.*")),
        )
        if file_path:
            self.parser_var.set(file_path)

    def log(self, message):
        if threading.current_thread() is not self.main_thread:
            self.after(0, self.log, message)
            return
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.update_idletasks()

    def save_log(self):
        content = self.log_text.get("1.0", tk.END).rstrip()
        if not content:
            messagebox.showinfo("保存日志", "当前没有可保存的日志。")
            return

        default_name = "ysm_tool_log_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        file_path = filedialog.asksaveasfilename(
            title="保存日志",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=(("Text", "*.txt"), ("All files", "*.*")),
        )
        if not file_path:
            return

        with Path(file_path).open("w", encoding="utf-8") as f:
            f.write(content + "\n")
        self.log(f"日志已保存：{file_path}")

    def analyze(self):
        self.run_async(self._analyze_impl)

    def _analyze_impl(self):
        self.clear_tree()
        folder = self.folder_var.get().strip()
        if not folder:
            raise ValueError("请先选择 YSM 工程文件夹。")

        self.log(f"读取工程：{folder}")
        project = YsmProject(folder)
        project.load()
        self.project = project
        self.log(f"主模型：{project.main_model_path}")
        self.log(f"骨骼数：{len(project.bones)}")
        self.log(f"Cubes：{project.total_cubes()}")

        candidates = project.find_candidates(self.min_cubes_var.get(), self.min_ratio_var.get())
        self.candidates = candidates
        if not candidates:
            self.log("没有找到符合阈值的隐藏垃圾子树。可以降低阈值后重新分析。")
            return

        self.log(f"找到 {len(candidates)} 个候选：")
        for idx, candidate in enumerate(candidates):
            self.selected_vars[candidate["name"]] = True
            reason = "scale=0 隐藏" if candidate["hidden_by_scale"] else "大体积辅助根"
            files = ", ".join(candidate["files"]) if candidate["files"] else "-"
            self.tree.insert("", tk.END, iid=candidate["name"], values=(
                "是",
                candidate["nodes"],
                candidate["cubes"],
                f"{candidate['ratio']:.1%}",
                reason,
                files,
            ))
        self.log(f"  {idx + 1}. {candidate['name']}：{candidate['nodes']} bones, {candidate['cubes']} cubes, {candidate['ratio']:.1%}, {reason}")

    def detect_anti_parser(self):
        self.run_async(self._detect_anti_parser_impl)

    def batch_unpack(self):
        input_dir = self.batch_input_var.get().strip()
        output_dir = self.batch_output_var.get().strip()
        if not input_dir:
            messagebox.showerror("错误", "请先选择批量解包输入目录。")
            return
        if not output_dir:
            output_dir = str(Path(input_dir).with_name(Path(input_dir).name + "_unpacked"))
            self.batch_output_var.set(output_dir)
        if Path(output_dir).exists():
            ok = messagebox.askyesno("确认输出", f"输出目录已存在，批量解包会写入该目录并可能覆盖同名文件：\n{output_dir}")
            if not ok:
                self.log("已取消批量解包。")
                return
        self.run_async(self._batch_unpack_impl)

    def _batch_unpack_impl(self):
        parser = self.parser_var.get().strip()
        input_dir = Path(self.batch_input_var.get().strip())
        output_dir = Path(self.batch_output_var.get().strip())
        log_level = self.batch_log_level_var.get()
        clean_anti = self.batch_anti_action_var.get().startswith("删除")
        default_hide_mode = self.default_hide_action_var.get()

        files = collect_ysm_files(input_dir)
        if not files:
            raise ValueError(f"输入目录没有找到 .ysm 文件：{input_dir}")

        self.log(f"批量解包开始：{input_dir}")
        self.log(f"输出目录：{output_dir}")
        self.log(f"发现 .ysm 文件：{len(files)}")
        self.log(f"日志等级：{log_level}")
        self.log("anti-parser 处理：" + ("删除诊断命中的垃圾数据" if clean_anti else "保留诊断命中的垃圾数据"))
        self.log(f"默认隐藏处理：{default_hide_mode}")

        started = datetime.now()
        projects = run_parser_batch(parser, input_dir, output_dir, log_level, self.log)

        total_high = 0
        total_warn = 0
        cleaned_projects = 0
        removed_bones = 0
        default_hidden_projects = 0
        default_hidden_bones = 0
        default_hidden_removed = 0
        report_lines = [
            "YSM batch unpack report",
            f"Started: {started.isoformat(timespec='seconds')}",
            f"Input: {input_dir}",
            f"Output: {output_dir}",
            f"YSM files: {len(files)}",
            f"Projects: {len(projects)}",
            f"Log level: {log_level}",
            "Anti-parser action: " + ("delete" if clean_anti else "keep"),
            f"Default hidden action: {default_hide_mode}",
            "",
        ]

        for project in projects:
            result = detect_anti_parser_payload(project)
            total_high += result["high_count"]
            total_warn += result["warn_count"]
            if log_level in ("正常", "详细", "调试") or result["high_count"] or result["warn_count"]:
                self.log(f"[批量] {project.name}: 数据特征命中 {result['high_count']}，辅助线索 {result['warn_count']}")

            clean_result = None
            if clean_anti and result["high_count"] > 0:
                clean_result = clean_anti_parser_garbage(project)
                if clean_result["removed_bones"]:
                    cleaned_projects += 1
                    removed_bones += len(clean_result["removed_bones"])
                    self.log(f"[清理] {project.name}: 删除 anti-parser 骨骼 {len(clean_result['removed_bones'])}，动画引用 {clean_result['cleaned_refs']}")

            hidden_result = None
            if default_hide_mode != DEFAULT_HIDE_NONE:
                hidden_result = apply_default_hidden_logic(project, default_hide_mode)
                if hidden_result["hidden_bones"]:
                    default_hidden_projects += 1
                    default_hidden_bones += len(hidden_result["hidden_bones"])
                    default_hidden_removed += len(hidden_result["removed_bones"])
                    if is_default_hide_write_mode(default_hide_mode):
                        self.log(f"[默认隐藏2.5] {project.name}: 识别 {len(hidden_result['hidden_bones'])} 个默认隐藏骨骼，已写入隐藏动画。未知条件 {hidden_result['skipped_conditional']}。")
                    elif is_default_hide_bake_mode(default_hide_mode):
                        self.log(f"[默认隐藏2.5] {project.name}: 识别 {len(hidden_result['hidden_bones'])} 个默认隐藏骨骼，已烘焙隐藏几何 {len(hidden_result['baked_bones'])} 个骨骼，cubes {hidden_result['old_cubes']} -> {hidden_result['new_cubes']}。")
                    else:
                        self.log(f"[默认隐藏2.5] {project.name}: 识别 {len(hidden_result['hidden_bones'])} 个默认隐藏骨骼，删除 {len(hidden_result['removed_bones'])} 个骨骼。未知条件 {hidden_result['skipped_conditional']}。")

            if log_level in ("详细", "调试"):
                for item in result["findings"]:
                    prefix = {"high": "[命中]", "warn": "[警告]", "info": "[信息]"}.get(item["severity"], "[信息]")
                    self.log(f"{prefix} {project.name} :: {item['where']} :: {item['detail']}")

            report_lines.append(f"Project: {project.name}")
            report_lines.append(f"  Path: {project}")
            report_lines.append(f"  Parser feature hits: {result['high_count']}")
            report_lines.append(f"  Name/plaintext clues: {result['warn_count']}")
            if clean_result:
                report_lines.append(f"  Removed anti-parser bones: {len(clean_result['removed_bones'])}")
                report_lines.append(f"  Clean report: {clean_result['report_path']}")
            if hidden_result:
                report_lines.append(f"  Default hidden bones: {len(hidden_result['hidden_bones'])}")
                report_lines.append(f"  Default hidden projectile/extra bones: {len(hidden_result['projectile_hidden_bones'])}")
                report_lines.append(f"  Default hidden projectile/extra name collisions skipped: {len(hidden_result['projectile_name_collisions'])}")
                report_lines.append(f"  Default hidden baked bones: {len(hidden_result['baked_bones'])}")
                report_lines.append(f"  Default hidden cubes: {hidden_result['old_cubes']} -> {hidden_result['new_cubes']}")
                report_lines.append(f"  Default hidden removed bones: {len(hidden_result['removed_bones'])}")
                report_lines.append(f"  Default hidden default-false conditions: {hidden_result['skipped_false']}")
                report_lines.append(f"  Default hidden unknown conditions: {hidden_result['skipped_conditional']}")
                report_lines.append(f"  Default hidden report: {hidden_result['report_path']}")
            report_lines.append("")

        batch_report = output_dir / "ysm_batch_unpack_report.txt"
        report_lines.extend([
            f"Finished: {datetime.now().isoformat(timespec='seconds')}",
            f"Total parser feature hits: {total_high}",
            f"Total name/plaintext clues: {total_warn}",
            f"Cleaned projects: {cleaned_projects}",
            f"Removed anti-parser bones: {removed_bones}",
            f"Default hidden projects: {default_hidden_projects}",
            f"Default hidden bones: {default_hidden_bones}",
            f"Default hidden removed bones: {default_hidden_removed}",
        ])
        with batch_report.open("w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")

        self.log("批量解包完成。")
        self.log(f"总数据特征命中：{total_high}")
        self.log(f"清理工程数：{cleaned_projects}")
        self.log(f"删除 anti-parser 骨骼：{removed_bones}")
        self.log(f"默认隐藏命中工程数：{default_hidden_projects}")
        self.log(f"默认隐藏骨骼：{default_hidden_bones}")
        if is_default_hide_delete_mode(default_hide_mode):
            self.log(f"删除默认隐藏骨骼：{default_hidden_removed}")
        self.log(f"批量报告：{batch_report}")
        self.after(0, messagebox.showinfo, "完成", f"批量解包完成：\n{output_dir}")

    def _detect_anti_parser_impl(self):
        target = self.folder_var.get().strip()
        if not target:
            raise ValueError("请先选择 YSM 工程文件夹、.ysm 文件或 JSON 文件。")

        self.log(f"检测 anti-parser 异常数据：{target}")
        temp_root = None
        parser36_success = False
        try:
            target_path = Path(target)
            if target_path.is_file() and target_path.suffix.lower() == ".ysm" and self.parser_var.get().strip():
                temp_root, unpacked_project = run_parser_to_temp_project(self.parser_var.get().strip(), target_path, self.log)
                parser36_success = True
                self.log(f"临时解包工程：{unpacked_project}")
                result = detect_anti_parser_payload(unpacked_project)
            else:
                if target_path.is_file() and target_path.suffix.lower() == ".ysm":
                    self.log("未设置 YSMParser.exe，先进行二进制轻量扫描。要深度检测，请选择 0.3.6 的 YSMParser.exe。")
                result = detect_anti_parser_payload(target)

            self.log(f"扫描文件数：{result['scanned_files']}")
            if result["high_count"] == 0:
                self.log("未发现 parser 内部数据特征命中。")
            else:
                self.log(f"发现 {result['high_count']} 条 parser 内部数据特征高危命中：")
            if result["warn_count"] > 0:
                self.log(f"另发现 {result['warn_count']} 条名字/明文辅助线索；这些线索不作为主判定依据。")

            for item in result["findings"]:
                prefix = {
                    "high": "[命中]",
                    "warn": "[警告]",
                    "info": "[信息]",
                }.get(item["severity"], "[信息]")
                self.log(f"{prefix} {item['file']} :: {item['where']} :: {item['detail']}")

            if result["high_count"] > 0:
                self.log("结论：该模型/工程命中 YSMParser 内部解析数据特征，疑似包含反解析异常数据。")
            elif result["warn_count"] > 0:
                self.log("结论：仅发现名字/明文辅助线索，未命中内部数据特征；建议用集成版 0.3.6 直接扫描 .ysm。")

            if target_path.is_file() and target_path.suffix.lower() == ".ysm" and parser36_success:
                diagnostics_path = unpacked_project / "_ysm_parser_diagnostics.json"
                if diagnostics_path.is_file():
                    self.log("已读取 YSMParser 0.3.6 内部诊断文件；这是当前优先使用的直接检测结果。")
                else:
                    self.log("当前 YSMParser.exe 未输出内部诊断文件；若要直接检测第一类自动剥离数据，请使用已修改源码重新编译的 0.3.6。")
        finally:
            if temp_root is not None:
                shutil.rmtree(temp_root, ignore_errors=True)
                self.log("临时解包目录已清理。")

    def clear_tree(self):
        self.selected_vars.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def toggle_candidate(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#1":
            return
        self.selected_vars[item] = not self.selected_vars.get(item, True)
        values = list(self.tree.item(item, "values"))
        values[0] = "是" if self.selected_vars[item] else "否"
        self.tree.item(item, values=values)

    def save(self):
        output = self.output_var.get().strip()
        if self.project and not output:
            output = str(self.project.folder.with_name(self.project.folder.name + "_bb_safe"))
            self.output_var.set(output)
        if output and Path(output).exists():
            ok = messagebox.askyesno("确认覆盖", f"输出文件夹已存在，保存时会先删除再重新生成：\n{output}")
            if not ok:
                self.log("已取消保存。")
                return
        self.run_async(self._save_impl)

    def _save_impl(self):
        if not self.project:
            raise ValueError("请先分析模型。")
        selected = [name for name, value in self.selected_vars.items() if value]
        if not selected:
            raise ValueError("没有勾选任何候选。")
        output = self.output_var.get().strip()
        if not output:
            output = str(self.project.folder.with_name(self.project.folder.name + "_bb_safe"))
            self.output_var.set(output)

        self.log(f"保存清理副本：{output}")
        result = self.project.save_clean_copy(selected, output)
        self.log(f"删除骨骼：{result['removed_bones']}")
        self.log(f"骨骼：{result['old_bones']} -> {result['new_bones']}")
        self.log(f"Cubes：{result['old_cubes']} -> {result['new_cubes']}")
        self.log(f"主模型大小：{result['bytes']} bytes")
        self.log(f"清理动画引用：{result['cleaned_refs']}")
        self.log(f"报告：{result['report_path']}")
        self.after(0, messagebox.showinfo, "完成", f"清理副本已保存：\n{result['output_folder']}")

    def run_async(self, target):
        def wrapper():
            try:
                target()
            except Exception as exc:
                self.log(f"错误：{exc}")
                self.after(0, messagebox.showerror, "错误", str(exc))
        threading.Thread(target=wrapper, daemon=True).start()


if __name__ == "__main__":
    app = CleanerApp()
    app.mainloop()
