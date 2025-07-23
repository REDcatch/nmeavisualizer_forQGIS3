import os
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QDialog, QVBoxLayout, QCheckBox, QPushButton
from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QIcon

class NmeaVisualizerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon_toolbar.png")
        self.action = QAction(QIcon(icon_path), "NMEA GNSS Visualizer", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&NMEA GNSS Visualizer", self.action)

    def unload(self):
        self.iface.removePluginMenu("&NMEA GNSS Visualizer", self.action)
        self.iface.removeToolBarIcon(self.action)

    def parse_gga(self, sentence):
        try:
            parts = sentence.split(',')
            if len(parts) < 10:
                return None
            timestamp = parts[1]
            lat_raw, lat_dir = parts[2], parts[3]
            lon_raw, lon_dir = parts[4], parts[5]
            if not lat_raw or not lon_raw:
                return None
            lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
            lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
            lat = -lat if lat_dir == 'S' else lat
            lon = -lon if lon_dir == 'W' else lon
            quality = int(parts[6])
            sats = int(parts[7])
            hdop = float(parts[8])
            alt = float(parts[9]) if parts[9] else 0.0
            return lat, lon, quality, sats, hdop, alt, timestamp
        except:
            return None

    def run(self):
        file_path, _ = QFileDialog.getOpenFileName(None, "Select NMEA file", "", "NMEA Files (*.nmea *.txt)")
        if not file_path:
            return

        dlg = QDialog()
        dlg.setWindowTitle("Export Options")
        layout = QVBoxLayout()
        chk_gpkg = QCheckBox("Export as GPKG")
        chk_shp = QCheckBox("Export as SHP")
        chk_kml = QCheckBox("Export as KML")
        chk_add = QCheckBox("Add to Map (Default)")
        chk_add.setChecked(True)
        layout.addWidget(chk_gpkg)
        layout.addWidget(chk_shp)
        layout.addWidget(chk_kml)
        layout.addWidget(chk_add)
        btn = QPushButton("OK")
        layout.addWidget(btn)
        dlg.setLayout(layout)
        btn.clicked.connect(dlg.accept)
        dlg.exec()

        export_gpkg = chk_gpkg.isChecked()
        export_shp = chk_shp.isChecked()
        export_kml = chk_kml.isChecked()
        add_to_map = chk_add.isChecked()

        features, fields = [], [
            QgsField("quality", QVariant.Int), QgsField("sats", QVariant.Int),
            QgsField("hdop", QVariant.Double), QgsField("latitude", QVariant.Double),
            QgsField("longitude", QVariant.Double), QgsField("altitude", QVariant.Double),
            QgsField("timestamp", QVariant.String)
        ]

        with open(file_path, 'r') as file:
            for line in file:
                if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                    parsed = self.parse_gga(line.strip())
                    if parsed:
                        lat, lon, quality, sats, hdop, alt, timestamp = parsed
                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
                        feat.setAttributes([quality, sats, hdop, lat, lon, alt, timestamp])
                        features.append(feat)

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "NMEA Points", "memory")
        pr = layer.dataProvider()
        pr.addAttributes(fields)
        layer.updateFields()
        pr.addFeatures(features)

        if add_to_map:
            QgsProject.instance().addMapLayer(layer)

        output_base = os.path.splitext(file_path)[0]
        if export_gpkg:
            QgsVectorFileWriter.writeAsVectorFormat(layer, output_base + ".gpkg", "utf-8", layer.crs(), "GPKG")
        if export_shp:
            QgsVectorFileWriter.writeAsVectorFormat(layer, output_base + ".shp", "utf-8", layer.crs(), "ESRI Shapefile")
        if export_kml:
            QgsVectorFileWriter.writeAsVectorFormat(layer, output_base + ".kml", "utf-8", layer.crs(), "KML")

        if not add_to_map:
            QMessageBox.information(None, "Success", f"Loaded {len(features)} positions.")
