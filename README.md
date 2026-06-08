```
     ___  _       _        ____       _                           _____           _
    / _ \| | __ _( )___   |  _ \ ___ | |_   _  __ _  ___  _ __  |_   _|__   ___ | |___
   | | | | |/ _` |// __| | |_) / _ \| | | | |/ _` |/ _ \| '_ \   | |/ _ \ / _ \| / __|
   | |_| | | (_| | \__ \  |  __/ (_) | | |_| | (_| | (_) | | | |  | | (_) | (_) | \__ \
    \___/|_|\__,_| |___/  |_|   \___/|_|\__, |\__, |\___/|_| |_|  |_|\___/ \___/|_|___/
                                        |___/ |___/
```

A **QGIS 3.44+** plugin for fast, intuitive polygon vertex editing — inspired by the workflow of JOSM.

Three modes, three keys: **W** to extend, **A** to move, **D** to delete.

---

## Installation

**From ZIP:**
1. Download `polygon_extender.zip` from the [latest release](https://github.com/AdelsJarlen/olas-polygon-tools/releases/latest)
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**
3. Select the downloaded file

**From QGIS Plugin Repository:**
Search for *"Ola's Polygon Tools"* in **Plugins → Manage and Install Plugins** (enable *Show experimental plugins* in Settings).

---

## Quick Start

1. Select a **polygon layer** and toggle **Edit Mode** (pencil icon)
2. Click the **Ola's Polygon Tools** button in the toolbar, or pick a mode from its dropdown menu
3. Use **W**, **A**, or **D** keys to switch modes — or select from the dropdown

---

## Modes

### ![W icon](icon_extend.png) W — Extend

> *Add new vertices to reshape or grow your polygon.*

**Edge extend** — Hover near a polygon edge (a green snap marker appears on it), then click anywhere to insert a new vertex at that position. The vertex is added to the hovered edge segment.

**Vertex extend** — Hover near an existing vertex (green marker snaps to it) and click to select it. Then click repeatedly to chain new vertices from that point, reshaping the polygon. A green preview outline follows your cursor. Right-click or press **Esc** to finish.

| Step | Action |
|------|--------|
| Hover edge | Green marker appears on nearest edge |
| Click away | New vertex inserted on that edge at click position |
| Hover vertex | Green marker snaps to vertex |
| Click vertex | Enters chaining mode — each click adds a new vertex |
| Right-click / Esc | Exits chaining mode |

---

### ![A icon](icon_move.png) A — Move

> *Relocate a vertex with a live preview of the result.*

Click near a vertex to select it (blue marker). As you move the cursor, a **blue dashed outline** shows exactly what the polygon will look like. Click again to place the vertex at its new position.

| Step | Action |
|------|--------|
| Hover | Blue marker highlights nearest vertex |
| Click | Selects the vertex |
| Move cursor | Live blue preview follows the cursor |
| Click again | Vertex moved to new position |
| Right-click / Esc | Cancels the move |

---

### ![D icon](icon_delete.png) D — Delete

> *Remove unwanted vertices with a clear visual warning.*

Hover near a vertex — a **red halo** and **"delete point"** label appear. Click to remove it. Polygons must keep at least 3 vertices.

| Step | Action |
|------|--------|
| Hover | Red halo + "delete point" label on nearest vertex |
| Click | Vertex removed |

---

## Toolbar

| Icon | State |
|------|-------|
| ![Default](icon.png) | Tool inactive — click to activate (starts in W mode) |
| ![Extend](icon_extend.png) | Extend mode active |
| ![Move](icon_move.png) | Move mode active |
| ![Delete](icon_delete.png) | Delete mode active |

- **Click the button** when active to **deactivate** the tool
- **Use the dropdown arrow** to pick a specific mode
- **Press W / A / D** on the keyboard to switch modes
- **Press Esc** to cancel the current operation or deactivate

---

## License

This project is open source. Contributions welcome!
