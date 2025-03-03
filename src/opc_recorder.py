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
        self.live_update_timer = QTimer(self)  # Timer for live updates
        self.live_update_timer.timeout.connect(self.update_live_values)
        self.live_update_timer.setInterval(100)  # Update every 100ms
        self.record_count = 0
        self.record_data_list = []
        self.selected_vars = {}  # Stores selected variable node IDs
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top bar with connection status
        top_layout = QHBoxLayout()
        
        # Connection status LED
        status_layout = QHBoxLayout()
        self.status_led = QLabel()
        self.status_led.setFixedSize(20, 20)
        self.status_led.setStyleSheet(
            "QLabel { background-color: red; border-radius: 10px; margin: 2px; }"
        )
        status_label = QLabel("Server Status:")
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_led)
        status_layout.addStretch()
        top_layout.addLayout(status_layout)
        
        # Server URL selection
        url_layout = QHBoxLayout()
        url_label = QLabel("OPC UA Server URL:")
        self.url_combo = QComboBox()
        self.url_combo.setEditable(True)
        self.url_combo.addItems([
            "opc.tcp://localhost:4840",
            "opc.tcp://192.168.101.10:4840"
        ])
        self.url_combo.setCurrentText("opc.tcp://localhost:4840")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_combo)
        top_layout.addLayout(url_layout)
        
        main_layout.addLayout(top_layout)

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
        self.var_list.itemChanged.connect(self.on_variable_checked)  # Connect checkbox changes
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
        self.interval_spin.setRange(1, 10000)  # 1ms to 10000ms
        self.interval_spin.setValue(100)  # Default to 100ms
        self.records_spin = QSpinBox()
        self.records_spin.setRange(1, 10000)
        self.records_spin.setValue(5)
        rec_layout.addWidget(QLabel("Interval (ms):"))
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

    def update_connection_status(self, connected=False):
        """Update the connection status LED."""
        if connected:
            self.status_led.setStyleSheet(
                "QLabel { background-color: lime; border-radius: 10px; margin: 2px; }"
            )
        else:
            self.status_led.setStyleSheet(
                "QLabel { background-color: red; border-radius: 10px; margin: 2px; }"
            )

    def connect_and_browse(self):
        """Connects to the OPC UA server and browses the address space."""
        # Disconnect existing client if any
        self.disconnect_client()
        
        # Clear existing items
        self.tree_widget.clear()
        self.dir_combo.clear()
        self.var_list.clear()
        
        server_url = self.url_combo.currentText().strip()
        try:
            print(f"Attempting to connect to: {server_url}")
            self.client = Client(server_url)
            
            # Simple connection without any special configuration
            self.client.connect()
            print("Successfully connected to server")
            self.update_connection_status(True)
            
            # Get root node and start browsing from there
            root = self.client.get_root_node()
            print(f"Got root node: {root}")
            
            # Create root item
            root_item = QTreeWidgetItem(["Root"])
            root_item.setData(0, 1, root.nodeid.to_string())
            self.tree_widget.addTopLevelItem(root_item)
            
            # Browse from root node to see everything
            self.browse_nodes(root, root_item)
            
            QMessageBox.information(self, "Success", "Connected to OPC UA server successfully!")
            
        except Exception as e:
            error_msg = f"Connection Error: {str(e)}\nType: {type(e)}"
            print(error_msg)
            QMessageBox.critical(self, "Connection Error", error_msg)
            self.update_connection_status(False)
            self.disconnect_client()

    def browse_nodes(self, node, parent_item):
        """Recursively browses nodes and adds them to tree and combo box."""
        try:
            display_name = node.get_display_name().Text
            node_id = node.nodeid.to_string()
            print(f"\nBrowsing node: {display_name} (ID: {node_id})")
            
            # Define the path we want to follow
            target_path = ['Root', 'Objects', 'PLC']
            current_level = parent_item.text(0)  # Get the current node name
            
            try:
                children = node.get_children()
                print(f"Found {len(children)} children for node {display_name}")
            except Exception as ce:
                print(f"Error getting children for node {display_name}: {str(ce)}")
                return
                
            for child in children:
                try:
                    # Get node name and class
                    browse_name = child.get_display_name().Text
                    child_id = child.nodeid.to_string()
                    
                    # If we haven't reached PLC yet, only follow the target path
                    if current_level in target_path and current_level != 'PLC':
                        current_index = target_path.index(current_level)
                        if current_index + 1 < len(target_path):
                            # If we're not at PLC level, only process next item in path
                            if browse_name != target_path[current_index + 1]:
                                continue
                    
                    # Get node class
                    node_class = None
                    try:
                        node_class = child.get_node_class()
                    except Exception:
                        print(f"Could not get node class for {browse_name}")
                    
                    print(f"Processing child: {browse_name} (Class: {node_class}, ID: {child_id})")
                    
                    # Create tree item
                    child_item = QTreeWidgetItem([browse_name])
                    child_item.setData(0, 1, child_id)
                    parent_item.addChild(child_item)
                    
                    # If we're at or below PLC level, show all variables
                    if current_level == 'PLC' or browse_name == 'PLC' or not current_level in target_path:
                        # Try to read value if it might be a variable
                        try:
                            if node_class == ua.NodeClass.Variable:
                                value = child.get_value()
                                value_type = type(value).__name__
                                print(f"Variable {browse_name} value: {value} (Type: {value_type})")
                                
                                # Add value info to tree
                                value_str = f"Value: {value}, Type: {value_type}"
                                value_item = QTreeWidgetItem([value_str])
                                child_item.addChild(value_item)
                                
                                # Add to variable list with full path
                                path_parts = []
                                temp_item = child_item
                                while temp_item is not None:
                                    path_parts.insert(0, temp_item.text(0))
                                    temp_item = temp_item.parent()
                                full_path = '/'.join(path_parts)
                                
                                item = QListWidgetItem(full_path)
                                item.setCheckState(0)
                                item.setData(1, child_id)
                                self.var_list.addItem(item)
                        except Exception as ve:
                            print(f"Error reading value for {browse_name}: {ve}")
                        
                        # Add to directory combo if it has children
                        try:
                            if len(child.get_children()) > 0:
                                path_parts = []
                                temp_item = child_item
                                while temp_item is not None:
                                    path_parts.insert(0, temp_item.text(0))
                                    temp_item = temp_item.parent()
                                full_path = '/'.join(path_parts)
                                print(f"Adding to directory combo: {full_path}")
                                self.dir_combo.addItem(full_path, child_id)
                        except Exception:
                            pass
                        
                        # Continue browsing all nodes under PLC
                        self.browse_nodes(child, child_item)
                    else:
                        # If we're still in the path to PLC, continue browsing
                        if current_level in target_path:
                            self.browse_nodes(child, child_item)
                        
                except Exception as ce:
                    print(f"Error processing child node {getattr(child, 'nodeid', 'unknown')}: {str(ce)}")
                    continue
                
        except Exception as e:
            print(f"Error browsing node {getattr(node, 'nodeid', 'unknown')}: {str(e)}")
        
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

        # Connect to server for persistent connection if not already connected
        if not self.persistent_client:
            server_url = self.url_combo.currentText().strip()
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
        interval_ms = self.interval_spin.value()  # Already in milliseconds
        self.record_timer.start(interval_ms)
        QMessageBox.information(self, "Recording", "Recording started.")

    def record_data(self):
        """Records selected variables' values and updates the live table."""
        if self.record_count >= self.records_spin.value():
            self.stop_recording()
            return

        current_time = datetime.now()
        row = {"timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}  # 24-hour format with milliseconds
        
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
        """Stops the recording process."""
        self.record_timer.stop()
        # Only disconnect the persistent client if we're not using it for live updates
        if self.persistent_client and not any(item.checkState() == 2 for item in (self.var_list.item(i) for i in range(self.var_list.count()))):
            try:
                self.persistent_client.disconnect()
                self.persistent_client = None
            except Exception:
                pass
        QMessageBox.information(self, "Recording", "Recording stopped.")

    def save_csv(self):
        """Saves the recorded data as a CSV file."""
        if not self.record_data_list:
            QMessageBox.warning(self, "Warning", "No recorded data to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if file_path:
            try:
                # Write data directly since timestamps are already in correct format
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
                self.update_connection_status(False)

    def on_variable_checked(self, item):
        """Handle when a variable checkbox is checked/unchecked."""
        var_name = item.text()
        node_id = item.data(1)
        
        if item.checkState() == 2:  # Checked
            self.selected_vars[var_name] = node_id
            # Start live updates if this is the first checked variable
            if len(self.selected_vars) == 1:
                self.start_live_updates()
        else:  # Unchecked
            if var_name in self.selected_vars:
                del self.selected_vars[var_name]
            # Stop live updates if no variables are checked
            if len(self.selected_vars) == 0:
                self.stop_live_updates()
        
        # Update live values table
        self.setup_live_table()

    def setup_live_table(self):
        """Set up the live values table with current selected variables."""
        self.live_table.setRowCount(len(self.selected_vars))
        self.live_table.setColumnCount(2)
        self.live_table.setHorizontalHeaderLabels(["Variable", "Current Value"])
        
        for i, var_name in enumerate(self.selected_vars.keys()):
            self.live_table.setItem(i, 0, QTableWidgetItem(var_name))
            self.live_table.setItem(i, 1, QTableWidgetItem("Waiting..."))

    def start_live_updates(self):
        """Start live updates for selected variables."""
        if not self.persistent_client:
            try:
                server_url = self.url_combo.currentText().strip()
                self.persistent_client = Client(server_url)
                self.persistent_client.connect()
                self.live_update_timer.start()
                print("Started live updates")
            except Exception as e:
                QMessageBox.critical(self, "Connection Error", f"Could not start live updates: {str(e)}")
                self.persistent_client = None
        else:
            self.live_update_timer.start()

    def stop_live_updates(self):
        """Stop live updates."""
        self.live_update_timer.stop()
        if self.persistent_client and not self.record_timer.isActive():
            try:
                self.persistent_client.disconnect()
                self.persistent_client = None
                print("Stopped live updates")
            except Exception:
                pass

    def update_live_values(self):
        """Update the live values table with current values."""
        if not self.persistent_client:
            return
            
        for i, (var_name, node_id) in enumerate(self.selected_vars.items()):
            try:
                node = self.persistent_client.get_node(node_id)
                value = node.get_value()
                self.live_table.setItem(i, 1, QTableWidgetItem(str(value)))
            except Exception as e:
                self.live_table.setItem(i, 1, QTableWidgetItem(f"Error: {str(e)}"))

    def closeEvent(self, event):
        """Ensures all clients are disconnected when the application closes."""
        self.stop_live_updates()
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