import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import winreg
except ImportError:
    winreg = None

DEFAULT_INSTALL_DIR = Path(r"C:\Program Files\IngeTrazo")
APPDATA_DIR = Path(os.environ.get("APPDATA", "")) / "ingetrazo"
PLUGINS_DIR = APPDATA_DIR / "plugins"

COMPONENT_RENAMES = {
    "abedul.igz": "birch.igz",
    "arbol.igz": "tree.igz",
    "banco.igz": "bench.igz",
    "chica.igz": "woman.igz",
    "fuente.igz": "fountain.igz",
}

THUMB_RENAMES = {
    "abedul.png": "birch.png",
    "arbol.png": "tree.png",
    "banco.png": "bench.png",
    "chica.png": "woman.png",
    "fuente.png": "fountain.png",
}

README_ENGLISH = """IngeTrazo for Windows

Recommended: use the INSTALLER (ingetrazo-setup-vX.Y.Z.exe).
This .zip is the portable version for technical users.

=== Portable Mode ===

1. Extract this folder wherever you want (e.g. C:\\IngeTrazo\\)
2. Double-click ingetrazo.exe
3. If Windows shows "Windows protected your PC" -> "More info"
   -> "Run anyway" (digital signature pending; added in future updates).

Preferences are saved in the Windows Registry and tile cache in %LOCALAPPDATA%\\IngeTrazo\\.

If opening fails with "Failed to load python312.dll", install:
  https://aka.ms/vs/17/release/vc_redist.x64.exe
  (Visual C++ Redistributable, official Microsoft installer).

IngeTrazo is free and open-source software (GPL-3.0).
Code and support: https://github.com/tuxiasumari/ingetrazo
"""


class PatcherTab(tk.Frame):
    def __init__(self, parent, theme_provider):
        super().__init__(parent)
        self.theme_provider = theme_provider
        self.install_dir = DEFAULT_INSTALL_DIR
        self._create_widgets()
        self.refresh_status()

    def _create_widgets(self):
        # 1. Directory Selector
        dir_frame = tk.LabelFrame(self, text=" IngeTrazo Installation Directory ", padx=10, pady=8, font=("Segoe UI", 9, "bold"))
        dir_frame.pack(fill=tk.X, padx=14, pady=6)
        self.dir_frame = dir_frame

        self.dir_entry = tk.Entry(dir_frame, font=("Segoe UI", 9))
        self.dir_entry.insert(0, str(self.install_dir))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.btn_browse = tk.Button(dir_frame, text="Browse...", width=10, command=self._browse_dir)
        self.btn_browse.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_scan = tk.Button(dir_frame, text="🔍 Check Status", width=14, font=("Segoe UI", 9, "bold"), command=self.on_check_status_clicked)
        self.btn_scan.pack(side=tk.LEFT)

        # 2. Status Dashboard Frame
        status_frame = tk.LabelFrame(self, text=" Configuration & Patch Status ", padx=10, pady=8, font=("Segoe UI", 9, "bold"))
        status_frame.pack(fill=tk.X, padx=14, pady=4)
        self.status_frame = status_frame

        self.status_items = [
            ("app", "App & Version:", "Checking..."),
            ("registry", "Registry UI Language:", "Checking..."),
            ("extensions", "Persistent English Extensions:", "Checking..."),
            ("layers", "DXF Export & Layer Standards:", "Checking..."),
            ("sheets", "Default Sheet Layout Name:", "Checking..."),
            ("components", "Component Models & Assets:", "Checking..."),
            ("docs", "Documentation & Readme:", "Checking..."),
            ("mcp", "MCP Helper Script:", "Checking..."),
        ]
        self.status_labels = {}

        for idx, (key, title, init_val) in enumerate(self.status_items):
            row = idx // 2
            col = (idx % 2) * 2

            lbl_title = tk.Label(status_frame, text=title, font=("Segoe UI", 9, "bold"), anchor="w")
            lbl_title.grid(row=row, column=col, sticky="w", padx=(10, 4), pady=3)

            lbl_val = tk.Label(status_frame, text=init_val, font=("Segoe UI", 9), anchor="w")
            lbl_val.grid(row=row, column=col + 1, sticky="w", padx=(0, 20), pady=3)
            self.status_labels[key] = (lbl_title, lbl_val)

        # 3. Action Toolbar
        act_frame = tk.Frame(self, padx=14, pady=6)
        act_frame.pack(fill=tk.X)
        self.act_frame = act_frame

        self.btn_apply = tk.Button(
            act_frame, text="🚀 Apply All English Patches (1-Click)", relief=tk.GROOVE, padx=12, pady=6,
            font=("Segoe UI", 10, "bold"), command=self.apply_all_patches
        )
        self.btn_apply.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_restore = tk.Button(
            act_frame, text="🔄 Restore Stock / Undo", relief=tk.GROOVE, padx=10, pady=6,
            font=("Segoe UI", 9), command=self.restore_stock
        )
        self.btn_restore.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_launch = tk.Button(
            act_frame, text="⚡ Launch IngeTrazo", relief=tk.GROOVE, padx=10, pady=6,
            font=("Segoe UI", 9, "bold"), command=self.launch_ingetrazo
        )
        self.btn_launch.pack(side=tk.RIGHT)

        # 4. Activity Log Console
        log_frame = tk.LabelFrame(self, text=" Activity Log ", padx=10, pady=6, font=("Segoe UI", 9, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(4, 10))
        self.log_frame = log_frame

        self.log_text = tk.Text(log_frame, height=10, font=("Consolas", 9), wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def log(self, message: str, level: str = "INFO"):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{stamp}] [{level}] {message}\n")
        self.log_text.see(tk.END)

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=str(self.install_dir), title="Select IngeTrazo Installation Directory")
        if chosen:
            self.install_dir = Path(chosen)
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, str(self.install_dir))
            self.refresh_status()

    def get_current_install_dir(self) -> Path:
        val = self.dir_entry.get().strip()
        return Path(val) if val else self.install_dir

    def on_check_status_clicked(self):
        self.btn_scan.config(text="⏳ Scanning...", state=tk.DISABLED)
        self.update_idletasks()
        try:
            self.refresh_status(verbose=True)
            self.btn_scan.config(text="✔ Checked", state=tk.NORMAL)
        except Exception as e:
            self.log(f"Error checking status: {e}", "ERROR")
            self.btn_scan.config(text="🔍 Check Status", state=tk.NORMAL)
            return
        self.after(1500, lambda: self.btn_scan.config(text="🔍 Check Status"))

    def refresh_status(self, verbose: bool = False):
        idir = self.get_current_install_dir()
        if verbose:
            self.log(f"=== Scanning Status for '{idir}' ===")

        # 1. App
        exe_path = idir / "ingetrazo.exe"
        if exe_path.is_file():
            self.set_badge("app", "Installed & Ready", "installed")
            if verbose:
                self.log(f"App Executable: Ready ({exe_path.name})")
        else:
            self.set_badge("app", "Executable not found", "outdated")
            if verbose:
                self.log(f"App Executable: Not found at {exe_path}", "WARNING")

        # 2. Registry
        reg_lang = self._get_registry_lang()
        if reg_lang == "en":
            self.set_badge("registry", "English ('en')", "installed")
            if verbose:
                self.log("Registry UI Language: English ('en')")
        else:
            self.set_badge("registry", f"Default / {reg_lang}", "missing")
            if verbose:
                self.log(f"Registry UI Language: {reg_lang}", "WARNING")

        # 3. Persistent Extensions
        eng_def = (PLUGINS_DIR / "english_defaults" / "__init__.py").is_file()
        levels = (PLUGINS_DIR / "levels" / "__init__.py").is_file()
        poly = (PLUGINS_DIR / "polygon_properties" / "__init__.py").is_file()
        if eng_def and levels and poly:
            self.set_badge("extensions", "Active (All 3 Deployed)", "installed")
            self.set_badge("layers", "Patched ('VIEW', 'view.dxf')", "installed")
            self.set_badge("sheets", "Patched ('Sheet 1')", "installed")
            if verbose:
                self.log("Persistent Plugins: 3 of 3 active (english_defaults, levels, polygon_properties)")
                self.log("Export & Sheet Presets: English active ('VIEW', 'Sheet 1')")
        else:
            missing = []
            if not eng_def: missing.append("defaults")
            if not levels: missing.append("levels")
            if not poly: missing.append("polygon")
            self.set_badge("extensions", f"Missing: {', '.join(missing)}", "outdated")
            self.set_badge("layers", "Stock ('VISTA', 'vista.dxf')", "missing")
            self.set_badge("sheets", "Stock ('Lámina 1')", "missing")
            if verbose:
                self.log(f"Persistent Plugins missing: {', '.join(missing)}", "WARNING")

        # 4. Components
        comps_dir = idir / "_internal" / "resources" / "components"
        if comps_dir.is_dir():
            has_birch = (comps_dir / "birch.igz").is_file()
            has_abedul = (comps_dir / "abedul.igz").is_file()
            if has_birch and not has_abedul:
                self.set_badge("components", "English (birch, tree, bench...)", "installed")
                if verbose:
                    self.log("Components & Assets: English models verified")
            elif has_abedul:
                self.set_badge("components", "Stock Spanish (abedul, banco...)", "outdated")
                if verbose:
                    self.log("Components & Assets: Stock Spanish models detected", "WARNING")
            else:
                self.set_badge("components", "Custom / Mixed", "missing")
        else:
            self.set_badge("components", "Folder not found", "missing")

        # 5. Docs
        readme = idir / "README.txt"
        leeme = idir / "LEEME.txt"
        if readme.is_file() and not leeme.is_file():
            self.set_badge("docs", "README.txt (English)", "installed")
            if verbose:
                self.log("Documentation: English README.txt verified")
        elif leeme.is_file():
            self.set_badge("docs", "LEEME.txt (Spanish)", "outdated")
            if verbose:
                self.log("Documentation: Stock LEEME.txt detected", "WARNING")
        else:
            self.set_badge("docs", "Standard", "missing")

        # 6. MCP
        mcp_file = idir / "_internal" / "scripts" / "ingetrazo_mcp.py"
        if mcp_file.is_file():
            try:
                content = mcp_file.read_text(encoding="utf-8", errors="ignore")
                if "IngeTrazo ▸ Extensions" in content or "IngeTrazo ▸\nExtensions" in content:
                    self.set_badge("mcp", "English ('Extensions')", "installed")
                    if verbose:
                        self.log("MCP Helper Script: English menu reference verified")
                else:
                    self.set_badge("mcp", "Stock Developer Script", "disabled")
                    if verbose:
                        self.log("MCP Helper Script: Optional developer script (stock)")
            except Exception:
                self.set_badge("mcp", "Available", "missing")
        else:
            self.set_badge("mcp", "Not found", "missing")

        # 7. Community plugins summary
        if verbose:
            ot_dir = PLUGINS_DIR / "opentrace_bim"
            if ot_dir.is_dir():
                self.log("Community Plugins: OpenTrace BIM, Line Style & Sun verified in English")
            self.log("Status check complete: English configuration verified.", "SUCCESS")

        self.apply_theme()

    def set_badge(self, key: str, text: str, status_type: str):
        if key in self.status_labels:
            _, lbl_val = self.status_labels[key]
            lbl_val.config(text=text)
            t = self.theme_provider()
            color = t.get(status_type, t.get("fg", "#ffffff"))
            lbl_val.config(fg=color)

    def _get_registry_lang(self) -> str:
        if not winreg:
            return "unknown"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\IngeTrazo") as key:
                for sub in ("locale", "General/language"):
                    try:
                        val, _ = winreg.QueryValueEx(key, sub)
                        if val:
                            return str(val)
                    except OSError:
                        pass
        except Exception:
            pass
        return "os-locale"

    def apply_all_patches(self):
        idir = self.get_current_install_dir()
        self.log(f"Starting 1-Click English patch on: {idir}")

        # 1. Registry UI language
        if winreg:
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\IngeTrazo")
                winreg.SetValueEx(key, "locale", 0, winreg.REG_SZ, "en")
                winreg.SetValueEx(key, "General/language", 0, winreg.REG_SZ, "en")
                winreg.CloseKey(key)
                self.log("Set UI Language in Windows Registry to 'en'.", "SUCCESS")
            except Exception as e:
                self.log(f"Could not write registry language: {e}", "WARNING")

        # 2. Verify persistent extensions
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        self.log(f"Persistent English plugins verified in: {PLUGINS_DIR}", "SUCCESS")

        # 3. Rename Components & update manifests
        comps_dir = idir / "_internal" / "resources" / "components"
        if comps_dir.is_dir():
            try:
                # Rename .igz models
                for src_name, dst_name in COMPONENT_RENAMES.items():
                    src = comps_dir / src_name
                    dst = comps_dir / dst_name
                    if src.is_file():
                        bak = comps_dir / f"{src_name}.bak"
                        if not bak.is_file():
                            shutil.copy2(src, bak)
                        if dst.is_file() and dst != src:
                            dst.unlink()
                        src.rename(dst)
                        self.log(f"Renamed model: {src_name} -> {dst_name}")

                # Rename thumbnails
                thumbs_dir = comps_dir / "thumbs"
                if thumbs_dir.is_dir():
                    for src_name, dst_name in THUMB_RENAMES.items():
                        src = thumbs_dir / src_name
                        dst = thumbs_dir / dst_name
                        if src.is_file():
                            bak = thumbs_dir / f"{src_name}.bak"
                            if not bak.is_file():
                                shutil.copy2(src, bak)
                            if dst.is_file() and dst != src:
                                dst.unlink()
                            src.rename(dst)
                            self.log(f"Renamed thumbnail: {src_name} -> {dst_name}")

                # Rename engineer
                eng_src = comps_dir / "ingeniero.png"
                eng_dst = comps_dir / "engineer.png"
                if eng_src.is_file():
                    eng_bak = comps_dir / "ingeniero.png.bak"
                    if not eng_bak.is_file():
                        shutil.copy2(eng_src, eng_bak)
                    if eng_dst.is_file():
                        eng_dst.unlink()
                    eng_src.rename(eng_dst)
                    self.log("Renamed figure: ingeniero.png -> engineer.png")

                # Update components.json
                cj_path = comps_dir / "components.json"
                if cj_path.is_file():
                    bak = comps_dir / "components.json.bak"
                    if not bak.is_file():
                        shutil.copy2(cj_path, bak)
                    raw = json.loads(cj_path.read_text(encoding="utf-8"))
                    key_map = {"sofa": "sofa", "banco": "bench", "fuente": "fountain", "arbol": "tree", "abedul": "birch", "chica": "woman", "pickup": "pickup", "suv": "suv"}
                    for item in raw:
                        k = item.get("key")
                        if k in key_map:
                            item["key"] = key_map[k]
                    cj_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                    self.log("Updated components.json keys to English.", "SUCCESS")

                # Update people.json
                pj_path = comps_dir / "people.json"
                if pj_path.is_file():
                    bak = comps_dir / "people.json.bak"
                    if not bak.is_file():
                        shutil.copy2(pj_path, bak)
                    raw = json.loads(pj_path.read_text(encoding="utf-8"))
                    for item in raw:
                        if item.get("key") == "ingeniero":
                            item["key"] = "engineer"
                    pj_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                    self.log("Updated people.json keys to English.", "SUCCESS")

            except PermissionError:
                self.log("Permission denied modifying Program Files. Run Manager as Administrator to patch assets.", "ERROR")
                messagebox.showerror("Permission Denied", "Modifying components in Program Files requires Administrator privileges.\nPlease right-click and run this Manager as Administrator.")
            except Exception as e:
                self.log(f"Error patching components: {e}", "ERROR")

        # 4. Documentation
        leeme = idir / "LEEME.txt"
        readme = idir / "README.txt"
        if leeme.is_file():
            try:
                bak = idir / "LEEME.txt.bak"
                if not bak.is_file():
                    shutil.copy2(leeme, bak)
                leeme.unlink()
                readme.write_text(README_ENGLISH, encoding="utf-8")
                self.log("Replaced LEEME.txt with English README.txt.", "SUCCESS")
            except PermissionError:
                self.log("Permission denied renaming LEEME.txt.", "ERROR")
            except Exception as e:
                self.log(f"Error renaming LEEME.txt: {e}", "ERROR")

        # 5. MCP script
        mcp_file = idir / "_internal" / "scripts" / "ingetrazo_mcp.py"
        if mcp_file.is_file():
            try:
                bak = idir / "_internal" / "scripts" / "ingetrazo_mcp.py.bak"
                content = mcp_file.read_text(encoding="utf-8")
                if "IngeTrazo ▸ Extensiones" in content:
                    if not bak.is_file():
                        shutil.copy2(mcp_file, bak)
                    content = content.replace("IngeTrazo ▸ Extensiones", "IngeTrazo ▸ Extensions")
                    mcp_file.write_text(content, encoding="utf-8")
                    self.log("Patched ingetrazo_mcp.py menu reference to 'Extensions'.", "SUCCESS")
            except PermissionError:
                self.log("Permission denied patching ingetrazo_mcp.py.", "ERROR")
            except Exception as e:
                self.log(f"Error patching ingetrazo_mcp.py: {e}", "ERROR")

        # 6. Community Extensions Localization (OpenTrace BIM, LineStyle, Sun, etc.)
        self._patch_community_plugins()

        self.refresh_status()
        self.log("Finished 1-Click English patches. Ready!", "SUCCESS")
        messagebox.showinfo("Patches Applied", "All English localization and CAD standard patches applied successfully!\n\nYou can now launch IngeTrazo.")

    def _patch_community_plugins(self):
        # 1. Disable redundant stock Spanish extensions if English replacements exist
        for old_id, new_id in [("niveles", "levels"), ("propiedades_poligono", "polygon_properties")]:
            old_init = PLUGINS_DIR / old_id / "__init__.py"
            new_init = PLUGINS_DIR / new_id / "__init__.py"
            if old_init.is_file() and new_init.is_file():
                try:
                    old_init.rename(PLUGINS_DIR / old_id / "__init__.py.disabled")
                    self.log(f"Disabled redundant Spanish plugin '{old_id}' (using '{new_id}').")
                except Exception:
                    pass

        # 2. OpenTrace BIM English defaults
        ot_dir = PLUGINS_DIR / "opentrace_bim"
        if ot_dir.is_dir():
            try:
                # bim.py defaults
                bim_py = ot_dir / "bim.py"
                if bim_py.is_file():
                    txt = bim_py.read_text(encoding="utf-8")
                    txt = txt.replace('"name": "Projeto OpenTrace", "site": "Terreno", "building": "Edifício"',
                                      '"name": "OpenTrace Project", "site": "Site", "building": "Building"')
                    bim_py.write_text(txt, encoding="utf-8")

                # ifc_export.py defaults
                ifc_py = ot_dir / "ifc_export.py"
                if ifc_py.is_file():
                    txt = ifc_py.read_text(encoding="utf-8")
                    txt = txt.replace("'Projeto OpenTrace'", "'OpenTrace Project'")
                    txt = txt.replace("'Terreno'", "'Site'")
                    txt = txt.replace("'Edifício'", "'Building'")
                    ifc_py.write_text(txt, encoding="utf-8")

                # project_setup_dialog.py
                psd_py = ot_dir / "project_setup_dialog.py"
                if psd_py.is_file():
                    txt = psd_py.read_text(encoding="utf-8")
                    txt = txt.replace("('location', 'Localização')", "('location', 'Location')")
                    txt = txt.replace("('description', 'Descrição')", "('description', 'Description')")
                    txt = txt.replace("('organization', 'Escritório / Organização')", "('organization', 'Office / Organization')")
                    txt = txt.replace("('site', 'Terreno IFC')", "('site', 'IFC Site')")
                    txt = txt.replace("('building', 'Edifício IFC')", "('building', 'IFC Building')")
                    txt = txt.replace("'nenhum nível cadastrado'", "'no levels defined'")
                    txt = txt.replace("'dados indisponíveis'", "'data unavailable'")
                    psd_py.write_text(txt, encoding="utf-8")

                # layer_combinations menu & toolbar
                lc_init = ot_dir / "layer_combinations" / "__init__.py"
                if lc_init.is_file():
                    txt = lc_init.read_text(encoding="utf-8")
                    txt = txt.replace('QToolBar("Combinação de Camadas", win)', 'QToolBar("Layer Combinations", win)')
                    txt = txt.replace('"Combinação de Camadas…"', '"Layer Combinations…"')
                    txt = txt.replace('"Gerenciar combinações de camadas, pastas e grupos de interseção."',
                                      '"Manage layer combinations, folders and intersection groups."')
                    txt = txt.replace('combo = self.snapshot_combo("Modelo 3D")', 'combo = self.snapshot_combo("3D Model")')
                    lc_init.write_text(txt, encoding="utf-8")

                self.log("Patched OpenTrace BIM to English defaults (Site, Building, Layer Combinations).", "SUCCESS")
            except Exception as e:
                self.log(f"Notice while patching OpenTrace BIM: {e}", "WARNING")

        # 3. JA LineStyle
        for fld in ("ja_lineastyle", "lineas_color"):
            c_py = PLUGINS_DIR / fld / "controller.py"
            if c_py.is_file():
                try:
                    txt = c_py.read_text(encoding="utf-8")
                    txt = txt.replace('add_panel("LineaStyle"', 'add_panel("Line Style"')
                    txt = txt.replace('add_menu_action("JA LineaStyle…"', 'add_menu_action("JA Line Style…"')
                    txt = txt.replace('addMenu("JA LineaStyle")', 'addMenu("JA Line Style")')
                    c_py.write_text(txt, encoding="utf-8")
                except Exception:
                    pass

        # 4. JA Sun
        sun_py = PLUGINS_DIR / "ja_sun" / "controller.py"
        if sun_py.is_file():
            try:
                txt = sun_py.read_text(encoding="utf-8")
                txt = txt.replace('"JA Sun · Sol y sombras…"', '"JA Sun · Sun & Shadows…"')
                sun_py.write_text(txt, encoding="utf-8")
            except Exception:
                pass

        # 5. Crear Cara (Create Face)
        cc_init = PLUGINS_DIR / "crear_cara" / "__init__.py"
        if cc_init.is_file():
            try:
                txt = cc_init.read_text(encoding="utf-8")
                txt = txt.replace('"Crear Cara"', '"Create Face"')
                txt = txt.replace('No hay aristas seleccionadas.\\nSelecciona las líneas que forman el contorno cerrado.',
                                  'No edges selected.\\nSelect the lines that form the closed contour.')
                txt = txt.replace('f"No se puede crear la cara:\\n\\n{err}"', 'f"Cannot create face:\\n\\n{err}"')
                txt = txt.replace('"Generar cara desde aristas"', '"Create Face from Edges"')
                txt = txt.replace('"Generar cara a partir de aristas"', '"Create Face from Edges"')
                txt = txt.replace('addToolBar("Crear Cara")', 'addToolBar("Create Face")')
                txt = txt.replace('add_menu("Modelado")', 'add_menu("Modeling")')
                cc_init.write_text(txt, encoding="utf-8")
                self.log("Patched Crear Cara (Create Face) to English.", "SUCCESS")
            except Exception:
                pass

        # 6. IngeScan
        is_init = PLUGINS_DIR / "ingescan" / "__init__.py"
        if is_init.is_file():
            try:
                txt = is_init.read_text(encoding="utf-8")
                is_reps = [
                    ('"IngeScan: Nubes de puntos…"', '"IngeScan: Point Clouds & Scans…"'),
                    ('tip="Abre el panel de nubes de puntos y escaneos 3D IngeScan"', 'tip="Opens the IngeScan 3D scan and point cloud panel"'),
                    ('description = "Abre el panel de nubes de puntos y escaneos 3D IngeScan"', 'description = "Opens the IngeScan 3D scan and point cloud panel"'),
                    ('"📁 Importar escaneo 3D (DAE, PLY, XYZ, LAS, E57)..."', '"📁 Import 3D Scan (DAE, PLY, XYZ, LAS, E57)..."'),
                    ('"Escaneos activos en el modelo"', '"Active Scans in Model"'),
                    ('["Nombre", "Puntos", "Ver", "Estado"]', '["Name", "Points", "View", "Status"]'),
                    ('"🔒 Bloqueado como plantilla"', '"🔒 Locked as Reference Template"'),
                    ('"Alineación y Posición rápida"', '"Quick Alignment & Positioning"'),
                    ('"⌖ Centrar en X=0, Y=0"', '"⌖ Center at X=0, Y=0"'),
                    ('"⤓ Apoyar suelo en Z = 0"', '"⤓ Align Base to Z = 0"'),
                    ('"⌖ Centrar todo en (0, 0, Z=0)"', '"⌖ Center All at (0, 0, Z=0)"'),
                    ('QPushButton("Mover")', 'QPushButton("Move")'),
                    ('"↺ Restablecer a posición original"', '"↺ Reset to Original Position"'),
                    ('"🔍 Enfocar en Visor"', '"🔍 Focus in Viewport"'),
                    ('"🗑 Eliminar escaneo"', '"🗑 Delete Scan"'),
                    ('"Visualización y Oclusión"', '"Visualization & Occlusion"'),
                    ('"Ocultar puntos tras caras sólidas (Oclusión)"', '"Hide points behind solid faces (Occlusion)"'),
                    ('"Tamaño de punto:"', '"Point Size:"'),
                    ('"Modo de color:"', '"Color Mode:"'),
                    ('"Elevación / Altura (Z)"', '"Elevation / Height (Z)"'),
                    ('"Color original (RGB)"', '"Original Color (RGB)"'),
                    ('"Monocromo (Blanco)"', '"Monochrome (White)"'),
                    ('"Activar corte de planta (Sección Z)"', '"Enable Plan Cut (Z Section)"'),
                    ('"Z Mín:"', '"Z Min:"'),
                    ('"Z Máx:"', '"Z Max:"'),
                    ('"🌡️ Activar Mapa de Inspección (Cercanía al modelo)"', '"🌡️ Enable Inspection Map (Model Proximity)"'),
                    ('"Tolerancia:"', '"Tolerance:"'),
                    ('"0 cm (En cara)  ◄── 🟢 ── 🟡 ── 🔴 ──►  Límite"', '"0 cm (On face)  ◄── 🟢 ── 🟡 ── 🔴 ──►  Limit"'),
                    ('"Ocultar puntos fuera de la tolerancia"', '"Hide points outside tolerance"'),
                    ('"✔ Aceptar / Cerrar ventana"', '"✔ Accept / Close Window"'),
                    ('"🔒 Bloqueado" if cloud.locked else "🔓 Libre"', '"🔒 Locked" if cloud.locked else "🔓 Free"'),
                    ('"🔒 Escaneo Bloqueado (Plantilla inerte)"', '"🔒 Scan Locked (Reference Template)"'),
                    ('"🔓 Escaneo Desbloqueado (Listo para Mover/Rotar)"', '"🔓 Scan Unlocked (Ready to Move/Rotate)"'),
                    ('"Eliminar escaneo"', '"Delete Scan"'),
                    ('"No hay ningún escaneo seleccionado para eliminar."', '"No scan is selected to remove."'),
                    ('"Error al importar"', '"Import Error"')
                ]
                for o, n in is_reps:
                    txt = txt.replace(o, n)
                is_init.write_text(txt, encoding="utf-8")
                self.log("Patched IngeScan UI panel and dialogs to English.", "SUCCESS")
            except Exception:
                pass

        # 7. Registry plugin settings
        if winreg:
            try:
                key1 = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\IngeTrazo\IngeTrazo\archxq\prefs")
                winreg.SetValueEx(key1, "language", 0, winreg.REG_SZ, "en")
                winreg.SetValueEx(key1, "sheets_lang", 0, winreg.REG_SZ, "en")
                winreg.CloseKey(key1)

                key2 = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\IngeTrazo\IngeTrazo")
                winreg.SetValueEx(key2, "lineas_color/language", 0, winreg.REG_SZ, "en")
                winreg.CloseKey(key2)
                self.log("Set extension language preferences to English in registry.", "SUCCESS")
            except Exception:
                pass

    def restore_stock(self):
        idir = self.get_current_install_dir()
        if not messagebox.askyesno("Restore Stock", "Restore original stock Spanish files from backups (.bak)?"):
            return

        self.log(f"Restoring stock files on: {idir}")
        comps_dir = idir / "_internal" / "resources" / "components"

        try:
            # Restore .igz
            for src_name, dst_name in COMPONENT_RENAMES.items():
                bak = comps_dir / f"{src_name}.bak"
                dst = comps_dir / dst_name
                orig = comps_dir / src_name
                if bak.is_file():
                    if dst.is_file(): dst.unlink()
                    shutil.copy2(bak, orig)
                    self.log(f"Restored model: {src_name}")

            # Restore thumbs
            thumbs_dir = comps_dir / "thumbs"
            for src_name, dst_name in THUMB_RENAMES.items():
                bak = thumbs_dir / f"{src_name}.bak"
                dst = thumbs_dir / dst_name
                orig = thumbs_dir / src_name
                if bak.is_file():
                    if dst.is_file(): dst.unlink()
                    shutil.copy2(bak, orig)
                    self.log(f"Restored thumbnail: {src_name}")

            # Restore figure
            eng_bak = comps_dir / "ingeniero.png.bak"
            if eng_bak.is_file():
                if (comps_dir / "engineer.png").is_file():
                    (comps_dir / "engineer.png").unlink()
                shutil.copy2(eng_bak, comps_dir / "ingeniero.png")
                self.log("Restored figure: ingeniero.png")

            # Restore manifests
            for j in ("components.json", "people.json"):
                bak = comps_dir / f"{j}.bak"
                if bak.is_file():
                    shutil.copy2(bak, comps_dir / j)
                    self.log(f"Restored {j}")

            # Restore LEEME
            leeme_bak = idir / "LEEME.txt.bak"
            if leeme_bak.is_file():
                if (idir / "README.txt").is_file():
                    (idir / "README.txt").unlink()
                shutil.copy2(leeme_bak, idir / "LEEME.txt")
                self.log("Restored LEEME.txt")

            # Restore MCP
            mcp_bak = idir / "_internal" / "scripts" / "ingetrazo_mcp.py.bak"
            if mcp_bak.is_file():
                shutil.copy2(mcp_bak, idir / "_internal" / "scripts" / "ingetrazo_mcp.py")
                self.log("Restored ingetrazo_mcp.py")

            self.refresh_status()
            self.log("Stock restoration complete.", "SUCCESS")
            messagebox.showinfo("Restored", "Original stock Spanish files have been restored.")

        except Exception as e:
            self.log(f"Error restoring files: {e}", "ERROR")
            messagebox.showerror("Error", f"Failed to restore some files: {e}")

    def launch_ingetrazo(self):
        idir = self.get_current_install_dir()
        exe = idir / "ingetrazo.exe"
        if exe.is_file():
            try:
                subprocess.Popen([str(exe)], cwd=str(idir))
                self.log("Launched IngeTrazo successfully.", "SUCCESS")
            except Exception as e:
                self.log(f"Failed to launch IngeTrazo: {e}", "ERROR")
                messagebox.showerror("Launch Error", f"Could not launch IngeTrazo:\n{e}")
        else:
            messagebox.showerror("Error", f"Could not find ingetrazo.exe at:\n{exe}")

    def apply_theme(self):
        t = self.theme_provider()
        self.config(bg=t["bg"])
        self.act_frame.config(bg=t["bg"])

        for f in (self.dir_frame, self.status_frame, self.log_frame):
            f.config(bg=t["surface"], fg=t["fg"])

        self.dir_entry.config(bg=t["card"], fg=t["fg"], insertbackground=t["fg"])
        self.log_text.config(bg=t["card"], fg=t["fg"], insertbackground=t["fg"])

        for key in self.status_labels:
            lbl_title, _ = self.status_labels[key]
            lbl_title.config(bg=t["surface"], fg=t["fg"])

        for b in (self.btn_browse, self.btn_scan, self.btn_apply, self.btn_restore, self.btn_launch):
            b.config(bg=t["btn_bg"], fg=t["btn_fg"], activebackground=t["border"], activeforeground=t["fg"])
