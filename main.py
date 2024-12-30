import sys
import os
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QLabel,
    QSizePolicy,
    QListWidget,
)
from PyQt6.QtCore import Qt, QDir, QObject, pyqtSlot, pyqtSignal, QEvent
from PyQt6.QtGui import QPixmap, QKeyEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import pyqtSlot, QUrl
from PyQt6.QtWebChannel import QWebChannel
import exif
import shapely.wkt
import shapely.geometry


class CustomWebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        print(f"JavaScript console message: {message} (line: {line_number})")


class JavaScriptHandler(QObject):
    coordinatesUpdated = pyqtSignal(str, str)

    @pyqtSlot(str, str)
    def coordinatesUpdatedSlot(self, lat, lng):
        self.coordinatesUpdated.emit(lat, lng)


class MapWidget(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.setPage(CustomWebEnginePage(self))
        self.channel = QWebChannel()
        self.jsHandler = JavaScriptHandler()

        self.channel.registerObject("jsHandler", self.jsHandler)
        self.page().setWebChannel(self.channel)

        self.setHtml(self.get_initial_map())

    def get_initial_map(self):
        leaflet_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Leaflet Map</title>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style> #map { width: 100%; height: 100%; } </style>
        </head>
        <body>
            <div id="map" style="height: 600px;"></div>
            <div id="coordinates">Coordinates: </div>
            <script>
                var map = L.map('map',{
            wheelPxPerZoomLevel: 10 // Add this option
        }).setView([55.666, 37.666], 11);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                }).addTo(map);

                var marker;

                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.jsHandler = channel.objects.jsHandler;
                    console.log("Channel initialized");
                });

                function removeMarkers() {
                    
                    if (marker) {
                        map.removeLayer(marker);
                    }
                }
                function addMarker(position) {
                   removeMarkers();
                    // Custom  icon
                    var squareIcon = L.icon({
                        iconUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHg9IjMiIHk9IjMiIHdpZHRoPSI5NCIgaGVpZ2h0PSI5NCIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSI2IiBzdHJva2UtbWl0ZXJsaW1pdD0iMi42MTMxMyIvPgo8cGF0aCBkPSJNNTAgMFYxMDAiIHN0cm9rZT0iYmxhY2siIHN0cm9rZS13aWR0aD0iMyIvPgo8cGF0aCBkPSJNMCA1MEMyLjgxNDA3IDUwIDY3LjgzOTIgNTAgMTAwIDUwIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjMiLz4KPC9zdmc+Cg==', // Base64 encoded SVG
                        iconSize: [20, 20],
                        iconAnchor: [10, 10]
                    });

                    // Create a square marker at the the map
                    marker = L.marker(position, {
                    draggable: true,
                    autoPan: true,
                    icon: squareIcon

                    }).addTo(map);

                    marker.on('dragend', function(e) {
                        var coords = e.target.getLatLng();
                        document.getElementById('coordinates').innerText = "Coordinates: " + coords.lat.toFixed(7) + ", " + coords.lng.toFixed(7);
                        if (window.jsHandler) {
                            //console.log("Sending coordinates to channel: " + coords.lat.toFixed(4) + ", " + coords.lng.toFixed(4));
                            window.jsHandler.coordinatesUpdatedSlot(coords.lat.toFixed(7), coords.lng.toFixed(7));
                        } else {
                            console.log("jsHandler is not defined");
                        }
                    });
                    
                    // Move marker to click location
                    map.on('click', function(e) {
                        var clickCoords = e.latlng;
                        marker.setLatLng(clickCoords);
                        marker.fire('dragend', { target: marker });
                        document.getElementById('coordinates').innerText = "Coordinates: " + clickCoords.lat.toFixed(7) + ", " + clickCoords.lng.toFixed(7);
                    });
                    }
                    function move_to_favorite_place(position, zoom) {
                        map.setView(position, zoom);
                        addMarker(position);
                    }
                    
            </script>
        </body>
        </html>
        """
        return leaflet_html


class RaskladGeotag(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Rasklad Geotag")
        self.setGeometry(100, 100, 800, 600)
        self.initial_coords = (55.666, 37.666)

        self.mainfiles = []
        self.mainfile_selected = ""
        self.filter_has_coords_enabled = False  # Initial state of the filter

        self.locationFavs = [
            {"key": "3", "name": "Алмаз", "wkt_geom": "POINT(37.60635 55.71159)"},
            {
                "key": "4",
                "name": "Университет",
                "wkt_geom": "POINT(37.536613 55.692061)",
            },
            {
                "key": "5",
                "name": "Тульская",
                "wkt_geom": "POINT(37.62311 55.70441)",
            },
            {
                "key": "6",
                "name": "Верхние Котлы",
                "wkt_geom": "POINT(37.62255 55.68992)",
            },
            {
                "key": "7",
                "name": "Nagatinskaya",
                "wkt_geom": "POINT(37.62372 55.68385)",
            },
        ]

        self.initUI()

    def initUI(self):
        widget = QWidget()
        self.setCentralWidget(widget)

        layout_horizontal = QHBoxLayout()
        layout = QVBoxLayout()

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label.setMinimumHeight(400)
        self.label.setScaledContents(True)
        self.label.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
        )

        self.select_button = QPushButton("Select Folder", self)
        self.select_button.clicked.connect(self.open_folder_dialog)

        self.save_button = QPushButton("Save coordinates to EXIF", self)
        self.save_button.clicked.connect(self.save2exif)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        # self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Modification Date", "lat", "lon", "State"]
        )
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 200)
        self.table.itemSelectionChanged.connect(self.display_image)
        self.table.installEventFilter(self)

        self.file_path_label = QLabel(self)
        self.file_path_label.setText("Selected File Path: ")

        layout.addWidget(self.label)
        layout.addWidget(self.select_button)
        layout.addWidget(self.table)
        layout.addWidget(self.file_path_label)

        layout_horizontal.addLayout(layout)

        self.map_widget = MapWidget()
        layout_vertical_right = QVBoxLayout()
        layout_vertical_right.addWidget(self.map_widget)

        layout_horizontal.addLayout(layout_vertical_right)
        self.coordinates_label = QLabel("Coordinates: ")
        self.map_widget.jsHandler.coordinatesUpdated.connect(
            self.update_coordinates_label
        )

        self.add_marker_button = QPushButton("Add Marker to Center")
        self.add_marker_button.clicked.connect(self.add_marker)
        layout_vertical_right.addWidget(self.add_marker_button)
        map_fav_widget = QListWidget()
        sorted_locationFavs = sorted(
            self.locationFavs, key=lambda x: (x["key"], x["name"])
        )

        for el in sorted_locationFavs:
            map_fav_widget.addItem(f"{el['key']} {el['name']}")
        # map_fav_widget.addItems(
        #    ["1 Октябрьская", "2 Шаболовская", "3 Алмаз", "4 Университет"]
        # )
        layout_vertical_right.addWidget(map_fav_widget)

        self.toggle_button = QPushButton("Hide files with coordinates", self)
        self.toggle_button.clicked.connect(self.toggle_filter)
        layout.addWidget(self.toggle_button)

        layout.addWidget(self.coordinates_label)
        layout.addWidget(self.save_button)

        widget.setLayout(layout_horizontal)
        self.marker_coordinates = None
        self.statusBar().showMessage("Select a directory with images to start")

    def toggle_filter(self):
        self.filter_has_coords_enabled = not self.filter_has_coords_enabled
        if self.filter_has_coords_enabled:
            self.toggle_button.setText("Display all files")
            # Add your filter logic here
            self.display_files(self.folder_path)
            print("Filter enabled")
            self.statusBar().showMessage("Showing only files without coordinates")
        else:
            self.toggle_button.setText("Hide files with coordinates")
            # Remove your filter logic here
            self.display_files(self.folder_path)
            print("Filter disabled")
            self.statusBar().showMessage("Showing all files")

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress and source is self.table:
            self.keyPressEvent(event)
            return True
        return super().eventFilter(source, event)

    def keyPressEvent(self, event: QKeyEvent):

        key_pressed = event.text()
        for fav in self.locationFavs:
            if fav["key"] == key_pressed:
                self.statusBar().showMessage(f'You pressed the key for {fav["name"]}')
                # wkt_point = "POINT(37.620393 55.734036)"
                wkt_point = fav.get("wkt_geom")
                if not wkt_point:
                    return
                retrieved_point = shapely.wkt.loads(wkt_point)
                retrieved_latitude = retrieved_point.y
                retrieved_longitude = retrieved_point.x
                zoom = 14
                js_code = f"move_to_favorite_place([{retrieved_latitude}, {retrieved_longitude}],{zoom});"
                self.map_widget.page().runJavaScript(js_code)
                return
        super().keyPressEvent(event)

    def add_marker(self, lat=None, lon=None):
        if not lat or not lon:
            js_code = "addMarker(map.getCenter());"
        else:
            js_code = f"addMarker([{lat}, {lon}]);"

        self.map_widget.page().runJavaScript(js_code)

    @pyqtSlot(str, str)
    def update_coordinates_label(self, lat, lon):
        if self.mainfile_selected:
            self.coordinates_label.setText(
                f"Coordinates: {lat} {lon} for file {self.mainfile_selected}"
            )
            for i, f in enumerate(self.mainfiles):
                if f["file_path"] == self.mainfile_selected:
                    f["modified"]["lat"] = lat
                    f["modified"]["lon"] = lon
                    f["is_modified"] = True

                    row_count = self.table.rowCount()
                    for row in range(row_count):
                        item = self.table.item(row, 0)  # Get the item in column 0
                        if item and item.text() == f["file_name"]:
                            self.table.setItem(
                                row, 2, QTableWidgetItem(f"{lat} modified")
                            )
                            self.table.setItem(
                                row, 3, QTableWidgetItem(f"{lon} modified")
                            )

                    break

    def save2exif(self):
        def to_deg(value, loc):
            value = float(value)
            if value < 0:
                loc_value = loc[0]
            else:
                loc_value = loc[1]

            abs_value = abs(value)
            deg = int(abs_value)
            temp_min = (abs_value - deg) * 60
            min = int(temp_min)
            sec = round((temp_min - min) * 60, 6)

            return deg, min, sec, loc_value

        for i, f in enumerate(self.mainfiles):
            if f.get("is_modified"):
                assert f["modified"]["lat"] and f["modified"]["lon"]
                lat = f["modified"]["lat"]
                lon = f["modified"]["lon"]
                if lat and lon:
                    lat_deg = to_deg(lat, ("S", "N"))
                    lon_deg = to_deg(lon, ("W", "E"))
                    creation_time = os.path.getctime(f["file_path"])
                    mod_time = os.path.getmtime(f["file_path"])

                    with open(f["file_path"], "rb") as image_file:
                        img = exif.Image(image_file)
                    img.gps_latitude = lat_deg[:3]
                    img.gps_latitude_ref = lat_deg[3]
                    img.gps_longitude = lon_deg[:3]
                    img.gps_longitude_ref = lon_deg[3]
                    with open(f["file_path"], "wb") as new_image_file:
                        new_image_file.write(img.get_file())
                    os.utime(f["file_path"], (creation_time, mod_time))

                    self.coordinates_label.setText(
                        f"Coordinates: {lat} {lon} for file {f['file_name']} saved to EXIF"
                    )
                else:
                    self.coordinates_label.setText(
                        f"Coordinates not found for file {f['file_name']}"
                    )

        has_coords1 = len([f for f in self.mainfiles if f.get("lat")])
        has_coords2 = len(
            [
                f
                for f in self.mainfiles
                if f.get("modified") and f["modified"].get("lat")
            ]
        )
        has_coords = has_coords1 + has_coords2
        total = len(self.mainfiles)
        self.statusBar().showMessage(
            f"Coordinates saved to EXIF. {has_coords} of {total} files have coordinates"
        )
        self.display_files(self.folder_path, supress_statusbar=True)

    def open_folder_dialog(self):
        self.folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if self.folder_path:
            self.display_files(self.folder_path)

    def read_files_data(self, folder_path):
        self.mainfiles = []
        print("mainfiles cleared")
        files = os.listdir(folder_path)
        for i, file_name in enumerate(files):
            if not file_name.lower().endswith(".jpg"):
                continue
            f = dict()
            f["modified"] = dict()
            f["file_path"] = os.path.join(folder_path, file_name)
            f["file_name"] = file_name
            f["file_info"] = os.stat(f["file_path"])
            f["modification_date"] = self.format_date(f["file_info"].st_mtime)
            try:
                with open(f["file_path"], "rb") as image_file:
                    img = exif.Image(image_file)
                    f["model"] = img.get("model")
                    f["datetime_original"] = img.get("datetime_original")

                    if (
                        img.has_exif
                        and img.get("gps_latitude")
                        and img.get("gps_longitude")
                    ):
                        lat = (
                            img.gps_latitude[0]
                            + img.gps_latitude[1] / 60
                            + img.gps_latitude[2] / 3600
                        )
                        lon = (
                            img.gps_longitude[0]
                            + img.gps_longitude[1] / 60
                            + img.gps_longitude[2] / 3600
                        )
                        if img.gps_latitude_ref == "S":
                            lat = -lat
                        if img.gps_longitude_ref == "W":
                            lon = -lon

                        f["lat"] = lat
                        f["lon"] = lon
            except:
                print("exif read error " + f["file_path"])

            self.mainfiles.append(f)

    def display_files(self, folder_path, supress_statusbar=False):
        self.read_files_data(folder_path)
        self.folder_path = folder_path  # Save the selected folder path

        self.table.setSortingEnabled(False)  # Disable sorting while updating
        self.table.setRowCount(0)

        files = self.mainfiles
        if self.filter_has_coords_enabled:
            files = [
                f
                for f in self.mainfiles
                if f.get("lat") is None and f.get("lon") is None
            ]

        self.table.setRowCount(len(files))

        for i, f in enumerate(files):

            item_file_name = QTableWidgetItem(f["file_name"])
            item_datetime = QTableWidgetItem(f.get("datetime_original"))
            item_lat = QTableWidgetItem(str(f.get("lat", "")))
            item_lon = QTableWidgetItem(str(f.get("lon", "")))

            # Disable editing for each item
            item_file_name.setFlags(
                item_file_name.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            item_datetime.setFlags(item_datetime.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_lat.setFlags(item_lat.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_lon.setFlags(item_lon.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(i, 0, item_file_name)
            self.table.setItem(i, 1, item_datetime)
            self.table.setItem(i, 2, item_lat)
            self.table.setItem(i, 3, item_lon)

        self.table.setSortingEnabled(True)  # Enable sorting after updating
        self.table.viewport().update()  # Explicitly trigger a redraw of the table
        if not supress_statusbar:
            self.statusBar().showMessage(f"Select image in table to edit coordinates")

    def display_image(self):
        selected_items = self.table.selectedItems()
        if selected_items:
            file_name = selected_items[0].text()
            full_path = os.path.join(self.folder_path, file_name)
            self.mainfile_selected = full_path
            self.file_path_label.setText(f"Selected File Path: {full_path}")
            pixmap = QPixmap(full_path)
            self.label.setPixmap(
                pixmap.scaled(
                    self.label.width(),
                    self.label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
            )
            self.label.setScaledContents(True)

            for i, f in enumerate(self.mainfiles):
                if f["file_path"] == full_path:
                    if f["modified"].get("lat") and f["modified"].get("lon"):
                        self.add_marker(f["modified"]["lat"], f["modified"]["lon"])
                    elif f.get("lat") and f.get("lon"):
                        self.add_marker(f["lat"], f["lon"])
                    else:
                        self.add_marker()
                    self.statusBar().showMessage(
                        f"Move the marker to set coordinates for {file_name}"
                    )

    def format_date(self, timestamp):
        from datetime import datetime

        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def main():
    app = QApplication(sys.argv)
    viewer = RaskladGeotag()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
