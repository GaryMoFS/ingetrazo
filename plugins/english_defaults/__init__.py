# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo English Localization & International CAD Defaults Override.

Enforces English UI localization, ensures DXF view exports default to 'view.dxf'
with international layer standards ('VIEW', 'VIEW-PROFILE', 'VIEW-SECTION'),
and sets composer sheets to default to 'Sheet 1'.
Persistent across all IngeTrazo application updates.
"""
from __future__ import annotations
import logging

log = logging.getLogger("ingetrazo.plugins.english_defaults")


def setup(app):
    # 1. Enforce English UI in core i18n
    try:
        from core.i18n import set_language
        set_language("en")
        log.info("Enforced 'en' UI language in core.i18n.")
    except Exception as e:
        log.warning(f"Could not enforce 'en' language: {e}")

    # 2. Patch default sheet name in core.composition
    try:
        import core.composition
        if hasattr(core.composition, "Composicion"):
            fields = getattr(core.composition.Composicion, "__dataclass_fields__", {})
            if "name" in fields:
                fields["name"].default = "Sheet 1"
                log.info("Patched default Composicion name to 'Sheet 1'.")
    except Exception as e:
        log.warning(f"Could not patch Composicion default sheet name: {e}")

    # 3. Patch DXF view export in views.main_window.MainWindow
    try:
        import views.main_window
        cls = views.main_window.MainWindow
        orig = getattr(cls, "_on_export_view_dxf", None)
        if orig and not getattr(orig, "_english_patched", False):
            def patched_on_export_view_dxf(self):
                """Patched export view as DXF using English layers and filename."""
                from core.i18n import tr
                path, _ = self.file_dialogs.getSaveFileName(
                    self, tr("Export current view as DXF"), "view.dxf", "DXF (*.dxf)"
                )
                if not path:
                    return
                from core.hlr import KIND_CUT, KIND_PROFILE, hlr_drawing, hlr_perspective
                from formats.dxf_out import save_dxf_layers
                vp = self.viewport
                from PySide6.QtWidgets import QApplication, QMessageBox
                from PySide6.QtCore import Qt
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    geometry = vp.hlr_geometry()
                    cam = vp.camera
                    fn = hlr_perspective if cam.perspective else hlr_drawing
                    lines = fn(geometry, cam)
                    from core.layers import line_styles
                    styles = line_styles(self.scene)
                    from views.composer import dxf_groups_by_layer
                    if len(self.scene.layers) > 1:
                        groups = dxf_groups_by_layer(lines, styles, hidden_lines=True)
                    else:
                        groups = [
                            ("VIEW", [s for k, s in lines if k != KIND_PROFILE and k != KIND_CUT]),
                            ("VIEW-PROFILE", [s for k, s in lines if k == KIND_PROFILE]),
                            ("VIEW-SECTION", [s for k, s in lines if k == KIND_CUT]),
                        ]
                    n = save_dxf_layers(path, [(layer, segs) for layer, segs in groups if segs])
                except Exception as exc:
                    QMessageBox.critical(self, tr("Export DXF failed"), str(exc))
                    return
                finally:
                    QApplication.restoreOverrideCursor()
                self.statusBar().showMessage(tr("Exported {n} lines to {name}", n=n, name=path), 5000)

            patched_on_export_view_dxf._english_patched = True
            cls._on_export_view_dxf = patched_on_export_view_dxf
            log.info("Patched MainWindow._on_export_view_dxf to English defaults (view.dxf, VIEW, VIEW-PROFILE, VIEW-SECTION).")
    except Exception as e:
        log.warning(f"Could not patch _on_export_view_dxf: {e}")

    # 4. Startup layout defaults: 1/2 screen if not maximized, and collapse sidebar tabs
    try:
        from PySide6.QtCore import QTimer
        win = getattr(app, "window", None)
        if win is not None:
            def _apply_startup_layout():
                try:
                    # Collapse Properties & all right-side dock tabs by default
                    act = getattr(win, "_act_sidebar", None)
                    if act is not None:
                        if act.isChecked():
                            act.setChecked(False)
                    elif hasattr(win, "_set_sidebar_visible"):
                        win._set_sidebar_visible(False)

                    # If not maximized last session, size to 1/2 of the screen
                    if not win.isMaximized():
                        screen = win.screen()
                        if screen is not None:
                            avail = screen.availableGeometry()
                            half_w = max(640, avail.width() // 2)
                            win.resize(half_w, avail.height())
                            win.move(avail.x(), avail.y())
                except Exception as exc:
                    log.warning(f"Could not apply startup layout: {exc}")

            QTimer.singleShot(150, win, _apply_startup_layout)
    except Exception as e:
        log.warning(f"Could not schedule startup layout: {e}")
