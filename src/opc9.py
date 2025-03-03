import sys
import csv
from datetime import datetime
from opcua import Client, ua
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QTreeWidget, QTreeWidgetItem, QComboBox, QListWidget,
    QListWidgetItem, QSpinBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox
)
from PyQt5.QtCore import QTimer

class OPCUARecorder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Variable Recorder")
        self.client = None  # Temporary client for browsing
        self.persistent_client = None  # Persistent client for recording/live updates
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.record_data)
        self.record_count = 0
        self.record_data_list = []
        self.selected_vars = {}  # Stores selected variable node IDs
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # OPC UA Server URL input
        url_layout = QHBoxLayout()
        url_label = QLabel("OPC UA Server URL:")
        self.url_edit = QLineEdit("opc.tcp://localhost:4840")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        main_layout.addLayout(url_layout)

        # Connect and Browse button
        self.connect_button = QPushButton("Connect and Browse")
        self.connect_button.clicked.connect(self.connect_and_browse)
        main_layout.addWidget(self.connect_button)

        # Tree view to display the full address space
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("OPC UA Address Space")
        main_layout.addWidget(self.tree_widget)

        # Directory selection combo box
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Select Directory:")
        self.dir_combo = QComboBox()
        self.dir_combo.currentIndexChanged.connect(self.directory_changed)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_combo)
        main_layout.addLayout(dir_layout)

        # Variables list with checkboxes
        main_layout.addWidget(QLabel("Select Variables to Record:"))
        self.var_list = QListWidget()
        main_layout.addWidget(self.var_list)

        # Live Values table: shows current value of each selected variable
        main_layout.addWidget(QLabel("Live Values:"))
        self.live_table = QTableWidget()
        self.live_table.setColumnCount(2)
        self.live_table.setHorizontalHeaderLabels(["Variable", "Current Value"])
        main_layout.addWidget(self.live_table)

        # Recording options: interval and total number of records
        rec_layout = QHBoxLayout()
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setValue(1)
        self.records_spin = QSpinBox()
        self.records_spin.setRange(1, 10000)
        self.records_spin.setValue(5)
        rec_layout.addWidget(QLabel("Interval (sec):"))
        rec_layout.addWidget(self.interval_spin)
        rec_layout.addWidget(QLabel("Number of Records:"))
        rec_layout.addWidget(self.records_spin)
        main_layout.addLayout(rec_layout)

        # Start and Stop Recording buttons
        btn_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Record")
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button = QPushButton("Stop Record")
        self.stop_button.clicked.connect(self.stop_recording)
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.stop_button)
        main_layout.addLayout(btn_layout)

        # Table to display recorded data
        main_layout.addWidget(QLabel("Recorded Data:"))
        self.data_table = QTableWidget()
        main_layout.addWidget(self.data_table)

        # Button to save CSV file
        self.save_button = QPushButton("Save CSV")
        self.save_button.clicked.connect(self.save_csv)
        main_layout.addWidget(self.save_button)

    def browse_nodes(self, node, parent_item):
        """Recursively browses nodes and adds them to tree and combo box."""
        try:
            print(f"Browsing node: {node.get_display_name().Text} (ID: {node.nodeid})")
            children = node.get_children()
            for child in children:
                try:
                    # Get node name and class
                    browse_name = child.get_display_name().Text
                    node_class = child.get_node_class()
                    node_id = child.nodeid.to_string()
                    print(f"Found child: {browse_name}, Class: {node_class}, ID: {node_id}")
                    
                    # Skip some standard folders that might cause issues
                    if node_id in ['i=84', 'i=85', 'i=86']:  # Types, Views, Objects folders
                        print(f"Skipping standard folder: {browse_name}")
                        continue
                    
                    # Create tree item
                    child_item = QTreeWidgetItem([browse_name])
                    child_item.setData(0, 1, node_id)
                    parent_item.addChild(child_item)
                    
                    # Add to combo box if it's a folder/object
                    if node_class in [ua.NodeClass.Object, ua.NodeClass.ObjectType, ua.NodeClass.Folder]:
                        self.dir_combo.addItem(browse_name, node_id)
                    
                    # If it's a variable, add it directly to the variable list
                    if node_class == ua.NodeClass.Variable:
                        try:
                            # Try to read the value to verify access
                            value = child.get_value()
                            print(f"Variable {browse_name} value: {value}")
                            
                            item = QListWidgetItem(browse_name)
                            item.setCheckState(0)  # Unchecked
                            item.setData(1, node_id)
                            self.var_list.addItem(item)
                        except Exception as ve:
                            print(f"Cannot read variable {browse_name}: {ve}")
                    
                    # Only recurse into Objects folder and custom folders
                    if node_class in [ua.NodeClass.Object, ua.NodeClass.Folder]:
                        self.browse_nodes(child, child_item)
                        
                except Exception as ce:
                    print(f"Error processing child node: {ce}")
                    continue
                
        except Exception as e:
            print(f"Error browsing node {node.nodeid}: {e}")
        
    def directory_changed(self):
        """When directory selection changes, update the variable list."""
        self.var_list.clear()
        index = self.dir_combo.currentIndex()
        if index < 0:
            return
        node_id = self.dir_combo.itemData(index)
        try:
            node = self.client.get_node(node_id)
            children = node.get_children()
            for child in children:
                if child.get_node_class() == ua.NodeClass.Variable:
                    item = QListWidgetItem(child.get_display_name().Text)
                    item.setCheckState(0)  # Unchecked
                    item.setData(1, child.nodeid.to_string())
                    self.var_list.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def start_recording(self):
        """Starts recording data from selected OPC UA variables."""
        # First check if any variables are selected
        self.selected_vars = {}
        for i in range(self.var_list.count()):
            item = self.var_list.item(i)
            if item.checkState():
                self.selected_vars[item.text()] = item.data(1)
        
        if not self.selected_vars:
            QMessageBox.warning(self, "Warning", "Please select at least one variable to record.")
            return

        # Connect to server for persistent connection
        server_url = self.url_edit.text().strip()
        try:
            self.persistent_client = Client(server_url)
            self.persistent_client.connect()
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))
            return

        # Reset recording state
        self.record_count = 0
        self.record_data_list = []
        
        # Setup data table headers
        headers = ["timestamp"] + list(self.selected_vars.keys())
        self.data_table.setColumnCount(len(headers))
        self.data_table.setHorizontalHeaderLabels(headers)
        
        # Setup live values table
        self.live_table.setRowCount(len(self.selected_vars))
        for i, var_name in enumerate(self.selected_vars.keys()):
            self.live_table.setItem(i, 0, QTableWidgetItem(var_name))
            self.live_table.setItem(i, 1, QTableWidgetItem("Waiting..."))

        # Start the timer for recording
        interval_ms = self.interval_spin.value() * 1000  # Convert seconds to milliseconds
        self.record_timer.start(interval_ms)
        QMessageBox.information(self, "Recording", "Recording started.")

    def record_data(self):
        """Records selected variables' values and updates the live table."""
        if self.record_count >= self.records_spin.value():
            self.stop_recording()
            return

        row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        for label, node_id in self.selected_vars.items():
            try:
                node = self.persistent_client.get_node(node_id)
                value = node.get_value()
                row[label] = value
            except Exception as e:
                row[label] = f"Error: {e}"

        self.record_data_list.append(row)
        self.record_count += 1
        self.update_data_table()

    def update_data_table(self):
        """Updates the data table with the recorded values."""
        self.data_table.setRowCount(len(self.record_data_list))
        headers = ["timestamp"] + list(self.selected_vars.keys())
        
        for row_idx, data_row in enumerate(self.record_data_list):
            for col_idx, header in enumerate(headers):
                value = str(data_row.get(header, ""))
                self.data_table.setItem(row_idx, col_idx, QTableWidgetItem(value))
                
            # Update live values table for the most recent row
            if row_idx == len(self.record_data_list) - 1:
                for i, (var_name, _) in enumerate(self.selected_vars.items()):
                    self.live_table.setItem(i, 1, QTableWidgetItem(str(data_row.get(var_name, ""))))

    def stop_recording(self):
        """Stops the recording process and disconnects the persistent OPC UA client."""
        self.record_timer.stop()
        if self.persistent_client:
            try:
                self.persistent_client.disconnect()
            except Exception:
                pass
            self.persistent_client = None
        QMessageBox.information(self, "Recording", "Recording stopped.")

    def save_csv(self):
        """Saves the recorded data as a CSV file."""
        if not self.record_data_list:
            QMessageBox.warning(self, "Warning", "No recorded data to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.record_data_list[0].keys())
                    writer.writeheader()
                    writer.writerows(self.record_data_list)
                QMessageBox.information(self, "Saved", f"Data saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def disconnect_client(self):
        """Safely disconnects the OPC UA client to prevent socket errors."""
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            finally:
                self.client = None

    def closeEvent(self, event):
        """Ensures all clients are disconnected when the application closes."""
        self.disconnect_client()
        if self.persistent_client:
            try:
                self.persistent_client.disconnect()
            except Exception:
                pass
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OPCUARecorder()
    window.show()
    sys.exit(app.exec_())