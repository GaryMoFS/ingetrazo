import sys
from pathlib import Path

# Ensure script directory is in sys.path
_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from patcher_tab import PatcherTab
from profiles_tab import ProfilesTab
import profiles_manager
import concurrent.futures
import ctypes
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import zipfile

# --- Enable Native High-DPI Awareness (Crisp Rendering) ---
def enable_high_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

enable_high_dpi_awareness()

CATALOG_URL = "https://raw.githubusercontent.com/ingelibre/ingetrazo-extensions/main/catalog.json"
PLUGINS_DIR = Path(os.environ.get("APPDATA", "")) / "ingetrazo" / "plugins"
IGNORED_FILE = Path(os.environ.get("APPDATA", "")) / "ingetrazo" / "ignored_plugins.json"
CACHE_FILE = PLUGINS_DIR.parent / "catalog_cache.json"

# Translations for Portuguese / Spanish community plugins to English
NAME_TRANSLATIONS = {
    "combinacao_de_camadas": "Layer Combinations",
    "contexto": "Site Context & Location",
    "croquis": "Architectural Hand Sketches",
    "lista_corte_marcenaria": "Woodworking Cut List",
    "propiedades_poligono": "Polygon Properties",
    "niveles": "Building Levels & Elevations",
    "automacao": "Parametric Automation",
    "planarq": "Architectural Drafting Tools",
    "lineas_color": "Colored Line Styles",
    "ja_lineastyle": "Colored Line Styles",
    "ui_colores_space": "Colored Toolbar & Space Tools",
    "aberturas": "Doors & Windows Openings",
    "ingefloor": "Architectural Flooring",
}

DARK_THEME = {
    "bg": "#1e2227",
    "surface": "#21252b",
    "card": "#282c34",
    "border": "#3e4451",
    "fg": "#e8eaed",
    "muted": "#9aa5b1",
    "accent": "#3182ce",
    "accent_hover": "#2b6cb0",
    "btn_bg": "#2d333b",
    "btn_fg": "#e8eaed",
    "select_bg": "#3e4451",
    "select_fg": "#ffffff",
    "installed": "#7ce0a3",
    "disabled": "#a0aec0",
    "outdated": "#f6ad55",
    "missing": "#9aa5b1",
}

LIGHT_THEME = {
    "bg": "#f4f6f8",
    "surface": "#ffffff",
    "card": "#ffffff",
    "border": "#d0d7de",
    "fg": "#1a202c",
    "muted": "#718096",
    "accent": "#2b6cb0",
    "accent_hover": "#2c5282",
    "btn_bg": "#edf2f7",
    "btn_fg": "#1a202c",
    "select_bg": "#cbd5e0",
    "select_fg": "#1a202c",
    "installed": "#2e7d32",
    "disabled": "#718096",
    "outdated": "#d84315",
    "missing": "#718096",
}

def parse_version_tuple(v_str: str) -> tuple:
    if not v_str or v_str == "-":
        return (-1,)
    parts = re.findall(r"\d+", str(v_str))
    return tuple(int(p) for p in parts) if parts else (0,)

def normalize_catalog(raw_data) -> dict[str, dict]:
    normalized = {}
    if isinstance(raw_data, dict):
        if "extensions" in raw_data and isinstance(raw_data["extensions"], list):
            items = raw_data["extensions"]
        else:
            items = list(raw_data.values())
    elif isinstance(raw_data, list):
        items = raw_data
    else:
        items = []

    for entry in items:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        ext_id = str(entry["id"]).strip()

        # Handle localized dict for name
        raw_name = entry.get("name")
        if isinstance(raw_name, dict):
            name = raw_name.get("en") or raw_name.get("es") or raw_name.get("pt") or ext_id
        elif isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip()
        else:
            name = ext_id.replace("_", " ").title()

        # Append English clarification if originally in Portuguese / Spanish
        clean_id = ext_id.lower().replace("-", "_")
        if clean_id in NAME_TRANSLATIONS and NAME_TRANSLATIONS[clean_id].lower() not in name.lower():
            name = f"{NAME_TRANSLATIONS[clean_id]} ({name})"

        # Handle localized dict for description / summary
        raw_desc = entry.get("summary") or entry.get("description") or ""
        if isinstance(raw_desc, dict):
            desc = raw_desc.get("en") or raw_desc.get("es") or raw_desc.get("pt") or ""
        elif isinstance(raw_desc, str):
            desc = raw_desc.strip()
        else:
            desc = ""

        author = entry.get("author", "Community")
        license_type = entry.get("license") or entry.get("licence") or "Open Source"

        normalized[ext_id] = {
            "id": ext_id,
            "name": name,
            "version": str(entry.get("version", "1.0.0")),
            "sha256": str(entry.get("sha256", "")).lower().strip(),
            "download": str(entry.get("download", "")).strip(),
            "description": desc,
            "author": author,
            "license": license_type
        }
    return normalized

def fetch_url_bytes(url: str, timeout: int = 6) -> bytes:
    if shutil.which("curl.exe"):
        try:
            res = subprocess.run(
                ["curl.exe", "-s", "--compressed", "--connect-timeout", "3", "-m", str(timeout), url],
                capture_output=True,
                timeout=timeout + 2
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "IngeTrazo-Manager/1.0", "Accept-Encoding": "gzip, deflate"}
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data
    except Exception:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data

class Tooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tip_window = None
        self.last_row = None

    def show(self, text: str, x: int, y: int, is_dark: bool = True):
        self.hide()
        bg = "#282c34" if is_dark else "#ffffff"
        fg = "#e8eaed" if is_dark else "#1a202c"
        border = "#3e4451" if is_dark else "#d0d7de"

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x + 16}+{y + 16}")

        frame = tk.Frame(tw, background=border, bd=1)
        frame.pack(fill=tk.BOTH)

        lbl = tk.Label(
            frame,
            text=text,
            justify=tk.LEFT,
            background=bg,
            foreground=fg,
            relief=tk.FLAT,
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
            wraplength=500
        )
        lbl.pack()

    def hide(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
        self.last_row = None

class PluginManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("IngeTrazo - Plugin & Extension Manager")
        self.root.geometry("1020x680")
        self.root.minsize(860, 520)

        self.is_dark = True
        self.theme = DARK_THEME

        self.catalog: dict[str, dict] = {}
        self.checked_ids: set[str] = set()
        self.ignored_ids: set[str] = self._load_ignored()
        self.local_meta_cache: dict[str, dict] = {}
        self.local_status_cache: dict[str, str] = {}  # ext_id -> "active" | "disabled"
        self.is_busy = False

        self.sort_state = {}
        self.tooltip = Tooltip(self.root)
        self.patcher_tab = None
        self.profiles_tab = None

        self._create_widgets()
        self._apply_theme()

        self._load_local_data_instant()
        self._populate_table("Ready.")

        threading.Thread(target=self._background_check_updates, daemon=True).start()
        self.root.after(1500, self._check_update_notice)

    def _create_widgets(self):
        # 1. Header Frame
        self.header_frame = tk.Frame(self.root, padx=14, pady=8)
        self.header_frame.pack(fill=tk.X)

        self.title_lbl = tk.Label(
            self.header_frame, text="IngeTrazo Plugin Manager", font=("Segoe UI", 14, "bold")
        )
        self.title_lbl.pack(side=tk.LEFT)

        self.btn_theme = tk.Button(
            self.header_frame, text="☀️ Light Mode", relief=tk.GROOVE, padx=8, pady=2,
            font=("Segoe UI", 9), command=self.toggle_theme
        )
        self.btn_theme.pack(side=tk.RIGHT, padx=(8, 0))

        self.folder_btn = tk.Button(
            self.header_frame, text="📁 Open Plugins Folder", relief=tk.GROOVE, padx=8, pady=2,
            font=("Segoe UI", 9), command=self.open_plugins_folder
        )
        self.folder_btn.pack(side=tk.RIGHT)

        # Notebook Container
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_plugins = tk.Frame(self.notebook)
        self.notebook.add(self.tab_plugins, text="  🧩 Plugins & Extensions  ")

        # 2. Summary Bar
        self.summary_frame = tk.LabelFrame(self.tab_plugins, text=" Summary ", padx=10, pady=6, font=("Segoe UI", 9, "bold"))
        self.summary_frame.pack(fill=tk.X, padx=14, pady=4)

        self.lbl_catalog = tk.Label(self.summary_frame, text="Catalog: -", font=("Segoe UI", 9, "bold"))
        self.lbl_catalog.pack(side=tk.LEFT, padx=10)

        self.lbl_active = tk.Label(self.summary_frame, text="Active: -", font=("Segoe UI", 9, "bold"))
        self.lbl_active.pack(side=tk.LEFT, padx=10)

        self.lbl_disabled = tk.Label(self.summary_frame, text="Disabled: -", font=("Segoe UI", 9))
        self.lbl_disabled.pack(side=tk.LEFT, padx=10)

        self.lbl_outdated = tk.Label(self.summary_frame, text="Out of Date: -", font=("Segoe UI", 9, "bold"))
        self.lbl_outdated.pack(side=tk.LEFT, padx=10)

        self.lbl_missing = tk.Label(self.summary_frame, text="Missing: -", font=("Segoe UI", 9))
        self.lbl_missing.pack(side=tk.LEFT, padx=10)

        self.lbl_ignored = tk.Label(self.summary_frame, text="Ignored: 0", font=("Segoe UI", 9))
        self.lbl_ignored.pack(side=tk.LEFT, padx=10)

        self.lbl_selected = tk.Label(self.summary_frame, text="Selected: 0", font=("Segoe UI", 9, "bold"))
        self.lbl_selected.pack(side=tk.RIGHT, padx=10)

        # 3. Primary Actions Bar
        self.actions_frame = tk.Frame(self.tab_plugins, padx=14, pady=3)
        self.actions_frame.pack(fill=tk.X)

        self.btn_download_selected = tk.Button(
            self.actions_frame, text="📥 Download Selected (0)", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9, "bold"), command=self.download_selected_async
        )
        self.btn_download_selected.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_disable = tk.Button(
            self.actions_frame, text="⏸ Disable Selected", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.disable_selected
        )
        self.btn_disable.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_enable = tk.Button(
            self.actions_frame, text="▶ Enable Selected", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.enable_selected
        )
        self.btn_enable.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_update_all = tk.Button(
            self.actions_frame, text="⚡ Update Outdated", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.update_all_async
        )
        self.btn_update_all.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_download_all = tk.Button(
            self.actions_frame, text="📥 Download All", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.download_all_async
        )
        self.btn_download_all.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_ignore = tk.Button(
            self.actions_frame, text="🚫 Ignore Selected", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.ignore_selected
        )
        self.btn_ignore.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_unignore = tk.Button(
            self.actions_frame, text="♻ Unignore", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.unignore_selected
        )
        self.btn_unignore.pack(side=tk.LEFT, padx=(0, 6))


        self.btn_refresh = tk.Button(
            self.actions_frame, text="🔄 Refresh Catalog", relief=tk.GROOVE, padx=8, pady=3,
            font=("Segoe UI", 9), command=self.refresh_catalog_manual
        )
        self.btn_refresh.pack(side=tk.RIGHT)

        # 4. Selection Toolbar Bar
        self.select_toolbar = tk.Frame(self.tab_plugins, padx=14, pady=3)
        self.select_toolbar.pack(fill=tk.X)

        self.lbl_select = tk.Label(self.select_toolbar, text="Select:", font=("Segoe UI", 9, "bold"))
        self.lbl_select.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_sel_all = tk.Button(self.select_toolbar, text="☑ All", width=6, relief=tk.GROOVE, command=self.select_all)
        self.btn_sel_all.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_desel_all = tk.Button(self.select_toolbar, text="☐ None", width=7, relief=tk.GROOVE, command=self.deselect_all)
        self.btn_desel_all.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_invert = tk.Button(self.select_toolbar, text="🔀 Invert", width=8, relief=tk.GROOVE, command=self.invert_selection)
        self.btn_invert.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_sel_active = tk.Button(self.select_toolbar, text="✅ Active Only", relief=tk.GROOVE, command=self.select_active)
        self.btn_sel_active.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_sel_disabled = tk.Button(self.select_toolbar, text="⏸ Disabled Only", relief=tk.GROOVE, command=self.select_disabled)
        self.btn_sel_disabled.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_sel_missing = tk.Button(self.select_toolbar, text="❌ Missing Only", relief=tk.GROOVE, command=self.select_missing)
        self.btn_sel_missing.pack(side=tk.LEFT, padx=(0, 4))

        self.hint_lbl = tk.Label(
            self.select_toolbar, text="(Click headers to sort | Hover row for full description)", font=("Segoe UI", 8)
        )
        self.hint_lbl.pack(side=tk.RIGHT)

        # 5. Progress Bar & Status
        self.prog_frame = tk.Frame(self.tab_plugins, padx=14, pady=2)
        self.prog_frame.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(self.prog_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=2)

        self.lbl_status = tk.Label(self.prog_frame, text="Ready", font=("Segoe UI", 9, "italic"))
        self.lbl_status.pack(side=tk.LEFT)

        # 6. Table of Plugins
        self.table_frame = tk.Frame(self.tab_plugins, padx=14, pady=4)
        self.table_frame.pack(fill=tk.BOTH, expand=True)

        self.columns = ("check", "status", "id", "name", "installed_ver", "catalog_ver", "description")
        self.col_titles = {
            "check": "Sel",
            "status": "Status",
            "id": "Plugin ID",
            "name": "Name",
            "installed_ver": "Installed",
            "catalog_ver": "Latest",
            "description": "Description"
        }

        self.tree = ttk.Treeview(self.table_frame, columns=self.columns, show="headings", selectmode="extended")

        for col in self.columns:
            self.tree.heading(col, text=self.col_titles[col], command=lambda c=col: self.sort_by_column(c))

        self.tree.column("check", width=42, anchor="center")
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("id", width=140)
        self.tree.column("name", width=210)
        self.tree.column("installed_ver", width=75, anchor="center")
        self.tree.column("catalog_ver", width=75, anchor="center")
        self.tree.column("description", width=340)

        scrollbar = ttk.Scrollbar(self.table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 7. Details / Description Preview Panel at Bottom
        self.details_frame = tk.Frame(self.tab_plugins, padx=14, pady=6)
        self.details_frame.pack(fill=tk.X)

        self.lbl_details_title = tk.Label(self.details_frame, text="Plugin Details:", font=("Segoe UI", 9, "bold"))
        self.lbl_details_title.pack(anchor=tk.W)

        self.lbl_details_text = tk.Label(
            self.details_frame, text="Hover over or click any plugin row above to read full details.",
            font=("Segoe UI", 9), anchor=tk.W, justify=tk.LEFT, wraplength=980
        )
        self.lbl_details_text.pack(fill=tk.X, anchor=tk.W)

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self.tooltip.hide())

        # 8. English & Post-Update Patcher Tab
        self.patcher_tab = PatcherTab(self.notebook, theme_provider=lambda: self.theme)
        self.notebook.add(self.patcher_tab, text="  🌐 English & Post-Update Patcher  ")

        # 9. Project Profiles Tab (User & Agentic Presets)
        self.profiles_tab = ProfilesTab(
            self.notebook,
            theme_provider=lambda: self.theme,
            on_plugins_changed=self._populate_table,
            get_tab1_checked=lambda: set(self.checked_ids),
            set_tab1_checked=self.set_checked_ids,
            script_path=Path(__file__).resolve(),
        )
        self.notebook.add(self.profiles_tab, text="  📦 Project Profiles  ")

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.theme = DARK_THEME if self.is_dark else LIGHT_THEME
        self.btn_theme.config(text="☀️ Light Mode" if self.is_dark else "🌙 Dark Mode")
        self._apply_theme()

    def _apply_theme(self):
        t = self.theme
        self.root.config(bg=t["bg"])

        self.tab_plugins.config(bg=t["bg"])
        for f in (self.header_frame, self.actions_frame, self.select_toolbar, self.prog_frame, self.table_frame, self.details_frame):
            f.config(bg=t["bg"])
        if hasattr(self, "patcher_tab") and self.patcher_tab:
            self.patcher_tab.apply_theme()
        if hasattr(self, "profiles_tab") and self.profiles_tab:
            self.profiles_tab.apply_theme()

        self.summary_frame.config(bg=t["surface"], fg=t["fg"])
        self.title_lbl.config(bg=t["bg"], fg=t["fg"])
        self.lbl_select.config(bg=t["bg"], fg=t["fg"])
        self.hint_lbl.config(bg=t["bg"], fg=t["muted"])
        self.lbl_status.config(bg=t["bg"], fg=t["muted"])
        self.lbl_details_title.config(bg=t["bg"], fg=t["fg"])
        self.lbl_details_text.config(bg=t["bg"], fg=t["muted"])

        self.lbl_catalog.config(bg=t["surface"], fg=t["fg"])
        self.lbl_active.config(bg=t["surface"], fg=t["installed"])
        self.lbl_disabled.config(bg=t["surface"], fg=t["disabled"])
        self.lbl_outdated.config(bg=t["surface"], fg=t["outdated"])
        self.lbl_missing.config(bg=t["surface"], fg=t["missing"])
        self.lbl_ignored.config(bg=t["surface"], fg=t["muted"])
        self.lbl_selected.config(bg=t["surface"], fg=t["accent"])

        btns = (
            self.folder_btn, self.btn_theme, self.btn_download_selected, self.btn_disable, self.btn_enable,
            self.btn_update_all, self.btn_download_all, self.btn_refresh, self.btn_sel_all, self.btn_desel_all,
            self.btn_invert, self.btn_sel_active, self.btn_sel_disabled, self.btn_sel_missing,
            self.btn_ignore, self.btn_unignore
        )
        for b in btns:
            b.config(bg=t["btn_bg"], fg=t["btn_fg"], activebackground=t["border"], activeforeground=t["fg"], bd=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=t["card"],
            foreground=t["fg"],
            fieldbackground=t["card"],
            rowheight=28,
            font=("Segoe UI", 9),
            bordercolor=t["border"]
        )
        style.map("Treeview", background=[("selected", t["select_bg"])], foreground=[("selected", t["select_fg"])])
        style.configure(
            "Treeview.Heading",
            background=t["surface"],
            foreground=t["fg"],
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            bordercolor=t["border"]
        )
        style.map("Treeview.Heading", background=[("active", t["border"])])

    def sort_by_column(self, col: str):
        is_reverse = self.sort_state.get(col, False)
        self.sort_state[col] = not is_reverse

        for c in self.columns:
            title = self.col_titles[c]
            if c == col:
                title += " ▼" if is_reverse else " ▲"
            self.tree.heading(c, text=title)

        items = []
        for iid in self.tree.get_children():
            val = self.tree.set(iid, col)
            if col in ("installed_ver", "catalog_ver"):
                sort_key = parse_version_tuple(val)
            elif col == "check":
                sort_key = 1 if "☑" in str(val) else 0
            elif col == "status":
                if "Outdated" in str(val):
                    sort_key = 0
                elif "Active" in str(val) or "Installed" in str(val):
                    sort_key = 1
                elif "Disabled" in str(val):
                    sort_key = 2
                else:
                    sort_key = 3
            else:
                sort_key = str(val).lower()
            items.append((sort_key, iid))

        items.sort(key=lambda x: x[0], reverse=is_reverse)

        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)

    def _on_tree_motion(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id or row_id not in self.catalog:
            self.tooltip.hide()
            return

        if row_id == self.tooltip.last_row:
            return

        self.tooltip.last_row = row_id
        entry = self.catalog[row_id]
        name = entry.get("name", row_id)
        ver = entry.get("version", "")
        author = entry.get("author", "Community")
        lic = entry.get("license", "Open Source")
        desc = entry.get("description", "No description available.")

        tip_text = f"📌 {name} (v{ver})\nAuthor: {author} | License: {lic}\n{'─'*45}\n{desc}"
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        self.tooltip.show(tip_text, x, y, is_dark=self.is_dark)

    def _on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        ext_id = selected[0]
        if ext_id in self.catalog:
            entry = self.catalog[ext_id]
            name = entry.get("name", ext_id)
            desc = entry.get("description", "No description available.")
            ver = entry.get("version", "-")
            author = entry.get("author", "Community")
            self.lbl_details_title.config(text=f"Plugin Details: {name} (v{ver} by {author})")
            self.lbl_details_text.config(text=desc)

    def _scan_local_plugins(self) -> dict[str, dict]:
        """Scan local plugins directory, recording version and active/disabled state."""
        installed = {}
        status_map = {}
        if PLUGINS_DIR.is_dir():
            try:
                for entry in os.scandir(PLUGINS_DIR):
                    if entry.is_dir():
                        meta_file = os.path.join(entry.path, "extension.json")
                        init_py = os.path.join(entry.path, "__init__.py")
                        init_dis = os.path.join(entry.path, "__init__.py.disabled")

                        meta = {}
                        if os.path.isfile(meta_file):
                            try:
                                with open(meta_file, "r", encoding="utf-8") as f:
                                    meta = json.load(f)
                            except Exception:
                                pass

                        # Determine active vs disabled
                        if os.path.isfile(init_py):
                            p_status = "active"
                        elif os.path.isfile(init_dis):
                            p_status = "disabled"
                        else:
                            p_status = "active" if any(f.endswith(".py") for f in os.listdir(entry.path)) else "disabled"

                        keys = [entry.name, entry.name.replace("-", "_"), entry.name.replace("_", "-")]
                        meta_id = meta.get("id")
                        if meta_id:
                            keys.extend([meta_id, meta_id.replace("-", "_"), meta_id.replace("_", "-")])

                        for k in keys:
                            installed[k] = meta
                            status_map[k] = p_status
            except Exception:
                pass
        self.local_meta_cache = installed
        self.local_status_cache = status_map
        return installed

    def _load_local_data_instant(self):
        self._scan_local_plugins()

        if CACHE_FILE.is_file():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                norm = normalize_catalog(cached_data)
                if norm:
                    self.catalog = norm
                    return
            except Exception:
                pass

        fallback = {}
        for ext_id, meta in self.local_meta_cache.items():
            name = meta.get("name") or ext_id.replace("_", " ").title()
            fallback[ext_id] = {
                "id": ext_id,
                "name": name,
                "version": str(meta.get("version", "1.0.0")),
                "sha256": str(meta.get("sha256", "")).lower().strip(),
                "download": str(meta.get("download", "")).strip(),
                "description": meta.get("description", "Installed extension"),
                "author": meta.get("author", "Community"),
                "license": meta.get("license", "Open Source")
            }
        self.catalog = fallback

    def _background_check_updates(self):
        try:
            self.root.after(0, self.lbl_status.config, {"text": "Checking GitHub for catalog updates..."})
            raw_bytes = fetch_url_bytes(CATALOG_URL, timeout=8)
            data = json.loads(raw_bytes.decode("utf-8"))
            new_cat = normalize_catalog(data)

            if new_cat and len(new_cat) >= len(self.catalog):
                self.catalog = new_cat
                try:
                    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(CACHE_FILE, "wb") as f:
                        f.write(raw_bytes)
                except Exception:
                    pass
                self.root.after(0, self._populate_table, f"Catalog up to date ({len(new_cat)} available plugins).")
            else:
                self.root.after(0, self.lbl_status.config, {"text": "Ready."})
        except Exception:
            self.root.after(0, self.lbl_status.config, {"text": f"Ready (offline mode, {len(self.catalog)} plugins)."})

    def refresh_catalog_manual(self):
        if self.is_busy:
            return
        self.lbl_status.config(text="Refreshing catalog from GitHub...")
        threading.Thread(target=self._background_check_updates, daemon=True).start()

    def set_busy(self, busy: bool, msg: str = ""):
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_download_selected.config(state=state)
        self.btn_disable.config(state=state)
        self.btn_enable.config(state=state)
        self.btn_update_all.config(state=state)
        self.btn_download_all.config(state=state)
        self.btn_refresh.config(state=state)
        if msg:
            self.lbl_status.config(text=msg)

    def open_plugins_folder(self):
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(PLUGINS_DIR))

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1":
                row_id = self.tree.identify_row(event.y)
                if row_id:
                    self.toggle_check(row_id)
                    return "break"

    def _on_tree_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.toggle_check(row_id)

    def _on_space(self, event):
        selected_rows = self.tree.selection()
        if not selected_rows:
            return
        for row_id in selected_rows:
            self.toggle_check(row_id)
        return "break"

    def toggle_check(self, ext_id: str):
        if ext_id in self.checked_ids:
            self.checked_ids.remove(ext_id)
        else:
            self.checked_ids.add(ext_id)
        self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def _update_row_checkbox(self, ext_id: str):
        if not self.tree.exists(ext_id):
            return
        current_vals = list(self.tree.item(ext_id, "values"))
        current_vals[0] = "☑" if ext_id in self.checked_ids else "☐"
        self.tree.item(ext_id, values=current_vals)

    def _update_selected_label(self):
        count = len(self.checked_ids)
        self.lbl_selected.config(text=f"Selected: {count}")
        self.btn_download_selected.config(text=f"📥 Download Selected ({count})")

    def select_all(self):
        self.checked_ids = set(self.catalog.keys())
        for ext_id in self.catalog.keys():
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def deselect_all(self):
        self.checked_ids.clear()
        for ext_id in self.catalog.keys():
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def invert_selection(self):
        for ext_id in self.catalog.keys():
            if ext_id in self.checked_ids:
                self.checked_ids.remove(ext_id)
            else:
                self.checked_ids.add(ext_id)
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def select_active(self):
        self.checked_ids.clear()
        for ext_id in self.catalog.keys():
            if self.local_status_cache.get(ext_id) == "active":
                self.checked_ids.add(ext_id)
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def select_disabled(self):
        self.checked_ids.clear()
        for ext_id in self.catalog.keys():
            if self.local_status_cache.get(ext_id) == "disabled":
                self.checked_ids.add(ext_id)
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    def select_missing(self):
        self.checked_ids.clear()
        for ext_id in self.catalog.keys():
            if ext_id not in self.local_meta_cache:
                self.checked_ids.add(ext_id)
            self._update_row_checkbox(ext_id)
        self._update_selected_label()

    # Enable & Disable Actions
    def disable_selected(self):
        if not self.checked_ids:
            messagebox.showinfo("Disable Plugins", "No plugins selected. Check the plugins you wish to disable.")
            return

        count = 0
        for ext_id in self.checked_ids:
            for folder_name in (ext_id, ext_id.replace("_", "-"), ext_id.replace("-", "_")):
                p_dir = PLUGINS_DIR / folder_name
                init_file = p_dir / "__init__.py"
                dis_file = p_dir / "__init__.py.disabled"
                if init_file.is_file():
                    try:
                        init_file.rename(dis_file)
                        count += 1
                        break
                    except Exception:
                        pass
        self._populate_table(f"Disabled {count} plugin(s). Restart IngeTrazo for changes to take effect.")
        messagebox.showinfo("Plugins Disabled", f"Successfully disabled {count} plugin(s).\n\nRestart IngeTrazo to update menus.")

    def enable_selected(self):
        if not self.checked_ids:
            messagebox.showinfo("Enable Plugins", "No plugins selected. Check the plugins you wish to enable.")
            return

        count = 0
        for ext_id in self.checked_ids:
            for folder_name in (ext_id, ext_id.replace("_", "-"), ext_id.replace("-", "_")):
                p_dir = PLUGINS_DIR / folder_name
                dis_file = p_dir / "__init__.py.disabled"
                init_file = p_dir / "__init__.py"
                if dis_file.is_file():
                    try:
                        dis_file.rename(init_file)
                        count += 1
                        break
                    except Exception:
                        pass
        self._populate_table(f"Enabled {count} plugin(s). Restart IngeTrazo for changes to take effect.")
        messagebox.showinfo("Plugins Enabled", f"Successfully enabled {count} plugin(s).\n\nRestart IngeTrazo to update menus.")

    def _load_ignored(self) -> set[str]:
        try:
            if IGNORED_FILE.is_file():
                data = json.loads(IGNORED_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return set(str(x) for x in data)
        except Exception:
            pass
        return set()

    def _save_ignored(self):
        try:
            IGNORED_FILE.parent.mkdir(parents=True, exist_ok=True)
            IGNORED_FILE.write_text(json.dumps(sorted(self.ignored_ids), indent=2), encoding="utf-8")
        except Exception:
            pass

    def ignore_selected(self):
        if not self.checked_ids:
            messagebox.showinfo("Ignore Plugins", "No plugins selected. Check the plugins you want to ignore from future searches and updates.")
            return
        to_ignore = set(self.checked_ids)
        self.ignored_ids.update(to_ignore)
        self._save_ignored()
        disabled_count = 0
        for ext_id in to_ignore:
            for folder_name in (ext_id, ext_id.replace("_", "-"), ext_id.replace("-", "_")):
                p_dir = PLUGINS_DIR / folder_name
                init_f = p_dir / "__init__.py"
                dis_f = p_dir / "__init__.py.disabled"
                if init_f.is_file():
                    try:
                        if dis_f.is_file():
                            dis_f.unlink()
                        init_f.rename(dis_f)
                        disabled_count += 1
                        break
                    except Exception:
                        pass
        self.checked_ids.difference_update(to_ignore)
        self._populate_table(f"Ignored {len(to_ignore)} plugin(s) (disabled {disabled_count} active).")

    def unignore_selected(self):
        if not self.checked_ids:
            messagebox.showinfo("Unignore Plugins", "No plugins selected. Check the ignored plugins you want to restore.")
            return
        restored = self.checked_ids.intersection(self.ignored_ids)
        self.ignored_ids.difference_update(restored)
        self._save_ignored()
        self.checked_ids.difference_update(restored)
        self._populate_table(f"Restored {len(restored)} plugin(s) from ignore list.")

    def _populate_table(self, status_msg):
        self._scan_local_plugins()

        for item in self.tree.get_children():
            self.tree.delete(item)

        active_count = 0
        disabled_count = 0
        outdated_count = 0
        missing_count = 0
        ignored_count = 0

        for ext_id, entry in sorted(self.catalog.items()):
            local = self.local_meta_cache.get(ext_id)
            p_status = self.local_status_cache.get(ext_id)
            name = entry.get("name", ext_id)
            cat_ver = entry.get("version", "-")
            desc = entry.get("description", "")
            cat_hash = entry.get("sha256", "").lower().strip()

            chk = "☑" if ext_id in self.checked_ids else "☐"

            if ext_id in self.ignored_ids:
                ignored_count += 1
                status = "🚫 Ignored"
                inst_ver = local.get("version", "-") if local else "-"
            elif local is None:
                status = "❌ Missing"
                inst_ver = "-"
                missing_count += 1
            else:
                inst_ver = local.get("version", "?")
                loc_hash = local.get("sha256", "").lower().strip()
                if (cat_hash and loc_hash != cat_hash) or (cat_ver != "-" and inst_ver != cat_ver):
                    status = "⚠️ Outdated"
                    outdated_count += 1
                elif p_status == "disabled":
                    status = "⏸ Disabled"
                    disabled_count += 1
                else:
                    status = "✅ Active"
                    active_count += 1

            self.tree.insert("", tk.END, iid=ext_id, values=(chk, status, ext_id, name, inst_ver, cat_ver, desc))

        total = len(self.catalog)
        self.lbl_catalog.config(text=f"Catalog: {total} plugins")
        self.lbl_active.config(text=f"Active: {active_count}")
        self.lbl_disabled.config(text=f"Disabled: {disabled_count}")
        self.lbl_outdated.config(text=f"Out of Date: {outdated_count}")
        self.lbl_missing.config(text=f"Missing: {missing_count}")
        self.lbl_ignored.config(text=f"Ignored: {ignored_count}")
        self._update_selected_label()

        self.lbl_status.config(text=status_msg)
        self.progress_bar["value"] = 0

    def download_selected_async(self):
        if self.is_busy:
            return
        if not self.checked_ids:
            messagebox.showinfo("Download Selected", "No plugins selected. Check the plugins you want to download or update.")
            return

        selected_items = [(ext_id, self.catalog[ext_id]) for ext_id in self.checked_ids if ext_id in self.catalog]
        count = len(selected_items)
        if not messagebox.askyesno("Download Selected", f"Download/update the {count} selected plugin(s)?"):
            return

        self.set_busy(True, f"Downloading {count} selected plugins (fast parallel mode)...")
        threading.Thread(target=self._download_batch_parallel, args=(selected_items, "Selected Download"), daemon=True).start()

    def update_all_async(self):
        if self.is_busy:
            return
        outdated_items = []
        for ext_id, entry in self.catalog.items():
            if ext_id in self.ignored_ids:
                continue
            local = self.local_meta_cache.get(ext_id)
            cat_hash = entry.get("sha256", "").lower().strip()
            cat_ver = entry.get("version", "-")
            if local and ((cat_hash and local.get("sha256", "").lower().strip() != cat_hash) or (cat_ver != "-" and local.get("version") != cat_ver)):
                outdated_items.append((ext_id, entry))

        if not outdated_items:
            messagebox.showinfo("Update Outdated", "All installed plugins are already up to date!")
            return

        self.set_busy(True, f"Updating {len(outdated_items)} plugins (fast parallel mode)...")
        threading.Thread(target=self._download_batch_parallel, args=(outdated_items, "Update All"), daemon=True).start()

    def download_all_async(self):
        if self.is_busy:
            return
        all_items = [(eid, ent) for eid, ent in self.catalog.items() if eid not in self.ignored_ids]
        if not all_items:
            messagebox.showwarning("Download All", "Catalog is empty. Try refreshing first.")
            return

        if not messagebox.askyesno("Download All", f"Download and install all {len(all_items)} plugins from the catalog?"):
            return

        self.set_busy(True, f"Downloading all {len(all_items)} plugins (fast parallel mode)...")
        threading.Thread(target=self._download_batch_parallel, args=(all_items, "Download All"), daemon=True).start()

    def _download_single_plugin(self, ext_id: str, entry: dict) -> bool:
        """Download and verify one plugin, extracting zip packages automatically."""
        download_url = entry.get("download")
        expected_hash = entry.get("sha256", "").lower().strip()
        version = entry.get("version", "1.0.0")

        if not download_url:
            return False

        try:
            content = fetch_url_bytes(download_url, timeout=12)
            if expected_hash:
                actual_hash = hashlib.sha256(content).hexdigest().lower()
                if actual_hash != expected_hash:
                    return False

            dest_dir = PLUGINS_DIR / ext_id

            # Detect and extract ZIP packages cleanly
            if content.startswith(b"PK\x03\x04"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        zf.extractall(PLUGINS_DIR)
                except Exception:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        zf.extractall(dest_dir)
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                with open(dest_dir / "__init__.py", "wb") as f:
                    f.write(content)

            dest_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "id": ext_id,
                "version": version,
                "sha256": expected_hash,
                "download": download_url
            }
            with open(dest_dir / "extension.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            return True
        except Exception:
            return False

    def _download_batch_parallel(self, items: list, action_name: str):
        total = len(items)
        success_count = 0
        completed_count = 0
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_ext = {
                executor.submit(self._download_single_plugin, ext_id, entry): ext_id
                for ext_id, entry in items
            }

            for future in concurrent.futures.as_completed(future_to_ext):
                completed_count += 1
                ext_id = future_to_ext[future]
                try:
                    ok = future.result()
                    if ok:
                        success_count += 1
                except Exception:
                    pass

                pct = int((completed_count / total) * 100)
                self.root.after(0, self._update_progress, pct, f"[{completed_count}/{total}] Downloaded {ext_id}...")

        self.root.after(0, self._download_finished, success_count, total, action_name)

    def _update_progress(self, pct, msg):
        self.progress_bar["value"] = pct
        self.lbl_status.config(text=msg)

    def _download_finished(self, success, total, action_name):
        self.set_busy(False)
        self._populate_table(f"{action_name} complete: {success}/{total} successfully processed.")
        messagebox.showinfo("Completed", f"{action_name} finished!\n\nSuccessfully processed {success} of {total} plugins.")

    def _check_update_notice(self):
        try:
            leeme = Path(r"C:\Program Files\IngeTrazo\LEEME.txt")
            if leeme.is_file():
                self.lbl_status.config(text="💡 Tip: Spanish defaults detected in install folder. Switch to 'English Patcher' tab to apply English patches.")
        except Exception:
            pass

    def set_checked_ids(self, ids: set[str]):
        self.checked_ids = set(ids)
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            ext_id = vals[1]
            vals[0] = "☑" if ext_id in self.checked_ids else "☐"
            self.tree.item(item, values=vals)
        self._update_selected_count()
        self.notebook.select(self.tab_plugins)

if __name__ == "__main__":
    cli_exit = profiles_manager.handle_cli(sys.argv[1:])
    if cli_exit is not None:
        sys.exit(cli_exit)
    root = tk.Tk()
    app = PluginManagerApp(root)
    root.mainloop()
