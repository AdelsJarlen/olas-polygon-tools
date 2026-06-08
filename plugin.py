import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolButton, QMenu

from .extend_tool import PolygonEditTool, MODE_EXTEND, MODE_MOVE, MODE_DELETE


_dir = os.path.dirname(__file__)


def _icon(name):
    path = os.path.join(_dir, name)
    return QIcon(path) if os.path.exists(path) else QIcon()


class OlasPolygonToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.tool = None
        self.toolbar_button = None
        self.menu_actions = []
        self.toolbar_action = None  # the action added to the toolbar

    # ── Setup ────────────────────────────────────────────────

    def initGui(self):
        # Ensure icons exist (generate on first load)
        self._ensure_icons()

        self.tool = PolygonEditTool(self.canvas, self.iface)
        self.tool.deactivated.connect(self._on_tool_deactivated)

        # Dropdown menu
        menu = QMenu()

        act_w = menu.addAction(_icon("icon_extend.png"), "W — Extend polygon")
        act_w.setToolTip("Click edges to pull new vertices outward")
        act_w.triggered.connect(lambda: self._activate_mode(MODE_EXTEND))

        act_a = menu.addAction(_icon("icon_move.png"), "A — Move vertex")
        act_a.setToolTip("Click a vertex, then click its new position")
        act_a.triggered.connect(lambda: self._activate_mode(MODE_MOVE))

        act_d = menu.addAction(_icon("icon_delete.png"), "D — Delete vertex")
        act_d.setToolTip("Click a vertex to remove it")
        act_d.triggered.connect(lambda: self._activate_mode(MODE_DELETE))

        self.menu_actions = [act_w, act_a, act_d]

        # Tool button with dropdown
        btn = QToolButton()
        btn.setIcon(_icon("icon.png"))
        btn.setToolTip("Ola's Polygon Tools")
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.setCheckable(True)
        btn.clicked.connect(self._on_button_clicked)
        self.toolbar_button = btn

        # Add to QGIS toolbar
        self.toolbar_action = self.iface.addToolBarWidget(btn)

        # Plugin menu entry
        self.menu_action = QAction(_icon("icon.png"), "Ola's Polygon Tools", self.iface.mainWindow())
        self.menu_action.triggered.connect(self._on_button_clicked)
        self.iface.addPluginToMenu("&Ola's Polygon Tools", self.menu_action)

    def _ensure_icons(self):
        if not os.path.exists(os.path.join(_dir, "icon.png")):
            try:
                from .generate_icons import generate
                generate()
            except Exception as e:
                print(f"[Ola's Polygon Tools] Icon generation failed: {e}")

    # ── Callbacks ────────────────────────────────────────────

    def _on_button_clicked(self):
        if self.canvas.mapTool() == self.tool:
            # Already active — deactivate
            self.canvas.unsetMapTool(self.tool)
        else:
            self._activate_mode(MODE_EXTEND)

    def _activate_mode(self, mode):
        if self.canvas.mapTool() != self.tool:
            self.canvas.setMapTool(self.tool)
        self.tool.set_mode(mode)
        icons = {MODE_EXTEND: "icon_extend.png", MODE_MOVE: "icon_move.png", MODE_DELETE: "icon_delete.png"}
        self.toolbar_button.setIcon(_icon(icons.get(mode, "icon.png")))
        self.toolbar_button.setChecked(True)

    def _on_tool_deactivated(self):
        self.toolbar_button.setIcon(_icon("icon.png"))
        self.toolbar_button.setChecked(False)

    # ── Teardown ─────────────────────────────────────────────

    def unload(self):
        self.iface.removePluginMenu("&Ola's Polygon Tools", self.menu_action)
        self.iface.removeToolBarIcon(self.toolbar_action)
        if self.canvas.mapTool() == self.tool:
            self.canvas.unsetMapTool(self.tool)
        del self.tool
