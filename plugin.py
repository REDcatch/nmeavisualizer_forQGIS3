
import os
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

class NmeaVisualizerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        self.action = QAction("NMEA GNSS Visualizer", self.iface.mainWindow())
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

            # Parse latitude
            lat_raw = parts[2]
            lat_dir = parts[3]
            lon_raw = parts[4]
            lon_dir = parts[5]

            if not lat_raw or not lon_raw:
                return None

            lat_deg = float(lat_raw[:2])
            lat_min = float(lat_raw[2:])
            lat = lat_deg + lat_min / 60.0
            if lat_dir == 'S':
                lat = -lat

            lon_deg = float(lon_raw[:3])
            lon_min = float(lon_raw[3:])
            lon = lon_deg + lon_min / 60.0
            if lon_dir == 'W':
                lon = -lon

            quality = int(parts[6])
            sats = int(parts[7])
            hdop = float(parts[8])
            alt = float(parts[9]) if parts[9] else 0.0

            return lat, lon, quality, sats, hdop, alt, timestamp
        except:
            return None

    def parse_rmc(self, sentence):
        try:
            parts = sentence.split(',')
            if len(parts) < 9:
                return None, None, None
            timestamp = parts[1]
            speed_knots = float(parts[7]) if parts[7] else 0.0
            course_deg = float(parts[8]) if parts[8] else 0.0
            return timestamp, speed_knots, course_deg
        except:
            return None, None, None

    def parse_gst(self, sentence):
        try:
            parts = sentence.split(',')
            if len(parts) < 9:
                return None, None, None, None, None
            timestamp = parts[1]
            rms = float(parts[6]) if parts[6] else 0.0
            sigma_lat = float(parts[7]) if parts[7] else 0.0
            sigma_lon = float(parts[8]) if parts[8] else 0.0
            sigma_alt = float(parts[9].split('*')[0]) if parts[9] else 0.0
            return timestamp, rms, sigma_lat, sigma_lon, sigma_alt
        except:
            return None, None, None, None, None

    def run(self):
        file_path, _ = QFileDialog.getOpenFileName(None, "Select NMEA file", "", "NMEA Files (*.nmea *.txt)")
        if not file_path:
            return

        features = []
        rmc_data = {}
        gst_data = {}

        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()

                if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                    t, speed, course = self.parse_rmc(line)
                    if t:
                        rmc_data[t] = (speed, course)

                if line.startswith("$GPGST") or line.startswith("$GNGST"):
                    t, rms, slat, slon, salt = self.parse_gst(line)
                    if t:
                        gst_data[t] = (rms, slat, slon, salt)

                if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                    result = self.parse_gga(line)
                    if result:
                        lat, lon, quality, sats, hdop, alt, timestamp = result
                        point = QgsPointXY(lon, lat)
                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry.fromPointXY(point))
                        speed, course = rmc_data.get(timestamp, (0.0, 0.0))
                        rms, slat, slon, salt = gst_data.get(timestamp, (0.0, 0.0, 0.0, 0.0))
                        feat.setAttributes([quality, sats, hdop, lat, lon, alt, timestamp, speed, course, rms, slat, slon, salt])
                        features.append(feat)

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "NMEA GNSS Points", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("quality", QVariant.Int),
            QgsField("sats", QVariant.Int),
            QgsField("hdop", QVariant.Double),
            QgsField("latitude", QVariant.Double),
            QgsField("longitude", QVariant.Double),
            QgsField("altitude", QVariant.Double),
            QgsField("timestamp", QVariant.String),
            QgsField("speed_knots", QVariant.Double),
            QgsField("course_deg", QVariant.Double),
            QgsField("rms", QVariant.Double),
            QgsField("sigma_lat", QVariant.Double),
            QgsField("sigma_lon", QVariant.Double),
            QgsField("sigma_alt", QVariant.Double)
        ])
        layer.updateFields()
        pr.addFeatures(features)
        layer.updateExtents()

        # Apply categorized style for all known fix types
        quality_styles = [
            (0, "Invalid", "#FF0000"),
            (1, "GPS Fix", "#FFA500"),
            (2, "DGPS Fix", "#32CD32"),
            (4, "RTK Fixed", "#0000FF"),
            (5, "RTK Float", "#00FFFF"),
            (999, "Other", "#A9A9A9")  # fallback for unlisted quality values
        ]

        categories = []
        for value, label, color_str in quality_styles:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(color_str))

            if value == 1:
                symbol.symbolLayer(0).setShape(4)  # Rhombus
            elif value == 2:
                symbol.symbolLayer(0).setShape(2)  # Diamond
            elif value == 4:
                symbol.setColor(QColor("#32CD32"))
                symbol.symbolLayer(0).setShape(0)  # Circle
            elif value == 5:
                symbol.setColor(QColor("#FFFF00"))
                symbol.symbolLayer(0).setShape(0)  # Circle

            category = QgsRendererCategory(value, symbol, label)
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer("quality", categories)
        renderer.setFallbackSymbol(QgsSymbol.defaultSymbol(layer.geometryType()))
        renderer.fallbackSymbol().setColor(QColor("#A9A9A9"))
        layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(None, "Success", f"Loaded {len(features)} valid positions from NMEA file.")
