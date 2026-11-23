#!/usr/bin/env python3
"""Pure-GitHub fingerstyle score library validator, incremental builder, and Pages packager."""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_SLUG = "zxsos/guitar-tab-library"
GITHUB_BLOB_BASE = f"https://github.com/{REPO_SLUG}/blob/main"
PLAYER_BASE_URL = "https://zxsos.github.io/guitar-tab-player/"
OPEN_TUNING_NO_CAPO: Dict[int, int] = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}
GUITAR_SCALE_CM = 65.0

MAX_PY_BYTES = 204_800  # 200 KB
MAX_BINARY_SCORE_BYTES = 5 * 1024 * 1024  # 5 MB for MIDI / MusicXML inbox files

TIER_LABELS: Dict[str, str] = {
    "beginner": "新手",
    "standard": "标准",
    "advanced": "进阶",
}
LABEL_TO_TIER: Dict[str, str] = {v: k for k, v in TIER_LABELS.items()}

FILENAME_RE = re.compile(r"^(?P<title>.+)_(?P<tierLabel>新手|标准|进阶)(?:_\d{1,3}分)?$")
LEAK_REGEX = re.compile(r"(textedit://|/home/|/Users/|C:\\Users\\)", re.IGNORECASE)
UNSAFE_PY_REGEX = re.compile(
    r"(\bos\.system\b|\bsubprocess\b|\bsocket\b|\burllib\b|\brequests\b|"
    r"\bshutil\.rmtree\b|\b__import__\b|\b(?:eval|exec|open|compile)\s*\()",
    re.IGNORECASE,
)

SAFE_IMPORT_MODULES = {"__future__", "dataclasses", "typing", "math", "enum"}
FORBIDDEN_CALL_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "input",
    "breakpoint",
}
FORBIDDEN_ATTR_NAMES = {"__subclasses__", "__globals__", "__builtins__", "__import__", "__code__"}

MIDI_OR_XML_EXTS = {".mid", ".midi", ".musicxml", ".xml", ".mxl"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sanitize_segment(raw: str, fallback: str = "Untitled") -> str:
    s = str(raw or "").strip()
    if ".." in s or "/" in s or "\\" in s:
        s = re.sub(r"[\\/]+", "_", s).replace("..", "")
    s = re.sub(r"[\u0000-\u001f\u007f]", "", s)
    s = re.sub(r'[:*?"<>|]', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"^[._-]+|[._-]+$", "", s)
    if len(s) > 60:
        s = re.sub(r"[._-]+$", "", s[:60])
    return s or fallback


def normalize_py_source(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").rstrip() + "\n"


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def security_check_py(py_path: Path) -> Tuple[str, str]:
    """Run static AST + regex + leak gate BEFORE importing or executing any .py file."""
    raw_bytes = py_path.read_bytes()
    if len(raw_bytes) > MAX_PY_BYTES:
        raise ValueError(f"{py_path.name}: 源码体积 {len(raw_bytes)} bytes 超过 200 KB 上限")
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{py_path.name}: 必须使用 UTF-8 编码 ({exc})") from exc

    norm_text = normalize_py_source(raw_text)
    if not norm_text.strip():
        raise ValueError(f"{py_path.name}: 源码为空")
    if LEAK_REGEX.search(norm_text):
        raise ValueError(f"{py_path.name}: 包含未脱敏的本地路径或 textedit:// 链接")
    if "def build_measures" not in norm_text or "Measure(" not in norm_text or "ev(" not in norm_text:
        raise ValueError(f"{py_path.name}: 缺少必要的 score_data.py 结构 (def build_measures / Measure / ev)")
    if UNSAFE_PY_REGEX.search(norm_text):
        raise ValueError(f"{py_path.name}: 检测到不允许的系统/网络/动态执行调用")

    try:
        tree = ast.parse(norm_text, filename=py_path.name)
    except SyntaxError as exc:
        raise ValueError(f"{py_path.name}: Python 语法错误第 {exc.lineno} 行: {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in SAFE_IMPORT_MODULES:
                    raise ValueError(f"{py_path.name}: 禁止导入非乐谱模块 '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top not in SAFE_IMPORT_MODULES:
                raise ValueError(f"{py_path.name}: 禁止从模块 '{node.module}' 导入")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALL_NAMES:
                raise ValueError(f"{py_path.name}: 禁止调用内置危险函数 '{node.func.id}()'")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTR_NAMES:
                raise ValueError(f"{py_path.name}: 禁止访问受限属性 '{node.attr}'")

    return norm_text, sha256_hex_bytes(norm_text.encode("utf-8"))


def _load_module_direct(py_path: Path) -> Any:
    mod_name = f"score_lib_{abs(hash(str(py_path.resolve())))}"
    spec = importlib.util.spec_from_file_location(mod_name, str(py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {py_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def finger_pos_cm(abs_fret: int) -> float:
    """Physical distance (cm) from guitar nut to finger placement center at absolute fret."""
    if abs_fret <= 0:
        return 0.0
    p0 = GUITAR_SCALE_CM * (1.0 - 2.0 ** (-(abs_fret - 1) / 12.0))
    p1 = GUITAR_SCALE_CM * (1.0 - 2.0 ** (-abs_fret / 12.0))
    return 0.5 * (p0 + p1)


def analyze_score_metadata(
    mod: Any,
    measures: List[Any],
    manifest: Dict[str, Any],
    *,
    artist_hint: str = "",
    filename_stem: str = "",
) -> Dict[str, Any]:
    """Infer artist/title/tier and compute physical playability score (0-100) + difficulty (1.0-10.0)."""
    title_from_name = ""
    tier_from_name = ""
    m_fn = FILENAME_RE.match(filename_stem)
    if m_fn:
        title_from_name = m_fn.group("title").replace("_", " ").strip()
        tier_from_name = LABEL_TO_TIER.get(m_fn.group("tierLabel"), "")

    raw_artist = (
        str(getattr(mod, "ARTIST", "") or "").strip()
        or str(artist_hint or "").strip()
        or str(getattr(mod, "COMPOSER", "") or "").strip()
        or str(manifest.get("composer") or "").strip()
    )
    raw_artist = re.sub(r"\s*[（(][^()（）]+[)）]\s*$", "", raw_artist).strip()
    if not raw_artist or raw_artist.lower() == "unknown":
        artist = "未分类"
    else:
        artist = sanitize_segment(raw_artist, "未分类")

    title = (
        str(getattr(mod, "TITLE", "") or "").strip()
        or str(manifest.get("title") or "").strip()
        or title_from_name
        or filename_stem.replace("_", " ").strip()
        or "Untitled"
    )

    capo = int(getattr(mod, "CAPO", manifest.get("capo", 0) or 0))
    bpm = int(getattr(mod, "TEMPO_BPM", manifest.get("bpm", 72) or 72))

    max_fret = 0
    note_count = 0
    pitched_count = 0
    non_rest_events = 0
    poly_events = 0
    max_simul = 0
    harm_count = 0
    pm_count = 0
    grace_count = 0
    slap_count = 0
    link_count = 0
    arp_count = 0
    sixteenth_events = 0
    tech_events = 0

    spans_cm: List[float] = []
    extreme_stretches: List[Tuple[int, float, int, int]] = []
    hard_stretches = 0
    impossible_chords: List[Tuple[int, int]] = []
    barre_events = 0
    awkward_shifts: List[Tuple[int, int, int, float]] = []
    large_shifts = 0
    shift_transitions = 0
    shift_velocities: List[float] = []

    non_pickup_bars = 0
    bass_bars = 0
    chord_bars = 0
    empty_bars = 0
    bar_slot_sums: List[int] = []
    bar_nps_list: List[float] = []
    distinct_bass: Set[int] = set()
    sections: Set[str] = set()
    dynamics: Set[float] = set()

    last_bar = measures[-1].bar if measures else 0
    active_mel: Optional[int] = None
    crossings = 0

    prev_anchor_cm: Optional[float] = None
    prev_mean_fret: Optional[float] = None
    elapsed_since_fretted_slots = 0
    total_slots = 0
    sec_per_slot = (60.0 / max(30, bpm)) / 4.0

    for meas in measures:
        events = getattr(meas, "events", []) or []
        is_pickup = bool(getattr(meas, "is_pickup", False))
        sec_label = getattr(meas, "section", None)
        if sec_label:
            sections.add(str(sec_label).strip())
        dynamics.add(round(float(getattr(meas, "dynamic", 1.0) or 1.0), 2))

        if not is_pickup:
            non_pickup_bars += 1
            if getattr(meas, "chords", None):
                chord_bars += 1
            if not events:
                empty_bars += 1

        bar_has_bass = False
        bar_pitched = 0
        bar_dur_sum = 0

        for ev_idx, e in enumerate(events):
            dur = max(1, int(getattr(e, "dur", 2) or 2))
            bar_dur_sum += dur
            total_slots += dur

            if dur == 1:
                sixteenth_events += 1
            ev_has_tech = False
            if getattr(e, "arpeggio", False):
                arp_count += 1
                ev_has_tech = True
            if getattr(e, "link_tech", None) in ("H", "P", "S"):
                link_count += 1
                ev_has_tech = True

            if getattr(e, "rest", False):
                active_mel = None
                elapsed_since_fretted_slots += dur
                continue

            notes = getattr(e, "notes", ()) or ()
            if not notes:
                elapsed_since_fretted_slots += dur
                continue

            non_rest_events += 1
            pitched = [nt for nt in notes if getattr(nt, "role", "melody") != "slap"]
            pitched_count += len(pitched)
            bar_pitched += len(pitched)
            if len(pitched) >= 2:
                poly_events += 1
            if len(pitched) > max_simul:
                max_simul = len(pitched)

            mels = [nt for nt in pitched if getattr(nt, "role", "melody") == "melody"]
            if mels:
                if any(getattr(nt, "harmonic", False) for nt in mels):
                    active_mel = None
                else:
                    active_mel = max(OPEN_TUNING_NO_CAPO[nt.string] + capo + nt.fret for nt in mels)

            is_closing = meas.bar == last_bar and ev_idx == len(events) - 1
            if not is_closing and active_mel is not None:
                for nt in pitched:
                    role = getattr(nt, "role", "melody")
                    if role in ("bass", "inner") and not getattr(nt, "harmonic", False):
                        cm = OPEN_TUNING_NO_CAPO[nt.string] + capo + nt.fret
                        if cm > active_mel:
                            crossings += 1

            fretted: List[Tuple[int, int]] = []
            for nt in notes:
                note_count += 1
                role = getattr(nt, "role", "melody")
                is_harm = bool(getattr(nt, "harmonic", False))
                if not is_harm and role != "slap":
                    if nt.fret > max_fret:
                        max_fret = nt.fret
                    if nt.fret > 0:
                        fretted.append((nt.string, nt.fret))
                if role == "bass":
                    bar_has_bass = True
                    distinct_bass.add(OPEN_TUNING_NO_CAPO[nt.string] + capo + nt.fret)
                elif role == "slap":
                    slap_count += 1
                    ev_has_tech = True
                if is_harm:
                    harm_count += 1
                    ev_has_tech = True
                if getattr(nt, "palm_mute", False):
                    pm_count += 1
                    ev_has_tech = True
                if getattr(nt, "grace_from", None) is not None:
                    grace_count += 1
                    ev_has_tech = True

            if ev_has_tech:
                tech_events += 1

            uniq_fretted = sorted(set(fretted))
            if uniq_fretted:
                frets_only = [f for _, f in uniq_fretted]
                min_f, max_f = min(frets_only), max(frets_only)
                at_min = [s for s, f in uniq_fretted if f == min_f]
                k = len(uniq_fretted)
                fingers_needed = (k - len(at_min) + 1) if len(at_min) >= 2 else k
                if fingers_needed > 4:
                    impossible_chords.append((meas.bar, fingers_needed))
                if (k >= 4 and len(at_min) >= 2) or (
                    k >= 3 and len(at_min) >= 2 and (max(at_min) - min(at_min)) >= 2
                ):
                    barre_events += 1

                if max_f > min_f:
                    span = finger_pos_cm(capo + max_f) - finger_pos_cm(capo + min_f)
                    spans_cm.append(span)
                    if span > 14.5:
                        extreme_stretches.append((meas.bar, round(span, 1), min_f, max_f))
                    elif span > 12.5:
                        hard_stretches += 1

                anchor = sum(finger_pos_cm(capo + f) for f in frets_only) / len(frets_only)
                mean_f = sum(frets_only) / len(frets_only)
                if prev_anchor_cm is not None and prev_mean_fret is not None:
                    dt = max(0.06, elapsed_since_fretted_slots * sec_per_slot)
                    shift_cm = abs(anchor - prev_anchor_cm)
                    fjump = abs(mean_f - prev_mean_fret)
                    shift_transitions += 1
                    shift_velocities.append(shift_cm / dt)
                    if fjump >= 4:
                        large_shifts += 1
                    if fjump >= 5 and shift_cm >= 12.0 and dt <= 0.28:
                        awkward_shifts.append((meas.bar, int(round(prev_mean_fret)), int(round(mean_f)), round(dt, 2)))
                prev_anchor_cm = anchor
                prev_mean_fret = mean_f
                elapsed_since_fretted_slots = dur
            else:
                elapsed_since_fretted_slots += dur

        if not is_pickup:
            if bar_has_bass:
                bass_bars += 1
            if bar_dur_sum > 0:
                bar_slot_sums.append(bar_dur_sum)
            bar_sec = max(0.25, (bar_dur_sum or 16) * sec_per_slot)
            bar_nps_list.append(bar_pitched / bar_sec)

    tech_variety = sum(
        1
        for flag in (
            link_count > 0,
            arp_count > 0,
            harm_count > 0,
            pm_count > 0,
            slap_count > 0,
            grace_count > 0,
        )
        if flag
    )

    # 1. Left-hand Playability (0..40)
    fretted_events_est = max(1, shift_transitions + 1)
    excess_hard = max(0, hard_stretches - int(fretted_events_est * 0.05))
    playability_f = 40.0
    playability_f -= min(18.0, len(impossible_chords) * 6.0)
    playability_f -= min(14.0, len(extreme_stretches) * 3.5)
    playability_f -= min(6.0, excess_hard * 0.8)
    playability_f -= min(8.0, len(awkward_shifts) * 1.5)
    playability_f -= min(10.0, crossings * 1.2)
    if max_fret > 17:
        playability_f -= 2.0
    playability_pts = max(0, min(40, int(round(playability_f))))

    # 2. Arrangement Richness (0..35)
    bass_ratio = bass_bars / max(1, non_pickup_bars)
    pts_bass = min(9.0, bass_ratio * 10.5) + min(2.0, len(distinct_bass) * 0.4)
    avg_poly = pitched_count / max(1, non_rest_events)
    poly_ratio = poly_events / max(1, non_rest_events)
    pts_poly = min(6.0, max(0.0, (avg_poly - 1.0) * 8.0)) + min(4.0, poly_ratio * 10.0)
    pts_tech = min(6.0, tech_variety * 1.6) + min(2.0, (tech_events / max(1, non_rest_events)) * 18.0)
    pts_struct = (
        min(3.0, len(sections) * 1.0)
        + min(2.0, max(0, len(dynamics) - 1) * 0.8)
        + (1.0 if non_pickup_bars >= 16 else (0.5 if non_pickup_bars >= 8 else 0.0))
    )
    arrangement_pts = max(0, min(35, int(round(pts_bass + pts_poly + pts_tech + pts_struct))))

    # 3. Notation Quality (0..25)
    if bar_slot_sums:
        dom_slots = max(set(bar_slot_sums), key=bar_slot_sums.count)
        aligned_bars = sum(1 for s in bar_slot_sums if s == dom_slots)
        unaligned_bars = max(0, non_pickup_bars - aligned_bars)
        aligned_ratio = aligned_bars / max(1, non_pickup_bars)
    else:
        unaligned_bars = non_pickup_bars
        aligned_ratio = 0.0
    chord_ratio = chord_bars / max(1, non_pickup_bars)
    has_title = bool(title and title != "Untitled")
    has_artist = bool(artist and artist != "未分类")
    has_setup = hasattr(mod, "CAPO") or bool(getattr(mod, "ARRANGER_INFO", ""))
    pts_meta = (
        (1.5 if has_title else 0.0)
        + (1.5 if has_artist else 0.0)
        + (1.0 if bpm > 0 else 0.0)
        + (1.0 if has_setup else 0.0)
    )
    pts_clean = max(0.0, 3.0 - empty_bars * 1.0 - (1.5 if non_pickup_bars < 4 else 0.0))
    notation_pts = max(0, min(25, int(round(aligned_ratio * 10.0 + min(7.0, chord_ratio * 7.8) + pts_meta + pts_clean))))

    quality_score = max(0, min(100, playability_pts + arrangement_pts + notation_pts))

    # Actionable diagnostics (top 5)
    issues: List[str] = []
    if impossible_chords:
        b0, f0 = impossible_chords[0]
        extra = f" 等 {len(impossible_chords)} 处" if len(impossible_chords) > 1 else ""
        issues.append(f"M{b0:02d}{extra} 同拍需 {f0} 指（超出左手可行范围）")
    if extreme_stretches:
        b0, sp0, mf0, xf0 = extreme_stretches[0]
        extra = f" 等 {len(extreme_stretches)} 处" if len(extreme_stretches) > 1 else ""
        issues.append(f"M{b0:02d}{extra} 左手跨度 {sp0:.1f}cm 过宽（{mf0}–{xf0}品）")
    if awkward_shifts:
        b0, pf0, nf0, dt0 = awkward_shifts[0]
        extra = f" 等 {len(awkward_shifts)} 处" if len(awkward_shifts) > 1 else ""
        issues.append(f"M{b0:02d}{extra} 快速大跳把位（{pf0}品→{nf0}品，{dt0:.2f}s）")
    if crossings > 0:
        issues.append(f"{crossings} 处声部交叉（伴奏高于旋律）")
    if non_pickup_bars >= 4 and bass_ratio < 0.5:
        issues.append(f"低音声部覆盖偏低（{int(round(bass_ratio * 100))}%）")
    if non_pickup_bars >= 4 and chord_ratio < 0.5:
        issues.append(f"和弦标记不足（{int(round(chord_ratio * 100))}%）")
    if unaligned_bars > 0:
        issues.append(f"{unaligned_bars} 个小节拍数未对齐")
    issues = issues[:5]

    # 4. Difficulty Index (Lv. 1.0 .. 10.0)
    dur_sec = max(1.0, total_slots * sec_per_slot)
    nps = pitched_count / dur_sec
    sorted_bnps = sorted(bar_nps_list) if bar_nps_list else [nps]
    p90_nps = sorted_bnps[min(len(sorted_bnps) - 1, int(len(sorted_bnps) * 0.9))]
    eff_nps = 0.55 * nps + 0.45 * p90_nps
    ratio_16th = sixteenth_events / max(1, non_rest_events)
    d_speed = min(
        3.0,
        max(0.0, (eff_nps - 1.0) * 0.42)
        + (0.35 if ratio_16th >= 0.08 else (0.15 if sixteenth_events > 0 else 0.0)),
    )

    sorted_spans = sorted(spans_cm) if spans_cm else [0.0]
    p95_span = sorted_spans[min(len(sorted_spans) - 1, int(len(sorted_spans) * 0.95))]
    barre_ratio = barre_events / max(1, non_rest_events)
    d_hand = min(
        2.2,
        min(1.3, max(0.0, (p95_span - 6.0) * 0.16)) + min(0.9, barre_ratio * 4.5),
    )

    avg_shift_vel = sum(shift_velocities) / max(1, len(shift_velocities))
    large_shift_ratio = large_shifts / max(1, shift_transitions)
    d_neck = min(
        1.8,
        min(0.9, max(0.0, (max_fret - 3) * 0.075))
        + min(0.9, large_shift_ratio * 3.0 + min(0.45, avg_shift_vel / 25.0)),
    )

    d_poly = min(1.4, max(0.0, (avg_poly - 1.0) * 1.1) + (0.3 if max_simul >= 4 else 0.0))
    d_tech = min(1.2, tech_variety * 0.18 + min(0.5, (tech_events / max(1, non_rest_events)) * 2.5))
    difficulty = round(min(10.0, max(1.0, 1.0 + d_speed + d_hand + d_neck + d_poly + d_tech)), 1)

    explicit_tier = str(getattr(mod, "TIER", "") or "").strip().lower()
    if explicit_tier in TIER_LABELS:
        tier = explicit_tier
    elif tier_from_name in TIER_LABELS:
        tier = tier_from_name
    elif difficulty >= 7.0 or max_fret > 12:
        tier = "advanced"
    elif difficulty >= 3.5 or sixteenth_events > 0 or tech_variety >= 1 or max_fret > 7:
        tier = "standard"
    else:
        tier = "beginner"

    bar_count = max(len(measures), len(manifest.get("bars") or []))
    manifest_notes = manifest.get("notes") or []
    total_notes = len(manifest_notes) if manifest_notes else note_count

    return {
        "artist": artist,
        "title": title,
        "tier": tier,
        "tierLabel": TIER_LABELS[tier],
        "bpm": bpm,
        "capo": capo,
        "bars": bar_count,
        "notes": total_notes,
        "maxFret": max_fret,
        "crossings": crossings,
        "qualityScore": quality_score,
        "scoreBreakdown": {
            "playability": playability_pts,
            "arrangement": arrangement_pts,
            "notation": notation_pts,
        },
        "scoreIssues": issues,
        "difficulty": difficulty,
    }


def _find_single_artifact(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"Expected artifact matching '{pattern}' in {directory}")
    return matches[0]


def _run_subprocess(cmd: List[str], *, cwd: Path) -> str:
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    combined = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\n{combined.strip()}")
    return combined.strip()


def build_single_py(
    py_path: Path,
    *,
    skill_scripts: Path,
    artist_hint: str,
    rel_path: str,
    dest_dir: Path,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate and build one score_data.py into dest_dir/<slug>/ (with optional SHA-256 cache)."""
    norm_text, sha256 = security_check_py(py_path)
    slug = sha256[:12]
    song_dir = dest_dir / "songs" / slug
    if song_dir.exists():
        shutil.rmtree(song_dir)
    song_dir.mkdir(parents=True, exist_ok=True)

    cache_entry = (cache_dir / sha256[:16]) if cache_dir else None
    if cache_entry and (cache_entry / "meta.json").is_file():
        try:
            cached = json.loads((cache_entry / "meta.json").read_text(encoding="utf-8"))
            req_files = [
                cached["manifestFile"],
                cached["audioFile"],
                cached["pdfFile"],
                cached["bundleFile"],
                "score_data.py",
                *cached["pages"],
            ]
            if all((cache_entry / f).is_file() for f in req_files):
                shutil.copytree(cache_entry, song_dir, dirs_exist_ok=True)
                # Refresh path/metrics cleanly if filename or folder changed
                mod = _load_module_direct(py_path)
                measures = mod.build_measures()
                manifest = json.loads((song_dir / cached["manifestFile"]).read_text(encoding="utf-8"))
                info = analyze_score_metadata(
                    mod,
                    measures,
                    manifest,
                    artist_hint=artist_hint,
                    filename_stem=py_path.stem,
                )
                return _assemble_item(cached, info, sha256=sha256, slug=slug, rel_path=rel_path, cached=True)
        except Exception:
            pass  # Cache corrupt or incompatible -> rebuild cleanly

    with tempfile.TemporaryDirectory(prefix="gtl_build_") as tmp_str:
        tmp_proj = Path(tmp_str)
        src_dir = tmp_proj / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        staged_py = src_dir / "score_data.py"
        staged_py.write_text(norm_text, encoding="utf-8")

        engine_py = skill_scripts / "tab_engine.py"
        skill_root = skill_scripts.parent.parent.parent
        _run_subprocess([sys.executable, str(engine_py), "build", str(tmp_proj)], cwd=skill_root)

        manifest_src = tmp_proj / "sync_manifest.json"
        manifest = json.loads(manifest_src.read_text(encoding="utf-8"))
        mp3_src = tmp_proj / manifest["audio"]
        pdf_src = tmp_proj / manifest["pdf"]
        bundle_src = _find_single_artifact(tmp_proj, "*_bundle.zip")
        pngs = sorted((tmp_proj / "previews").glob("page-*.png"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))
        if not pngs:
            raise FileNotFoundError("No preview page-*.png rendered")

        shutil.copy2(manifest_src, song_dir / "sync_manifest.json")
        shutil.copy2(mp3_src, song_dir / mp3_src.name)
        shutil.copy2(pdf_src, song_dir / pdf_src.name)
        shutil.copy2(bundle_src, song_dir / bundle_src.name)
        (song_dir / "score_data.py").write_text(norm_text, encoding="utf-8")
        previews_out = song_dir / "previews"
        previews_out.mkdir(parents=True, exist_ok=True)
        page_rels: List[str] = []
        for png in pngs:
            shutil.copy2(png, previews_out / png.name)
            page_rels.append(f"previews/{png.name}")

        mod = _load_module_direct(staged_py)
        measures = mod.build_measures()
        info = analyze_score_metadata(
            mod,
            measures,
            manifest,
            artist_hint=artist_hint,
            filename_stem=py_path.stem,
        )

        meta = {
            "duration": round(float(manifest.get("duration") or 0.0), 3),
            "manifestFile": "sync_manifest.json",
            "audioFile": mp3_src.name,
            "pdfFile": pdf_src.name,
            "bundleFile": bundle_src.name,
            "pages": page_rels,
        }
        (song_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if cache_entry is not None:
            if cache_entry.exists():
                shutil.rmtree(cache_entry)
            shutil.copytree(song_dir, cache_entry)

        return _assemble_item(meta, info, sha256=sha256, slug=slug, rel_path=rel_path, cached=False)


def _assemble_item(
    meta: Dict[str, Any],
    info: Dict[str, Any],
    *,
    sha256: str,
    slug: str,
    rel_path: str,
    cached: bool,
) -> Dict[str, Any]:
    encoded_rel = "/".join(urllib.parse.quote(seg) for seg in rel_path.split("/"))
    return {
        "slug": slug,
        "path": rel_path,
        "artist": info["artist"],
        "title": info["title"],
        "tier": info["tier"],
        "tierLabel": info["tierLabel"],
        "bpm": info["bpm"],
        "capo": info["capo"],
        "maxFret": info["maxFret"],
        "bars": info["bars"],
        "notes": info["notes"],
        "duration": meta["duration"],
        "crossings": info["crossings"],
        "qualityScore": info["qualityScore"],
        "scoreBreakdown": info["scoreBreakdown"],
        "scoreIssues": info["scoreIssues"],
        "difficulty": info["difficulty"],
        "sha256": sha256,
        "songBase": f"songs/{slug}/",
        "manifestFile": meta["manifestFile"],
        "audioFile": meta["audioFile"],
        "pdfFile": meta["pdfFile"],
        "bundleFile": meta["bundleFile"],
        "pages": meta["pages"],
        "githubUrl": f"{GITHUB_BLOB_BASE}/{encoded_rel}",
        "cached": cached,
    }


def _write_pages_shell(out_dir: Path, catalog: Dict[str, Any]) -> None:
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    rows = []
    for it in catalog["items"]:
        artist = html.escape(it["artist"])
        title = html.escape(it["title"])
        tier_label = html.escape(it["tierLabel"])
        slug = urllib.parse.quote(it["slug"])
        capo_txt = f"Capo {it['capo']}" if it.get("capo", 0) > 0 else "标准调弦"
        lv_txt = f"Lv.{it['difficulty']:.1f}" if it.get("difficulty") is not None else ""
        sc_txt = f"{it['qualityScore']}分" if it.get("qualityScore") is not None else ""
        extra = " · ".join(x for x in (tier_label, lv_txt, sc_txt, capo_txt, f"最高{it['maxFret']}品") if x)
        rows.append(
            f'<li><a href="{PLAYER_BASE_URL}?song={slug}">{artist} - {title}</a> '
            f'<small>({extra})</small></li>'
        )
    list_html = "\n        ".join(rows) if rows else "<li>暂无曲目</li>"
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Guitar TAB Library · 在线指弹曲库</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; max-width: 720px; margin: 48px auto; padding: 0 20px; color: #18181b; line-height: 1.6; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    .cta {{ display: inline-block; margin: 12px 0 20px; padding: 10px 18px; border-radius: 10px; background: #4f46e5; color: #fff; text-decoration: none; font-weight: 600; }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 8px 0; }}
    a {{ color: #4f46e5; }}
    small {{ color: #71717a; }}
  </style>
</head>
<body>
  <h1>Guitar TAB Library · 在线指弹谱库</h1>
  <p>本站点托管自动化编译的指弹谱库产物（<code>catalog.json</code>），推荐在练习播放器中直接浏览与练琴。</p>
  <a class="cta" href="{PLAYER_BASE_URL}">打开在线指弹播放器</a>
  <h2>已收录曲目（{len(catalog["items"])}）</h2>
  <ul>
    {list_html}
  </ul>
</body>
</html>
"""
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")


def run_publish_mode(
    repo_root: Path,
    skill_scripts: Path,
    out_dir: Path,
    cache_dir: Optional[Path],
    write_index: bool,
) -> int:
    scores_root = repo_root / "scores"
    py_files = sorted(scores_root.glob("*/*.py")) if scores_root.is_dir() else []
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)

    existing_timestamps: Dict[Tuple[str, str], str] = {}
    index_path = repo_root / "index.json"
    if index_path.is_file():
        try:
            old_idx = json.loads(index_path.read_text(encoding="utf-8"))
            for old_it in old_idx.get("items") or []:
                existing_timestamps[(str(old_it.get("path", "")), str(old_it.get("sha256", "")))] = str(
                    old_it.get("updatedAt") or ""
                )
        except Exception:
            pass

    now = _now_iso()
    catalog_items: List[Dict[str, Any]] = []
    index_items: List[Dict[str, Any]] = []
    used_slugs: Set[str] = set()

    for py_path in py_files:
        rel_path = py_path.relative_to(repo_root).as_posix()
        artist_hint = py_path.parent.name
        built = build_single_py(
            py_path,
            skill_scripts=skill_scripts,
            artist_hint=artist_hint,
            rel_path=rel_path,
            dest_dir=out_dir,
            cache_dir=cache_dir,
        )
        slug = built["slug"]
        if slug in used_slugs:
            # Handle rare identical-source copies across folders without overwriting
            suffix = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:4]
            new_slug = f"{slug}_{suffix}"
            shutil.move(str(out_dir / "songs" / slug), str(out_dir / "songs" / new_slug))
            built["slug"] = new_slug
            built["songBase"] = f"songs/{new_slug}/"
        used_slugs.add(built["slug"])

        updated_at = existing_timestamps.get((rel_path, built["sha256"])) or now
        built["updatedAt"] = updated_at
        status_tag = "CACHED" if built.pop("cached", False) else "BUILT"
        print(
            f"[{status_tag}] {rel_path} -> {built['songBase']} "
            f"({built['tierLabel']}, {built['qualityScore']}分, Lv.{built['difficulty']:.1f}, {built['bars']} bars)"
        )

        catalog_items.append(built)
        index_items.append(
            {
                "path": rel_path,
                "artist": built["artist"],
                "title": built["title"],
                "tier": built["tier"],
                "tierLabel": built["tierLabel"],
                "bpm": built["bpm"],
                "capo": built["capo"],
                "maxFret": built["maxFret"],
                "bars": built["bars"],
                "notes": built["notes"],
                "qualityScore": built["qualityScore"],
                "difficulty": built["difficulty"],
                "sha256": built["sha256"],
                "updatedAt": updated_at,
            }
        )

    catalog_items.sort(key=lambda x: (x["artist"], x["title"], x["tier"], x["path"]))
    index_items.sort(key=lambda x: (x["artist"], x["title"], x["tier"], x["path"]))

    catalog = {
        "version": 1,
        "updatedAt": max((it["updatedAt"] for it in catalog_items), default=now),
        "repo": REPO_SLUG,
        "items": catalog_items,
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_pages_shell(out_dir, catalog)
    print(f"[PASS] Packaged {len(catalog_items)} score(s) into {out_dir}")

    if write_index:
        new_index = {
            "version": 1,
            "updatedAt": catalog["updatedAt"],
            "items": index_items,
        }
        index_path.write_text(json.dumps(new_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[PASS] Refreshed {index_path.name} ({len(index_items)} items)")
    return 0


def _detect_pr_changed_files(repo_root: Path) -> List[str]:
    cmd = ["git", "-c", "core.quotePath=false", "diff", "--name-only", "-z", "--diff-filter=AM", "HEAD~1", "HEAD"]
    res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True)
    if res.returncode != 0:
        return []
    raw = res.stdout.decode("utf-8", errors="replace")
    return [p for p in raw.split("\0") if p and (p.startswith("scores/") or p.startswith("inbox/"))]


def run_pr_mode(
    repo_root: Path,
    skill_scripts: Path,
    files: List[str],
    out_dir: Path,
    report_out: Optional[Path],
) -> int:
    candidates = [f.strip() for f in files if f.strip()]
    if not candidates:
        candidates = _detect_pr_changed_files(repo_root)

    targets = [f for f in candidates if f.startswith("scores/") or f.startswith("inbox/")]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[str] = []
    diag_notes: List[str] = []
    failures: List[str] = []

    if not targets:
        md = (
            "<!-- guitar-tab-pr-report -->\n"
            "### 指弹谱库 PR 自动质检\n\n"
            "本次变更未涉及 `scores/` 或 `inbox/` 下的曲谱文件，无需重新编译。\n"
        )
        if report_out:
            report_out.write_text(md, encoding="utf-8")
        print("[INFO] No score files changed in PR.")
        return 0

    for idx, rel_str in enumerate(targets):
        fpath = (repo_root / rel_str).resolve()
        if not fpath.is_file():
            failures.append(f"`{rel_str}`: 文件不存在")
            continue

        rel_parts = Path(rel_str).parts
        artist_hint = rel_parts[1] if len(rel_parts) >= 3 else "未分类"
        ext = fpath.suffix.lower()

        try:
            if ext == ".py":
                built = build_single_py(
                    fpath,
                    skill_scripts=skill_scripts,
                    artist_hint=artist_hint,
                    rel_path=rel_str,
                    dest_dir=out_dir,
                )
                suggest_path = (
                    f"scores/{built['artist']}/"
                    f"{sanitize_segment(built['title'], 'Untitled')}_{built['tierLabel']}.py"
                )
                capo_txt = f"Capo {built['capo']}" if built["capo"] > 0 else "无变调夹"
                bd = built["scoreBreakdown"]
                score_cell = f"**{built['qualityScore']}** ({bd['playability']}/{bd['arrangement']}/{bd['notation']})"
                diff_cell = f"Lv.{built['difficulty']:.1f}"
                status = "✅ 通过"
                if rel_str.startswith("inbox/"):
                    status += f"（建议归档至 `{suggest_path}`）"
                rows.append(
                    f"| `{rel_str}` | {built['artist']} - {built['title']} ({built['tierLabel']}) | "
                    f"{score_cell} | {diff_cell} | {capo_txt} / {built['maxFret']}品 | {status} |"
                )
                if built.get("scoreIssues"):
                    diag_notes.append(f"- `{rel_str}`: " + "；".join(built["scoreIssues"]))
            elif rel_str.startswith("inbox/") and ext in MIDI_OR_XML_EXTS:
                if fpath.stat().st_size > MAX_BINARY_SCORE_BYTES:
                    raise ValueError(f"{fpath.name}: 体积超过 5 MB 上限")
                with tempfile.TemporaryDirectory(prefix="gtl_import_") as imp_tmp:
                    imp_proj = Path(imp_tmp)
                    import_py = skill_scripts / "import_score.py"
                    skill_root = skill_scripts.parent.parent.parent
                    _run_subprocess(
                        [sys.executable, str(import_py), str(fpath), "--out", str(imp_proj), "--artist", artist_hint],
                        cwd=skill_root,
                    )
                    gen_py = imp_proj / "src" / "score_data.py"
                    built = build_single_py(
                        gen_py,
                        skill_scripts=skill_scripts,
                        artist_hint=artist_hint,
                        rel_path=rel_str,
                        dest_dir=out_dir,
                    )
                    suggest_path = (
                        f"scores/{built['artist']}/"
                        f"{sanitize_segment(built['title'], 'Untitled')}_{built['tierLabel']}.py"
                    )
                    capo_txt = f"Capo {built['capo']}" if built["capo"] > 0 else "无变调夹"
                    bd = built["scoreBreakdown"]
                    score_cell = f"**{built['qualityScore']}** ({bd['playability']}/{bd['arrangement']}/{bd['notation']})"
                    diff_cell = f"Lv.{built['difficulty']:.1f}"
                    conv_dir = out_dir / "converted" / f"{idx:02d}"
                    conv_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(gen_py, conv_dir / Path(suggest_path).name)
                    rows.append(
                        f"| `{rel_str}` | {built['artist']} - {built['title']} ({built['tierLabel']}) | "
                        f"{score_cell} | {diff_cell} | {capo_txt} / {built['maxFret']}品 | "
                        f"✅ 已转源码并编译（可在 Artifact 下载 `{Path(suggest_path).name}` 并归档至 `{suggest_path}`） |"
                    )
                    if built.get("scoreIssues"):
                        diag_notes.append(f"- `{rel_str}`: " + "；".join(built["scoreIssues"]))
            else:
                raise ValueError(f"不支持的文件类型或路径 '{rel_str}'（请放到 scores/<歌手>/*.py 或 inbox/<歌手>/*.mid|.musicxml|.mxl）")
        except Exception as exc:
            err_msg = str(exc).splitlines()[0][:240]
            failures.append(f"- `{rel_str}`: {err_msg}")
            rows.append(f"| `{rel_str}` | {artist_hint} | - | - | - | ❌ 失败 |")
            print(f"[FAIL] {rel_str}: {exc}", file=sys.stderr)

    lines = [
        "<!-- guitar-tab-pr-report -->",
        "### 指弹谱库 PR 自动质检与云端试编报告",
        "",
        "| 提交文件 | 曲目 | 评分 (手型/编配/规范) | 难度 | Capo / 最高品 | 状态 |",
        "| :--- | :--- | :---: | :---: | :---: | :--- |",
        *rows,
        "",
    ]
    if diag_notes:
        lines.extend(["#### 谱面物理手型与编配诊断", "", *diag_notes, ""])
    if failures:
        lines.extend(["#### 错误详情", "", *failures, ""])
    else:
        lines.append("全部校验与云端试编已通过，试听 MP3 / 六线谱 PDF / 同步包已上传至本次 Check 的 Artifacts，确认无误后可直接点击 **Merge** 上架播放器。")

    report_md = "\n".join(lines).rstrip() + "\n"
    if report_out:
        report_out.write_text(report_md, encoding="utf-8")
    print(report_md)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate, build, and package guitar-tab-library.")
    parser.add_argument("--mode", required=True, choices=("pr", "publish"))
    parser.add_argument("--skill-scripts", required=True, help="Path to fingerstyle-guitar-tab/scripts")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--out-dir", required=True, help="Output directory (_site or _pr_out)")
    parser.add_argument("--cache-dir", default=None, help="Incremental build cache directory")
    parser.add_argument("--report-out", default=None, help="Markdown report path for PR mode")
    parser.add_argument("--write-index", action="store_true", help="Refresh repo root index.json in publish mode")
    parser.add_argument("--files", nargs="*", default=[], help="Changed/added files for PR mode")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    skill_scripts = Path(args.skill_scripts).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    cache_dir = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else None
    report_out = Path(args.report_out).expanduser().resolve() if args.report_out else None

    if args.mode == "publish":
        return run_publish_mode(repo_root, skill_scripts, out_dir, cache_dir, args.write_index)
    return run_pr_mode(repo_root, skill_scripts, list(args.files), out_dir, report_out)


if __name__ == "__main__":
    raise SystemExit(main())
