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


def analyze_score_metadata(
    mod: Any,
    measures: List[Any],
    manifest: Dict[str, Any],
    *,
    artist_hint: str = "",
    filename_stem: str = "",
) -> Dict[str, Any]:
    """Infer artist/title/tier and extract factual guitar/tab metrics."""
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
    harm_count = 0
    pm_count = 0
    grace_count = 0
    slap_count = 0
    link_count = 0
    arp_count = 0
    has_16th = False

    last_bar = measures[-1].bar if measures else 0
    active_mel: Optional[int] = None
    crossings = 0

    for meas in measures:
        events = getattr(meas, "events", []) or []
        for ev_idx, e in enumerate(events):
            if getattr(e, "dur", 0) == 1:
                has_16th = True
            if getattr(e, "arpeggio", False):
                arp_count += 1
            if getattr(e, "link_tech", None) in ("H", "P", "S"):
                link_count += 1
            if getattr(e, "rest", False):
                active_mel = None
                continue
            notes = getattr(e, "notes", ()) or ()
            pitched = [nt for nt in notes if getattr(nt, "role", "melody") != "slap"]
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

            for nt in notes:
                note_count += 1
                role = getattr(nt, "role", "melody")
                is_harm = bool(getattr(nt, "harmonic", False))
                if not is_harm and role != "slap" and nt.fret > max_fret:
                    max_fret = nt.fret
                if role == "slap":
                    slap_count += 1
                if is_harm:
                    harm_count += 1
                if getattr(nt, "palm_mute", False):
                    pm_count += 1
                if getattr(nt, "grace_from", None) is not None:
                    grace_count += 1

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

    explicit_tier = str(getattr(mod, "TIER", "") or "").strip().lower()
    if explicit_tier in TIER_LABELS:
        tier = explicit_tier
    elif tier_from_name in TIER_LABELS:
        tier = tier_from_name
    elif max_fret > 12:
        tier = "advanced"
    elif has_16th or tech_variety >= 1 or max_fret > 7:
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
        rows.append(
            f'<li><a href="{PLAYER_BASE_URL}?song={slug}">{artist} - {title}</a> '
            f'<small>({tier_label} · {capo_txt} · 最高{it["maxFret"]}品 · {it["bars"]}小节)</small></li>'
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
        print(f"[{status_tag}] {rel_path} -> {built['songBase']} ({built['tierLabel']}, {built['bars']} bars, 最高{built['maxFret']}品)")

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
                status = "✅ 通过"
                if rel_str.startswith("inbox/"):
                    status += f"（建议归档至 `{suggest_path}`）"
                rows.append(
                    f"| `{rel_str}` | {built['artist']} | {built['title']} | {built['tierLabel']} | "
                    f"{capo_txt} / {built['maxFret']}品 | {built['bars']} / {built['notes']} | "
                    f"{built['crossings']} | {status} |"
                )
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
                    # Also expose converted score_data.py under out_dir/converted/<idx>/
                    conv_dir = out_dir / "converted" / f"{idx:02d}"
                    conv_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(gen_py, conv_dir / Path(suggest_path).name)
                    rows.append(
                        f"| `{rel_str}` | {built['artist']} | {built['title']} | {built['tierLabel']} | "
                        f"{capo_txt} / {built['maxFret']}品 | {built['bars']} / {built['notes']} | "
                        f"{built['crossings']} | ✅ 已转源码并编译（可在 Artifact 下载 `{Path(suggest_path).name}` 并归档至 `{suggest_path}`） |"
                    )
            else:
                raise ValueError(f"不支持的文件类型或路径 '{rel_str}'（请放到 scores/<歌手>/*.py 或 inbox/<歌手>/*.mid|.musicxml|.mxl）")
        except Exception as exc:
            err_msg = str(exc).splitlines()[0][:240]
            failures.append(f"- `{rel_str}`: {err_msg}")
            rows.append(f"| `{rel_str}` | {artist_hint} | - | - | - | - | - | ❌ 失败 |")
            print(f"[FAIL] {rel_str}: {exc}", file=sys.stderr)

    lines = [
        "<!-- guitar-tab-pr-report -->",
        "### 指弹谱库 PR 自动质检与云端试编报告",
        "",
        "| 提交文件 | 歌手 | 曲目 | 档位 | Capo / 最高品 | 小节 / 音符 | 声部交叉 | 状态 |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
        *rows,
        "",
    ]
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
