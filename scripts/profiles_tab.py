# SPDX-License-Identifier: GPL-3.0-or-later
"""Dedicated Project Profiles Tab for IngeTrazo Plugin Manager."""

from __future__ import annotations

import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

import profiles_manager as pm


class ProfilesTab(tk.Frame):
    def __init__(
        self,
        parent,
        theme_provider,
        on_plugins_changed=None,
        get_tab1_checked=None,
        set_tab1_checked=None,
        script_path: Path | None = None,
    ):
        super().__init__(parent)
        self.theme_provider = theme_provider
        self.on_plugins_changed = on_plugins_changed
        self.get_tab1_checked = get_tab1_checked
        self.set_tab1_checked = set_tab1_checked
        self.script_path = script_path or (Path(__file__).resolve().parent / "ingetrazo_plugin_manager.pyw")

        self.profiles: dict[str, dict] = pm.load_profiles()
        self.installed: dict[str, str] = pm.scan_installed_plugins()
        self.current_profile_name: str | None = None
        self.editing_plugins: set[str] = set()
        self.visible_plugin_ids: list[str] = []

        self._create_widgets()
        self._refresh_profile_list()
        if self.profiles:
            first_name = next(iter(self.profiles))
            self.profile_listbox.selection_set(0)
            self._load_profile_into_editor(first_name)
        self.apply_theme()

    def _create_widgets(self):
        # Main split container
        self.main_pane = tk.Frame(self, padx=12, pady=10)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # === LEFT PANE: Saved Profiles ===
        self.left_frame = tk.LabelFrame(
            self.main_pane, text=" Saved Project Profiles ", padx=8, pady=8, font=("Segoe UI", 9, "bold")
        )
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        list_wrap = tk.Frame(self.left_frame)
        list_wrap.pack(fill=tk.BOTH, expand=True)
        self.list_wrap = list_wrap

        self.profile_listbox = tk.Listbox(
            list_wrap, width=28, font=("Segoe UI", 9), exportselection=False, activestyle="none"
        )
        prof_scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.profile_listbox.yview)
        self.profile_listbox.configure(yscrollcommand=prof_scroll.set)
        self.profile_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        prof_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.profile_listbox.bind("<<ListboxSelect>>", self._on_profile_selected)

        left_btns = tk.Frame(self.left_frame, pady=6)
        left_btns.pack(fill=tk.X)
        self.left_btns = left_btns

        self.btn_new_active = tk.Button(
            left_btns, text="➕ New (From Active)", relief=tk.GROOVE, padx=6, pady=3,
            font=("Segoe UI", 8, "bold"), command=self._new_from_active
        )
        self.btn_new_active.pack(fill=tk.X, pady=(0, 4))

        self.btn_new_checked = tk.Button(
            left_btns, text="☑ New (From Checked)", relief=tk.GROOVE, padx=6, pady=3,
            font=("Segoe UI", 8), command=self._new_from_checked
        )
        self.btn_new_checked.pack(fill=tk.X, pady=(0, 4))

        self.btn_delete_prof = tk.Button(
            left_btns, text="🗑 Delete Profile", relief=tk.GROOVE, padx=6, pady=3,
            font=("Segoe UI", 8), command=self._delete_profile
        )
        self.btn_delete_prof.pack(fill=tk.X)

        # === RIGHT PANE: Profile Editor & Plugin Picker ===
        self.right_frame = tk.LabelFrame(
            self.main_pane, text=" Profile Configuration & Plugins ", padx=10, pady=8, font=("Segoe UI", 9, "bold")
        )
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Metadata form
        meta_frame = tk.Frame(self.right_frame)
        meta_frame.pack(fill=tk.X, pady=(0, 6))
        self.meta_frame = meta_frame

        self.lbl_name = tk.Label(meta_frame, text="Name:", font=("Segoe UI", 9, "bold"))
        self.lbl_name.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        self.entry_name = tk.Entry(meta_frame, font=("Segoe UI", 9))
        self.entry_name.grid(row=0, column=1, sticky="ew", pady=3)

        self.lbl_desc = tk.Label(meta_frame, text="Notes:", font=("Segoe UI", 9, "bold"))
        self.lbl_desc.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        self.entry_desc = tk.Entry(meta_frame, font=("Segoe UI", 9))
        self.entry_desc.grid(row=1, column=1, sticky="ew", pady=3)
        meta_frame.columnconfigure(1, weight=1)

        # Mode & options row
        opts_frame = tk.Frame(self.right_frame)
        opts_frame.pack(fill=tk.X, pady=(0, 6))
        self.opts_frame = opts_frame

        self.lbl_mode = tk.Label(opts_frame, text="Apply Mode:", font=("Segoe UI", 9, "bold"))
        self.lbl_mode.pack(side=tk.LEFT, padx=(0, 6))

        self.mode_var = tk.StringVar(value="exact")
        self.rad_exact = tk.Radiobutton(
            opts_frame, text="Exact Switch (disable others)", variable=self.mode_var, value="exact", font=("Segoe UI", 8)
        )
        self.rad_exact.pack(side=tk.LEFT, padx=(0, 10))

        self.rad_add = tk.Radiobutton(
            opts_frame, text="Additive (keep others)", variable=self.mode_var, value="additive", font=("Segoe UI", 8)
        )
        self.rad_add.pack(side=tk.LEFT, padx=(0, 14))

        self.keep_eng_var = tk.BooleanVar(value=True)
        self.chk_keep_eng = tk.Checkbutton(
            opts_frame, text="Keep English Defaults active", variable=self.keep_eng_var, font=("Segoe UI", 8)
        )
        self.chk_keep_eng.pack(side=tk.RIGHT)

        # Filter & plugin list helpers
        filter_frame = tk.Frame(self.right_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 4))
        self.filter_frame = filter_frame

        self.lbl_filter = tk.Label(filter_frame, text="Filter:", font=("Segoe UI", 9))
        self.lbl_filter.pack(side=tk.LEFT, padx=(0, 4))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._refresh_plugin_checklist())
        self.entry_filter = tk.Entry(filter_frame, textvariable=self.filter_var, width=22, font=("Segoe UI", 9))
        self.entry_filter.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_count = tk.Label(filter_frame, text="0 plugins in profile", font=("Segoe UI", 9, "bold"))
        self.lbl_count.pack(side=tk.LEFT)

        self.btn_load_active = tk.Button(
            filter_frame, text="Load Active", relief=tk.GROOVE, padx=6, font=("Segoe UI", 8),
            command=self._load_active_into_editor
        )
        self.btn_load_active.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_clear_all = tk.Button(
            filter_frame, text="Clear", relief=tk.GROOVE, padx=6, font=("Segoe UI", 8),
            command=self._clear_editor_plugins
        )
        self.btn_clear_all.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_sel_all = tk.Button(
            filter_frame, text="All", relief=tk.GROOVE, padx=6, font=("Segoe UI", 8),
            command=self._select_all_editor_plugins
        )
        self.btn_sel_all.pack(side=tk.RIGHT)

        # Plugin checklist
        chk_wrap = tk.Frame(self.right_frame)
        chk_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.chk_wrap = chk_wrap

        self.plugin_listbox = tk.Listbox(
            chk_wrap, font=("Consolas", 9), exportselection=False, activestyle="none"
        )
        p_scroll = ttk.Scrollbar(chk_wrap, orient=tk.VERTICAL, command=self.plugin_listbox.yview)
        self.plugin_listbox.configure(yscrollcommand=p_scroll.set)
        self.plugin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        p_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.plugin_listbox.bind("<Button-1>", self._on_plugin_list_click)
        self.plugin_listbox.bind("<space>", self._on_plugin_list_space)

        # Bottom Action Bar
        bot_frame = tk.Frame(self.right_frame)
        bot_frame.pack(fill=tk.X, pady=(2, 0))
        self.bot_frame = bot_frame

        self.btn_activate = tk.Button(
            bot_frame, text="▶ Activate Profile", relief=tk.GROOVE, padx=10, pady=5,
            font=("Segoe UI", 9, "bold"), command=self._activate_current_profile
        )
        self.btn_activate.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_save = tk.Button(
            bot_frame, text="💾 Save Changes", relief=tk.GROOVE, padx=10, pady=5,
            font=("Segoe UI", 9, "bold"), command=self._save_current_profile
        )
        self.btn_save.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_check_tab1 = tk.Button(
            bot_frame, text="☑ Select in Plugins Tab", relief=tk.GROOVE, padx=8, pady=5,
            font=("Segoe UI", 8), command=self._push_to_tab1_selection
        )
        self.btn_check_tab1.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_copy_cli = tk.Button(
            bot_frame, text="🤖 Copy Agent CLI Cmd", relief=tk.GROOVE, padx=8, pady=5,
            font=("Segoe UI", 8), command=self._copy_agent_cli
        )
        self.btn_copy_cli.pack(side=tk.RIGHT)

        # Status line
        self.lbl_status = tk.Label(self.right_frame, text="Click any plugin row to toggle inclusion in this profile.", font=("Segoe UI", 8), anchor="w")
        self.lbl_status.pack(fill=tk.X, pady=(4, 0))

    # --- Helpers ---

    def _refresh_profile_list(self):
        self.profile_listbox.delete(0, tk.END)
        for name, prof in self.profiles.items():
            tag = "Exact" if prof.get("mode", "exact") == "exact" else "Add"
            cnt = len(prof.get("plugins", []))
            self.profile_listbox.insert(tk.END, f"{name}  [{tag}, {cnt}]")

    def _on_profile_selected(self, _event=None):
        sel = self.profile_listbox.curselection()
        if not sel:
            return
        names = list(self.profiles.keys())
        idx = sel[0]
        if 0 <= idx < len(names):
            self._load_profile_into_editor(names[idx])

    def _load_profile_into_editor(self, name: str):
        self.installed = pm.scan_installed_plugins()
        prof = self.profiles.get(name)
        if not prof:
            return
        self.current_profile_name = name
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, name)
        self.entry_desc.delete(0, tk.END)
        self.entry_desc.insert(0, prof.get("description", ""))
        self.mode_var.set(prof.get("mode", "exact"))
        self.keep_eng_var.set(prof.get("always_keep_english", True))
        self.editing_plugins = set(prof.get("plugins", []))
        self._refresh_plugin_checklist()

    def _refresh_plugin_checklist(self):
        q = self.filter_var.get().strip().lower()
        yview = self.plugin_listbox.yview()
        self.plugin_listbox.delete(0, tk.END)
        self.visible_plugin_ids = []

        # Show checked plugins first, then alphabetical
        ordered = sorted(
            self.installed.keys(),
            key=lambda pid: (0 if pid in self.editing_plugins else 1, pid.lower())
        )
        for pid in ordered:
            if q and q not in pid.lower():
                continue
            self.visible_plugin_ids.append(pid)
            mark = "☑" if pid in self.editing_plugins else "☐"
            st = self.installed[pid]
            st_lbl = "active" if st == "active" else "disabled"
            self.plugin_listbox.insert(tk.END, f" {mark}  {pid:<34} ({st_lbl})")

        if yview:
            self.plugin_listbox.yview_moveto(yview[0])
        self.lbl_count.config(text=f"{len(self.editing_plugins)} plugin(s) in profile")

    def _toggle_index(self, idx: int):
        if 0 <= idx < len(self.visible_plugin_ids):
            pid = self.visible_plugin_ids[idx]
            if pid in self.editing_plugins:
                self.editing_plugins.remove(pid)
            else:
                self.editing_plugins.add(pid)
            self._refresh_plugin_checklist()
            self.plugin_listbox.selection_clear(0, tk.END)
            self.plugin_listbox.selection_set(idx)
            self.plugin_listbox.activate(idx)

    def _on_plugin_list_click(self, event):
        idx = self.plugin_listbox.nearest(event.y)
        self._toggle_index(idx)
        return "break"

    def _on_plugin_list_space(self, _event):
        sel = self.plugin_listbox.curselection()
        if sel:
            self._toggle_index(sel[0])
        return "break"

    def _select_all_editor_plugins(self):
        self.editing_plugins.update(self.visible_plugin_ids)
        self._refresh_plugin_checklist()

    def _clear_editor_plugins(self):
        self.editing_plugins.clear()
        self._refresh_plugin_checklist()

    def _load_active_into_editor(self):
        self.installed = pm.scan_installed_plugins()
        self.editing_plugins = {pid for pid, st in self.installed.items() if st == "active"}
        self._refresh_plugin_checklist()
        self.lbl_status.config(text=f"Loaded {len(self.editing_plugins)} currently active plugins into editor.")

    # --- CRUD & Activation ---

    def _create_profile_prompt(self, plugin_ids: list[str], source_label: str):
        name = simpledialog.askstring("New Project Profile", f"Profile name (from {source_label}, {len(plugin_ids)} plugins):", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.profiles and not messagebox.askyesno("Overwrite?", f"Profile '{name}' already exists. Overwrite it?", parent=self):
            return
        desc = simpledialog.askstring("Profile Notes", "Optional project description / agent notes:", parent=self) or ""
        self.profiles[name] = {
            "name": name,
            "description": desc.strip(),
            "mode": "exact",
            "always_keep_english": True,
            "plugins": sorted(set(plugin_ids)),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        pm.save_profiles(self.profiles)
        self._refresh_profile_list()
        idx = list(self.profiles.keys()).index(name)
        self.profile_listbox.selection_clear(0, tk.END)
        self.profile_listbox.selection_set(idx)
        self._load_profile_into_editor(name)
        self.lbl_status.config(text=f"Saved new profile '{name}' ({len(plugin_ids)} plugins).")

    def _new_from_active(self):
        active = pm.get_active_plugins()
        self._create_profile_prompt(active, "currently active plugins")

    def _new_from_checked(self):
        if not self.get_tab1_checked:
            return
        checked = sorted(self.get_tab1_checked())
        if not checked:
            messagebox.showinfo("No Checked Plugins", "No plugins are checked in the 'Plugins & Extensions' tab.", parent=self)
            return
        self._create_profile_prompt(checked, "checked rows in Plugins tab")

    def _save_current_profile(self) -> str | None:
        new_name = self.entry_name.get().strip()
        if not new_name:
            messagebox.showwarning("Invalid Name", "Please enter a profile name.", parent=self)
            return None

        old_name = self.current_profile_name
        if old_name and old_name != new_name and old_name in self.profiles:
            del self.profiles[old_name]

        self.profiles[new_name] = {
            "name": new_name,
            "description": self.entry_desc.get().strip(),
            "mode": self.mode_var.get(),
            "always_keep_english": self.keep_eng_var.get(),
            "plugins": sorted(self.editing_plugins),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.current_profile_name = new_name
        pm.save_profiles(self.profiles)
        self._refresh_profile_list()
        idx = list(self.profiles.keys()).index(new_name)
        self.profile_listbox.selection_clear(0, tk.END)
        self.profile_listbox.selection_set(idx)
        self.lbl_status.config(text=f"Saved profile '{new_name}' ({len(self.editing_plugins)} plugins).")
        return new_name

    def _delete_profile(self):
        name = self.current_profile_name
        if not name or name not in self.profiles:
            return
        if not messagebox.askyesno("Delete Profile", f"Delete profile '{name}'?", parent=self):
            return
        del self.profiles[name]
        pm.save_profiles(self.profiles)
        self.current_profile_name = None
        self._refresh_profile_list()
        if self.profiles:
            first_name = next(iter(self.profiles))
            self.profile_listbox.selection_set(0)
            self._load_profile_into_editor(first_name)
        else:
            self.entry_name.delete(0, tk.END)
            self.entry_desc.delete(0, tk.END)
            self._clear_editor_plugins()
        self.lbl_status.config(text=f"Deleted profile '{name}'.")

    def _activate_current_profile(self):
        name = self._save_current_profile()
        if not name:
            return
        res = pm.apply_profile(name, self.profiles)
        self.installed = pm.scan_installed_plugins()
        self._refresh_plugin_checklist()
        if self.on_plugins_changed:
            self.on_plugins_changed(f"Activated profile '{name}' ({res['active_total']} active).")
        msg = (
            f"Profile '{name}' activated ({res['mode']} mode).\n\n"
            f"• Enabled: {res['enabled']}\n"
            f"• Disabled: {res['disabled']}\n"
            f"• Total Active Now: {res['active_total']}\n\n"
            "Restart IngeTrazo for plugin changes to take effect."
        )
        if res["missing"]:
            msg += f"\n\nNot installed locally ({len(res['missing'])}): {', '.join(res['missing'][:8])}"
        self.lbl_status.config(text=f"Activated '{name}': {res['enabled']} enabled, {res['disabled']} disabled ({res['active_total']} active).")
        messagebox.showinfo("Profile Activated", msg, parent=self)

    def _push_to_tab1_selection(self):
        if self.set_tab1_checked:
            self.set_tab1_checked(set(self.editing_plugins))
            self.lbl_status.config(text=f"Checked {len(self.editing_plugins)} plugins in the Plugins & Extensions tab.")

    def _copy_agent_cli(self):
        name = self.entry_name.get().strip() or self.current_profile_name or ""
        if not name:
            return
        py_exe = Path(sys.executable).name
        if py_exe.lower() == "pythonw.exe":
            py_exe = "python"
        cmd = f'{py_exe} "{self.script_path}" --apply-profile "{name}"'
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.lbl_status.config(text=f"Copied agent command: {cmd}")

    # --- Theme ---

    def apply_theme(self):
        t = self.theme_provider()
        self.config(bg=t["bg"])
        self.main_pane.config(bg=t["bg"])

        for lf in (self.left_frame, self.right_frame):
            lf.config(bg=t["surface"], fg=t["fg"])

        for f in (self.list_wrap, self.left_btns, self.meta_frame, self.opts_frame, self.filter_frame, self.chk_wrap, self.bot_frame):
            f.config(bg=t["surface"])

        for lbl in (self.lbl_name, self.lbl_desc, self.lbl_mode, self.lbl_filter):
            lbl.config(bg=t["surface"], fg=t["fg"])

        self.lbl_count.config(bg=t["surface"], fg=t["installed"])
        self.lbl_status.config(bg=t["surface"], fg=t["muted"])

        for rb in (self.rad_exact, self.rad_add, self.chk_keep_eng):
            rb.config(bg=t["surface"], fg=t["fg"], selectcolor=t["card"], activebackground=t["surface"], activeforeground=t["fg"])

        for ent in (self.entry_name, self.entry_desc, self.entry_filter):
            ent.config(bg=t["card"], fg=t["fg"], insertbackground=t["fg"])

        for lb in (self.profile_listbox, self.plugin_listbox):
            lb.config(bg=t["card"], fg=t["fg"], selectbackground=t["select_bg"], selectforeground=t["select_fg"])

        for b in (
            self.btn_new_active, self.btn_new_checked, self.btn_delete_prof,
            self.btn_load_active, self.btn_clear_all, self.btn_sel_all,
            self.btn_activate, self.btn_save, self.btn_check_tab1, self.btn_copy_cli
        ):
            b.config(bg=t["btn_bg"], fg=t["btn_fg"], activebackground=t["border"], activeforeground=t["fg"])
