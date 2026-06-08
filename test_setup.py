from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject

layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Test Polygons", "memory")
pr = layer.dataProvider()
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10,60), QgsPointXY(11,60), QgsPointXY(11,61), QgsPointXY(10,61), QgsPointXY(10,60)]]))
pr.addFeatures([f])
layer.updateExtents()
QgsProject.instance().addMapLayer(layer)
iface.setActiveLayer(layer)
iface.mapCanvas().setExtent(layer.extent().buffered(0.5))
iface.mapCanvas().refresh()
layer.startEditing()
