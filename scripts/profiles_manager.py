# SPDX-License-Identifier: GPL-3.0-or-later
"""Project-based Plugin Profile Manager & Agentic CLI for IngeTrazo."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

APPDATA_DIR = Path(os.environ.get("APPDATA", "")) / "ingetrazo"
PLUGINS_DIR = APPDATA_DIR / "plugins"
PROFILES_FILE = APPDATA_DIR / "plugin_profiles.json"

SUPERSEDED_SPANISH = {"niveles", "propiedades_poligono"}
CORE_ENGLISH_ID = "english_defaults"


def scan_installed_plugins() -> dict[str, str]:
    """Returns {plugin_folder_name: 'active' | 'disabled'} for all plugins in PLUGINS_DIR."""
    result: dict[str, str] = {}
    if not PLUGINS_DIR.is_dir():
        return result
    for d in sorted(PLUGINS_DIR.iterdir(), key=lambda x: x.name.lower()):
        if not d.is_dir() or d.name.startswith(".") or d.name == "__pycache__":
            continue
        if (d / "__init__.py").is_file():
            result[d.name] = "active"
        elif (d / "__init__.py.disabled").is_file():
            result[d.name] = "disabled"
    return result


def get_active_plugins() -> list[str]:
    """Returns sorted list of currently active plugin IDs."""
    return [pid for pid, st in scan_installed_plugins().items() if st == "active"]


def _default_profiles(installed: dict[str, str]) -> dict[str, dict]:
    """Creates starter profiles tailored to current installation and agentic workflows."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    active_now = [pid for pid, st in installed.items() if st == "active"]
    all_ids = set(installed.keys())

    def _keep_installed(candidates: list[str]) -> list[str]:
        return [c for c in candidates if c in all_ids]

    return {
        "Current Full Snapshot": {
            "name": "Current Full Snapshot",
            "description": "Snapshot of all currently active plugins so you can restore your full setup anytime.",
            "mode": "exact",
            "always_keep_english": True,
            "plugins": active_now,
            "updated_at": now,
        },
        "Minimal English + AI": {
            "name": "Minimal English + AI",
            "description": "Lightweight core for fast startup and AI/MCP agentic modeling.",
            "mode": "exact",
            "always_keep_english": True,
            "plugins": _keep_installed([
                "english_defaults", "levels", "polygon_properties",
                "ai_assistant", "ai_bridge", "python_console", "model_info",
            ]),
            "updated_at": now,
        },
        "BIM & Architecture": {
            "name": "BIM & Architecture",
            "description": "OpenTrace BIM, parametric walls, openings, floor generator, and IFC tools.",
            "mode": "exact",
            "always_keep_english": True,
            "plugins": _keep_installed([
                "english_defaults", "levels", "polygon_properties",
                "opentrace_bim", "openings", "walls_tool", "ifc_editor",
                "planarq", "pisogen_arq", "ai_bridge",
            ]),
            "updated_at": now,
        },
        "Site, Survey & Point Clouds": {
            "name": "Site, Survey & Point Clouds",
            "description": "IngeScan, point clouds, GeoTIFF, terrain/roads, and site climate analysis.",
            "mode": "exact",
            "always_keep_english": True,
            "plugins": _keep_installed([
                "english_defaults", "levels", "polygon_properties",
                "ingescan", "pointcloud_splat", "igz_geotiff_import",
                "analisis_sitio", "terraroad", "grading_tool", "ai_bridge",
            ]),
            "updated_at": now,
        },
    }


def load_profiles() -> dict[str, dict]:
    """Loads profiles from plugin_profiles.json, seeding defaults on first run."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROFILES_FILE.is_file():
        profiles = _default_profiles(scan_installed_plugins())
        save_profiles(profiles)
        return profiles
    try:
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "profiles" in data and isinstance(data["profiles"], dict):
            return data["profiles"]
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    profiles = _default_profiles(scan_installed_plugins())
    save_profiles(profiles)
    return profiles


def save_profiles(profiles: dict[str, dict]) -> None:
    """Persists profiles dict to plugin_profiles.json."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "profiles": profiles}
    PROFILES_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _set_plugin_state(plugin_id: str, enable: bool) -> bool:
    """Enables or disables a single plugin by renaming __init__.py. Returns True if changed."""
    p_dir = PLUGINS_DIR / plugin_id
    if not p_dir.is_dir():
        return False
    init_f = p_dir / "__init__.py"
    dis_f = p_dir / "__init__.py.disabled"
    try:
        if enable and dis_f.is_file() and not init_f.is_file():
            dis_f.rename(init_f)
            return True
        if not enable and init_f.is_file():
            if dis_f.is_file():
                dis_f.unlink()
            init_f.rename(dis_f)
            return True
    except OSError:
        return False
    return False


def apply_profile(profile_name: str, profiles: dict[str, dict] | None = None) -> dict:
    """Applies a named profile to PLUGINS_DIR. Returns a summary dict."""
    if profiles is None:
        profiles = load_profiles()
    if profile_name not in profiles:
        raise KeyError(f"Profile '{profile_name}' not found.")

    prof = profiles[profile_name]
    mode = prof.get("mode", "exact")
    keep_eng = prof.get("always_keep_english", True)
    target_set = set(prof.get("plugins", []))
    installed = scan_installed_plugins()

    if keep_eng and CORE_ENGLISH_ID in installed:
        target_set.add(CORE_ENGLISH_ID)

    enabled_count = 0
    disabled_count = 0
    missing = [pid for pid in sorted(target_set) if pid not in installed]

    for pid, current_state in installed.items():
        if pid in SUPERSEDED_SPANISH and pid not in prof.get("plugins", []):
            # Keep superseded Spanish clones disabled
            if current_state == "active" and _set_plugin_state(pid, False):
                disabled_count += 1
            continue

        if pid in target_set:
            if current_state != "active" and _set_plugin_state(pid, True):
                enabled_count += 1
        elif mode == "exact":
            if current_state == "active" and _set_plugin_state(pid, False):
                disabled_count += 1

    return {
        "profile": profile_name,
        "mode": mode,
        "enabled": enabled_count,
        "disabled": disabled_count,
        "active_total": len(get_active_plugins()),
        "missing": missing,
    }


def handle_cli(argv: list[str]) -> int | None:
    """Handles headless CLI flags for agents. Returns exit code if handled, else None for GUI."""
    if not argv:
        return None

    if "--list-profiles" in argv:
        profiles = load_profiles()
        summary = [
            {
                "name": name,
                "mode": p.get("mode", "exact"),
                "plugin_count": len(p.get("plugins", [])),
                "description": p.get("description", ""),
            }
            for name, p in profiles.items()
        ]
        print(json.dumps({"profiles": summary, "active_plugins": len(get_active_plugins())}, indent=2))
        return 0

    if "--apply-profile" in argv:
        idx = argv.index("--apply-profile")
        if idx + 1 >= len(argv):
            print(json.dumps({"error": "Missing profile name after --apply-profile"}))
            return 2
        name = argv[idx + 1]
        try:
            res = apply_profile(name)
            print(json.dumps({"status": "ok", **res}, indent=2))
            return 0
        except KeyError as e:
            print(json.dumps({"status": "error", "error": str(e)}))
            return 1

    if "--save-active" in argv:
        idx = argv.index("--save-active")
        if idx + 1 >= len(argv):
            print(json.dumps({"error": "Missing profile name after --save-active"}))
            return 2
        name = argv[idx + 1]
        profiles = load_profiles()
        active = get_active_plugins()
        profiles[name] = {
            "name": name,
            "description": "Saved via CLI",
            "mode": "exact",
            "always_keep_english": True,
            "plugins": active,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_profiles(profiles)
        print(json.dumps({"status": "ok", "saved": name, "plugin_count": len(active)}, indent=2))
        return 0

    return None
