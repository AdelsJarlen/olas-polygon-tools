import math

from qgis.PyQt.QtCore import Qt, QPointF
from qgis.PyQt.QtGui import QColor, QCursor, QFont, QPen, QBrush
from qgis.PyQt.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem
from qgis.core import (
    Qgis,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand


# ── Mode constants ───────────────────────────────────────────
MODE_NONE = "none"
MODE_EXTEND = "extend"   # W key
MODE_DELETE = "delete"    # D key
MODE_MOVE = "move"        # A key


class PolygonEditTool(QgsMapTool):
    """
    Multi-mode polygon vertex editing tool.

    Modes (selected via dropdown or hotkeys W / D / A):
      W — Extend: hover an edge to preview a snap-point, click to pull
          a new vertex outward to the cursor position.
          OR: click a vertex to select it, then click to place new vertices
          that reshape the polygon from that point.
      D — Delete: hover a vertex (red halo + "delete point" label),
          click to remove it.
      A — Move: click a vertex to select it, click again to relocate.
          Live blue preview of the resulting polygon shape while moving.
    """

    # Snap tolerances in screen pixels — per mode
    HOVER_TOLERANCE_PX = 20          # default / delete mode
    EXTEND_TOLERANCE_PX = 50         # W mode — much larger for edge/vertex detection
    MOVE_TOLERANCE_PX = 40           # A mode — larger for vertex selection

    def __init__(self, canvas, iface):
        super().__init__(canvas)
        self.iface = iface

        # Mode
        self.active_mode = MODE_NONE

        # ── Extend (W) state ─────────────────────────────────
        # Tracks which edge segment the cursor is near
        self.hover_fid = None
        self.hover_ring = 0
        self.hover_seg_start = -1   # index of first vertex of hovered segment
        self._hover_vertex_idx = -1 # vertex index when hovering a vertex in W mode
        # Vertex-extend sub-mode: user clicked a vertex, placing new nodes
        self.extend_vertex_mode = False
        self.extend_layer = None
        self.extend_fid = None
        self.extend_ring = 0
        self.extend_idx = -1        # the selected vertex index
        self.extend_preview = None  # QgsRubberBand for preview

        # ── Move (A) state ───────────────────────────────────
        self.move_layer = None
        self.move_fid = None
        self.move_ring = 0
        self.move_idx = -1
        self.move_preview = None    # QgsRubberBand — live polygon preview

        # ── Visual feedback ──────────────────────────────────
        self.hover_marker = None      # QGraphicsEllipseItem — edge snap preview (W) / selectable halo (A)
        self.hover_halo = None        # QGraphicsEllipseItem — red halo (D)
        self.hover_label = None       # QGraphicsTextItem — "delete point" tooltip (D)
        self.move_marker = None       # QgsRubberBand — selected vertex (A)

    # ═══════════════════════════════════════════════════════════
    #  Public API — mode switching (called by plugin.py)
    # ═══════════════════════════════════════════════════════════

    def set_mode(self, mode):
        self._cleanup_mode()
        self.active_mode = mode
        msgs = {
            MODE_EXTEND: "EXTEND mode (W): hover an edge and click outward, or click a vertex to reshape",
            MODE_DELETE: "DELETE mode (D): hover a vertex, click to remove it",
            MODE_MOVE: "MOVE mode (A): click a vertex, then click its new position",
        }
        self.iface.messageBar().pushMessage(
            "Ola's Polygon Tools", msgs.get(mode, ""), level=Qgis.Info, duration=4,
        )

    # ═══════════════════════════════════════════════════════════
    #  Activation / deactivation
    # ═══════════════════════════════════════════════════════════

    def activate(self):
        super().activate()
        self.canvas().setCursor(QCursor(Qt.CrossCursor))

    def deactivate(self):
        self._full_reset()
        super().deactivate()

    # ═══════════════════════════════════════════════════════════
    #  Key shortcuts (W / D / A still work as toggles)
    # ═══════════════════════════════════════════════════════════

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        mode_map = {Qt.Key_W: MODE_EXTEND, Qt.Key_D: MODE_DELETE, Qt.Key_A: MODE_MOVE}
        if key in mode_map:
            new_mode = mode_map[key]
            if self.active_mode == new_mode:
                # Toggle off
                if new_mode == MODE_EXTEND:
                    pass  # each click is independent in extend
                self.set_mode(MODE_NONE)
            else:
                self.set_mode(new_mode)
        elif key == Qt.Key_Escape:
            # Escape cancels sub-mode first, then full reset
            if self.extend_vertex_mode:
                self._reset_extend_vertex()
                return
            if self.move_idx >= 0:
                self._reset_move()
                return
            self._full_reset()

    def keyReleaseEvent(self, event):
        pass  # modes are toggle, not hold

    # ═══════════════════════════════════════════════════════════
    #  Mouse events
    # ═══════════════════════════════════════════════════════════

    def canvasPressEvent(self, event):
        if event.button() == Qt.RightButton:
            # Right-click cancels sub-mode first
            if self.extend_vertex_mode:
                self._reset_extend_vertex()
                return
            if self.move_idx >= 0:
                self._reset_move()
                return
            self._full_reset()
            return

        if event.button() != Qt.LeftButton:
            return

        map_point = self.toMapCoordinates(event.pos())

        if self.active_mode == MODE_EXTEND:
            self._on_click_extend(map_point)
        elif self.active_mode == MODE_DELETE:
            self._on_click_delete(map_point)
        elif self.active_mode == MODE_MOVE:
            self._on_click_move(map_point)

    def canvasMoveEvent(self, event):
        map_point = self.toMapCoordinates(event.pos())

        if self.active_mode == MODE_EXTEND:
            self._on_hover_extend(map_point)
        elif self.active_mode == MODE_DELETE:
            self._on_hover_delete(map_point, event.pos())
        elif self.active_mode == MODE_MOVE:
            self._on_hover_move(map_point)

    # ═══════════════════════════════════════════════════════════
    #  EXTEND (W) — hover edge + click outward, OR click vertex
    # ═══════════════════════════════════════════════════════════

    def _on_hover_extend(self, map_point):
        # If in vertex-extend sub-mode, show preview
        if self.extend_vertex_mode:
            self._update_extend_vertex_preview(map_point)
            return

        layer = self._editable_polygon_layer(quiet=True)
        if not layer:
            self._clear_hover_marker()
            return

        tol_px = self.EXTEND_TOLERANCE_PX

        # Check for nearby vertex first (higher priority than edge)
        fid_v, ring_v, idx_v, dist_v = self._find_nearest_vertex(layer, map_point, tol_px)
        if fid_v is not None:
            geom = layer.getFeature(fid_v).geometry()
            ring_pts = self._get_ring_points(geom, ring_v)
            self._show_hover_marker(ring_pts[idx_v], QColor(46, 125, 50, 200), radius=9)
            # Store vertex hover info so click knows it's a vertex
            self.hover_fid = fid_v
            self.hover_ring = ring_v
            self.hover_seg_start = -1  # signals "vertex, not edge"
            self._hover_vertex_idx = idx_v
            return

        # Check for nearby edge
        result = self._find_nearest_segment(layer, map_point, tol_px)
        if result is None:
            # Keep the last hovered edge selected so user can click
            # away from edge to place vertex outward — only hide marker
            self._clear_hover_marker()
            self._hover_vertex_idx = -1
            return

        fid, ring_idx, seg_start, snap_pt = result
        self.hover_fid = fid
        self.hover_ring = ring_idx
        self.hover_seg_start = seg_start
        self._hover_vertex_idx = -1
        self._show_hover_marker(snap_pt, QColor(46, 125, 50, 200), radius=7)

    def _on_click_extend(self, map_point):
        # If in vertex-extend sub-mode, place new vertex
        if self.extend_vertex_mode:
            self._place_extend_vertex(map_point)
            return

        layer = self._editable_polygon_layer()
        if not layer:
            return

        # Check if we clicked a vertex (not an edge) — enter vertex-extend sub-mode
        if (self.hover_fid is not None
                and self.hover_seg_start == -1
                and self._hover_vertex_idx >= 0):
            self._enter_extend_vertex_mode(
                layer, self.hover_fid, self.hover_ring, self._hover_vertex_idx
            )
            return

        # Use the segment we were hovering, or find nearest now
        if self.hover_fid is not None and self.hover_seg_start >= 0:
            fid = self.hover_fid
            ring_idx = self.hover_ring
            seg_start = self.hover_seg_start
        else:
            result = self._find_nearest_segment(layer, map_point, self.EXTEND_TOLERANCE_PX)
            if result is None:
                self.iface.messageBar().pushMessage(
                    "Ola's Polygon Tools", "No polygon edge or vertex found nearby.",
                    level=Qgis.Warning, duration=3,
                )
                return
            fid, ring_idx, seg_start, _ = result

        geom = layer.getFeature(fid).geometry()
        ring = self._get_ring_points(geom, ring_idx)
        n = len(ring) - 1  # unique vertices

        # Insert new vertex at cursor position after seg_start
        insert_pos = seg_start + 1
        new_ring = list(ring[:n])
        new_ring.insert(insert_pos, map_point)
        new_ring.append(new_ring[0])  # close ring

        layer.changeGeometry(fid, self._rebuild_geometry(geom, ring_idx, new_ring))
        layer.triggerRepaint()
        self._clear_hover_marker()

        self.iface.messageBar().pushMessage(
            "Ola's Polygon Tools", "Vertex inserted.",
            level=Qgis.Success, duration=2,
        )

    # ── Vertex-extend sub-mode ───────────────────────────────

    def _enter_extend_vertex_mode(self, layer, fid, ring, idx):
        """User clicked a vertex — enter sub-mode to place new nodes from it."""
        self.extend_vertex_mode = True
        self.extend_layer = layer
        self.extend_fid = fid
        self.extend_ring = ring
        self.extend_idx = idx
        self._clear_hover_marker()

        # Show selected vertex marker
        geom = layer.getFeature(fid).geometry()
        ring_pts = self._get_ring_points(geom, ring)
        self._show_hover_marker(ring_pts[idx], QColor(0, 200, 80, 220), radius=10)

        self.iface.messageBar().pushMessage(
            "Ola's Polygon Tools",
            f"Vertex {idx} selected — click to place new vertex (right-click/Esc to finish).",
            level=Qgis.Info, duration=5,
        )

    def _update_extend_vertex_preview(self, map_point):
        """Show a preview line from selected vertex to cursor."""
        if not self.extend_layer or self.extend_fid is None:
            return

        geom = self.extend_layer.getFeature(self.extend_fid).geometry()
        ring_pts = self._get_ring_points(geom, self.extend_ring)
        n = len(ring_pts) - 1
        idx = self.extend_idx

        # Build preview: polygon with new vertex inserted after selected vertex
        new_ring = list(ring_pts[:n])
        insert_pos = idx + 1
        new_ring.insert(insert_pos, map_point)
        new_ring.append(new_ring[0])  # close

        self._show_extend_preview(new_ring)

    def _place_extend_vertex(self, map_point):
        """Insert a new vertex after the selected vertex, then advance selection."""
        layer = self.extend_layer
        fid = self.extend_fid
        geom = layer.getFeature(fid).geometry()
        ring_pts = self._get_ring_points(geom, self.extend_ring)
        n = len(ring_pts) - 1

        idx = self.extend_idx
        insert_pos = idx + 1
        new_ring = list(ring_pts[:n])
        new_ring.insert(insert_pos, map_point)
        new_ring.append(new_ring[0])  # close

        layer.changeGeometry(fid, self._rebuild_geometry(geom, self.extend_ring, new_ring))
        layer.triggerRepaint()

        # Advance the selected index to the newly inserted vertex
        # so subsequent clicks chain from the new vertex
        self.extend_idx = insert_pos

        self.iface.messageBar().pushMessage(
            "Ola's Polygon Tools", "Vertex placed — click again or right-click/Esc to finish.",
            level=Qgis.Success, duration=2,
        )

    def _show_extend_preview(self, ring_points):
        """Show/update the green polygon preview for vertex-extend mode."""
        self._clear_extend_preview()
        rb = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)
        rb.setColor(QColor(46, 200, 80, 120))
        rb.setFillColor(QColor(46, 200, 80, 30))
        rb.setWidth(2)
        for pt in ring_points:
            rb.addPoint(pt)
        self.extend_preview = rb

    def _clear_extend_preview(self):
        if self.extend_preview:
            self.canvas().scene().removeItem(self.extend_preview)
            self.extend_preview = None

    def _reset_extend_vertex(self):
        """Exit vertex-extend sub-mode."""
        self.extend_vertex_mode = False
        self.extend_layer = None
        self.extend_fid = None
        self.extend_ring = 0
        self.extend_idx = -1
        self._clear_extend_preview()
        self._clear_hover_marker()
        self._hover_vertex_idx = -1

    # ═══════════════════════════════════════════════════════════
    #  DELETE (D) — hover vertex with red halo, click to delete
    # ═══════════════════════════════════════════════════════════

    def _on_hover_delete(self, map_point, pixel_pos):
        layer = self._editable_polygon_layer(quiet=True)
        if not layer:
            self._clear_hover_delete()
            return

        fid, ring, idx, dist = self._find_nearest_vertex(layer, map_point)
        if fid is not None:
            geom = layer.getFeature(fid).geometry()
            ring_pts = self._get_ring_points(geom, ring)
            self._show_hover_delete(ring_pts[idx], pixel_pos)
        else:
            self._clear_hover_delete()

    def _on_click_delete(self, map_point):
        layer = self._editable_polygon_layer()
        if not layer:
            return

        fid, ring, idx, dist = self._find_nearest_vertex(layer, map_point)
        if fid is None:
            return

        geom = layer.getFeature(fid).geometry()
        ring_pts = self._get_ring_points(geom, ring)
        n = len(ring_pts) - 1

        if n <= 3:
            self.iface.messageBar().pushMessage(
                "Ola's Polygon Tools",
                "Cannot delete — polygon must keep at least 3 vertices.",
                level=Qgis.Warning, duration=3,
            )
            return

        new_ring = [ring_pts[i] for i in range(n) if i != idx]
        new_ring.append(new_ring[0])

        layer.changeGeometry(fid, self._rebuild_geometry(geom, ring, new_ring))
        layer.triggerRepaint()
        self._clear_hover_delete()

        self.iface.messageBar().pushMessage(
            "Ola's Polygon Tools", f"Deleted vertex {idx}.",
            level=Qgis.Success, duration=2,
        )

    # ═══════════════════════════════════════════════════════════
    #  MOVE (A) — click vertex, click new position with live preview
    # ═══════════════════════════════════════════════════════════

    def _on_hover_move(self, map_point):
        # If vertex selected, update live preview
        if self.move_idx >= 0:
            self._update_move_preview(map_point)
            return

        layer = self._editable_polygon_layer(quiet=True)
        if not layer:
            self._clear_hover_marker()
            return

        fid, ring, idx, dist = self._find_nearest_vertex(layer, map_point, self.MOVE_TOLERANCE_PX)
        if fid is not None:
            geom = layer.getFeature(fid).geometry()
            ring_pts = self._get_ring_points(geom, ring)
            self._show_hover_marker(ring_pts[idx], QColor(21, 101, 192, 200), radius=8)
        else:
            self._clear_hover_marker()

    def _on_click_move(self, map_point):
        # First click: select vertex
        if self.move_idx < 0:
            layer = self._editable_polygon_layer()
            if not layer:
                return
            fid, ring, idx, dist = self._find_nearest_vertex(layer, map_point, self.MOVE_TOLERANCE_PX)
            if fid is None:
                return

            self.move_layer = layer
            self.move_fid = fid
            self.move_ring = ring
            self.move_idx = idx
            self._clear_hover_marker()

            geom = layer.getFeature(fid).geometry()
            ring_pts = self._get_ring_points(geom, ring)
            self._show_move_selected(ring_pts[idx])

            self.iface.messageBar().pushMessage(
                "Ola's Polygon Tools",
                f"Vertex {idx} selected — click new location.",
                level=Qgis.Info, duration=3,
            )
        # Second click: relocate vertex
        else:
            layer = self.move_layer
            fid = self.move_fid
            geom = layer.getFeature(fid).geometry()
            ring_pts = self._get_ring_points(geom, self.move_ring)
            n = len(ring_pts) - 1

            idx = self.move_idx
            if idx >= n:
                idx = idx % n

            new_ring = list(ring_pts[:n])
            new_ring[idx] = map_point
            new_ring.append(new_ring[0])

            layer.changeGeometry(fid, self._rebuild_geometry(geom, self.move_ring, new_ring))
            layer.triggerRepaint()

            self.iface.messageBar().pushMessage(
                "Ola's Polygon Tools", f"Moved vertex {self.move_idx}.",
                level=Qgis.Success, duration=2,
            )
            self._reset_move()

    def _update_move_preview(self, map_point):
        """Live-update a blue polygon preview with the vertex at cursor position."""
        if not self.move_layer or self.move_fid is None:
            return

        geom = self.move_layer.getFeature(self.move_fid).geometry()
        ring_pts = self._get_ring_points(geom, self.move_ring)
        n = len(ring_pts) - 1

        idx = self.move_idx
        if idx >= n:
            idx = idx % n

        # Build the preview ring with the vertex moved to cursor
        new_ring = list(ring_pts[:n])
        new_ring[idx] = map_point
        new_ring.append(new_ring[0])  # close

        self._show_move_preview(new_ring)

    def _show_move_preview(self, ring_points):
        """Show/update blue polygon outline preview for move mode."""
        self._clear_move_preview()
        rb = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)
        rb.setColor(QColor(21, 101, 192, 180))
        rb.setFillColor(QColor(21, 101, 192, 25))
        rb.setWidth(2)
        rb.setLineStyle(Qt.DashLine)
        for pt in ring_points:
            rb.addPoint(pt)
        self.move_preview = rb

    def _clear_move_preview(self):
        if self.move_preview:
            self.canvas().scene().removeItem(self.move_preview)
            self.move_preview = None

    def _reset_move(self):
        self.move_layer = None
        self.move_fid = None
        self.move_ring = 0
        self.move_idx = -1
        self._clear_move_marker()
        self._clear_move_preview()

    # ═══════════════════════════════════════════════════════════
    #  Cleanup helpers
    # ═══════════════════════════════════════════════════════════

    def _cleanup_mode(self):
        """Clean up state from the current mode before switching."""
        self._clear_hover_marker()
        self._clear_hover_delete()
        self._clear_move_marker()
        self._clear_move_preview()
        self._clear_extend_preview()
        if self.active_mode == MODE_MOVE:
            self._reset_move()
        if self.active_mode == MODE_EXTEND:
            self._reset_extend_vertex()
        self.hover_fid = None
        self.hover_seg_start = -1
        self._hover_vertex_idx = -1

    def _full_reset(self):
        self._cleanup_mode()
        self.active_mode = MODE_NONE

    # ═══════════════════════════════════════════════════════════
    #  Layer / geometry helpers
    # ═══════════════════════════════════════════════════════════

    def _editable_polygon_layer(self, quiet=False):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            if not quiet:
                self.iface.messageBar().pushMessage(
                    "Ola's Polygon Tools", "Select a vector layer first.",
                    level=Qgis.Warning, duration=3)
            return None
        if not layer.isEditable():
            if not quiet:
                self.iface.messageBar().pushMessage(
                    "Ola's Polygon Tools", "Layer must be in edit mode.",
                    level=Qgis.Warning, duration=3)
            return None
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            if not quiet:
                self.iface.messageBar().pushMessage(
                    "Ola's Polygon Tools", "Active layer must be a polygon layer.",
                    level=Qgis.Warning, duration=3)
            return None
        return layer

    def _find_nearest_vertex(self, layer, map_point, tol_px=None):
        if tol_px is None:
            tol_px = self.HOVER_TOLERANCE_PX
        tolerance = tol_px * self.canvas().mapUnitsPerPixel()
        best_fid = None
        best_ring = 0
        best_idx = -1
        best_dist = float("inf")

        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            closest_pt, idx, prev_idx, next_idx, dist = geom.closestVertex(map_point)
            if dist < 0:
                continue
            if dist < best_dist and math.sqrt(dist) < tolerance:
                best_fid = feature.id()
                best_dist = dist
                ring_idx, vertex_in_ring = self._vertex_to_ring_index(geom, idx)
                best_ring = ring_idx
                best_idx = vertex_in_ring

        return best_fid, best_ring, best_idx, best_dist

    def _find_nearest_segment(self, layer, map_point, tol_px=None):
        """Return (fid, ring_idx, seg_start_vertex, snap_point) or None."""
        if tol_px is None:
            tol_px = self.HOVER_TOLERANCE_PX
        tolerance = tol_px * self.canvas().mapUnitsPerPixel()
        best = None
        best_sq_dist = float("inf")

        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            sq_dist, snap_pt, after_vertex, left_of = geom.closestSegmentWithContext(map_point)
            if sq_dist < 0:
                continue
            if sq_dist < best_sq_dist and math.sqrt(sq_dist) < tolerance:
                best_sq_dist = sq_dist
                # after_vertex is the index of the vertex AFTER the snap point
                # so the segment is (after_vertex - 1, after_vertex)
                seg_end = after_vertex
                fid = feature.id()

                ring_idx, seg_end_local = self._vertex_to_ring_index(geom, seg_end)
                ring_pts = self._get_ring_points(geom, ring_idx)
                n = len(ring_pts) - 1
                seg_start_local = (seg_end_local - 1) % n

                best = (fid, ring_idx, seg_start_local, QgsPointXY(snap_pt))

        return best

    def _vertex_to_ring_index(self, geom, vertex_id):
        polygon = geom.asPolygon() if not geom.isMultipart() else geom.asMultiPolygon()[0]
        count = 0
        for ring_idx, ring in enumerate(polygon):
            ring_len = len(ring)
            if vertex_id < count + ring_len:
                local_idx = vertex_id - count
                n_unique = ring_len - 1
                if n_unique > 0 and local_idx >= n_unique:
                    local_idx = local_idx % n_unique
                return ring_idx, local_idx
            count += ring_len
        return 0, vertex_id

    def _get_ring_points(self, geom, ring_idx):
        if geom.isMultipart():
            polygon = geom.asMultiPolygon()[0]
        else:
            polygon = geom.asPolygon()
        return [QgsPointXY(p) for p in polygon[ring_idx]]

    def _rebuild_geometry(self, geom, modified_ring, new_ring_points):
        if geom.isMultipart():
            multi = geom.asMultiPolygon()
            polygon = multi[0]
            polygon[modified_ring] = [QgsPointXY(p) for p in new_ring_points]
            multi[0] = polygon
            return QgsGeometry.fromMultiPolygonXY(multi)
        else:
            polygon = geom.asPolygon()
            polygon[modified_ring] = [QgsPointXY(p) for p in new_ring_points]
            return QgsGeometry.fromPolygonXY(polygon)

    # ═══════════════════════════════════════════════════════════
    #  Visual feedback — generic hover marker (W edge snap / A vertex)
    # ═══════════════════════════════════════════════════════════

    def _show_hover_marker(self, map_pt, color, radius=7):
        scene = self.canvas().scene()
        self._clear_hover_marker()

        canvas_pt = self.toCanvasCoordinates(map_pt)
        self.hover_marker = QGraphicsEllipseItem(
            canvas_pt.x() - radius, canvas_pt.y() - radius,
            radius * 2, radius * 2,
        )
        pen = QPen(color)
        pen.setWidth(2)
        self.hover_marker.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(80)
        self.hover_marker.setBrush(QBrush(fill))
        self.hover_marker.setZValue(1000)
        scene.addItem(self.hover_marker)

    def _clear_hover_marker(self):
        if self.hover_marker:
            self.canvas().scene().removeItem(self.hover_marker)
            self.hover_marker = None

    # ═══════════════════════════════════════════════════════════
    #  Visual feedback — delete hover (red halo + tooltip)
    # ═══════════════════════════════════════════════════════════

    def _show_hover_delete(self, vertex_map_pt, pixel_pos):
        scene = self.canvas().scene()
        self._clear_hover_delete()

        canvas_pt = self.toCanvasCoordinates(vertex_map_pt)
        radius = 12
        self.hover_halo = QGraphicsEllipseItem(
            canvas_pt.x() - radius, canvas_pt.y() - radius,
            radius * 2, radius * 2,
        )
        pen = QPen(QColor(220, 30, 30, 200))
        pen.setWidth(3)
        self.hover_halo.setPen(pen)
        self.hover_halo.setBrush(QBrush(QColor(220, 30, 30, 50)))
        self.hover_halo.setZValue(1000)
        scene.addItem(self.hover_halo)

        self.hover_label = QGraphicsTextItem("delete point")
        font = QFont("Sans", 9, QFont.Bold)
        self.hover_label.setFont(font)
        self.hover_label.setDefaultTextColor(QColor(220, 30, 30))
        self.hover_label.setPos(pixel_pos.x() + 14, pixel_pos.y() + 14)
        self.hover_label.setZValue(1001)
        scene.addItem(self.hover_label)

    def _clear_hover_delete(self):
        scene = self.canvas().scene()
        if self.hover_halo:
            scene.removeItem(self.hover_halo)
            self.hover_halo = None
        if self.hover_label:
            scene.removeItem(self.hover_label)
            self.hover_label = None

    # ═══════════════════════════════════════════════════════════
    #  Visual feedback — move selected marker (blue dot)
    # ═══════════════════════════════════════════════════════════

    def _show_move_selected(self, map_pt):
        self._clear_move_marker()
        self.move_marker = QgsRubberBand(self.canvas(), QgsWkbTypes.PointGeometry)
        self.move_marker.setColor(QColor(21, 101, 192, 220))
        self.move_marker.setWidth(3)
        self.move_marker.setIconSize(10)
        self.move_marker.addPoint(map_pt)

    def _clear_move_marker(self):
        if self.move_marker:
            self.canvas().scene().removeItem(self.move_marker)
            self.move_marker = None
