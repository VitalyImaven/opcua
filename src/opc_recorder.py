import sys
import csv
import os
from datetime import datetime
from opcua import Client, ua
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QTreeWidget, QTreeWidgetItem, QComboBox, QListWidget,
    QListWidgetItem, QSpinBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QFrame, QSplitter, QHeaderView, QCheckBox, QTabWidget, QInputDialog
)
from PyQt5.QtCore import QTimer, Qt

class RecordingScenario(QWidget):
    def __init__(self, parent=None, name="New Scenario", client=None):
        super().__init__(parent)
        self.name = name
        self.client = client
        self.selected_vars = {}
        self.record_data_list = []
        self.record_count = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.record_data)
        self.live_update_timer = QTimer(self)
        self.live_update_timer.timeout.connect(self.update_live_values)
        self.live_update_timer.setInterval(100)  # Update every 100ms
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Directory selection
        dir_frame = QFrame()
        dir_frame.setStyleSheet("background-color: white; border-radius: 4px; padding: 10px;")
        dir_layout = QVBoxLayout(dir_frame)
        dir_label = QLabel("Select Directory:")
        dir_label.setStyleSheet("font-weight: bold;")
        self.dir_combo = QComboBox()
        self.dir_combo.currentIndexChanged.connect(self.directory_changed)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_combo)
        layout.addWidget(dir_frame)

        # Variables list
        vars_list_label = QLabel("Select Variables to Record:")
        vars_list_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(vars_list_label)
        self.var_list = QListWidget()
        self.var_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #dcdcdc;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 5px;
            }
        """)
        self.var_list.itemChanged.connect(self.on_variable_checked)
        layout.addWidget(self.var_list)

        # Live Values table
        live_label = QLabel("Live Values:")
        live_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(live_label)
        self.live_table = QTableWidget()
        self.live_table.setAlternatingRowColors(True)
        layout.addWidget(self.live_table)

        # Recording controls in a frame
        controls_frame = QFrame()
        controls_frame.setStyleSheet("background-color: white; border-radius: 4px; padding: 10px;")
        controls_layout = QHBoxLayout(controls_frame)
        
        # Recording options
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 10000)
        self.interval_spin.setValue(100)
        self.records_spin = QSpinBox()
        self.records_spin.setRange(1, 10000)
        self.records_spin.setValue(5)
        
        interval_label = QLabel("Interval (ms):")
        records_label = QLabel("Number of Records:")
        
        controls_layout.addWidget(interval_label)
        controls_layout.addWidget(self.interval_spin)
        controls_layout.addSpacing(20)
        controls_layout.addWidget(records_label)
        controls_layout.addWidget(self.records_spin)
        controls_layout.addStretch()
        
        # Record control buttons
        self.start_button = QPushButton("Start Record")
        self.start_button.clicked.connect(self.start_recording)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        
        self.stop_button = QPushButton("Stop Record")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
        """)
        
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        layout.addWidget(controls_frame)

        # Data table
        data_label = QLabel("Recorded Data:")
        data_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(data_label)
        self.data_table = QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        layout.addWidget(self.data_table)

        # Save controls
        save_controls = QHBoxLayout()
        self.auto_save_checkbox = QCheckBox("Auto-save to Records directory")
        self.auto_save_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 10pt;
                color: #2c3e50;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #bdc3c7;
                background: white;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #27ae60;
                background: #2ecc71;
                border-radius: 3px;
            }
        """)
        save_controls.addWidget(self.auto_save_checkbox)
        
        self.save_button = QPushButton("Save CSV")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
            }
            QPushButton:hover {
                background-color: #1abc9c;
            }
        """)
        self.save_button.clicked.connect(self.save_csv)
        save_controls.addWidget(self.save_button)
        layout.addLayout(save_controls)

    def directory_changed(self):
        """When directory selection changes, update the variable list."""
        self.var_list.clear()
        index = self.dir_combo.currentIndex()
        if index < 0 or not self.client:
            return
            
        try:
            node_id = self.dir_combo.itemData(index)
            node = self.client.get_node(node_id)
            children = node.get_children()
            
            # Get the current directory path
            current_dir = self.dir_combo.currentText()
            
            for child in children:
                try:
                    if child.get_node_class() == ua.NodeClass.Variable:
                        item = QListWidgetItem()
                        display_name = child.get_display_name().Text
                        # Create full path by combining directory path and variable name
                        full_path = f"{current_dir}/{display_name}"
                        item.setText(full_path)
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(Qt.Unchecked)
                        item.setData(Qt.UserRole, child.nodeid.to_string())
                        
                        # Try to get initial value and type
                        try:
                            value = child.get_value()
                            value_type = type(value).__name__
                            item.setToolTip(f"Current Value: {value}\nType: {value_type}")
                        except Exception:
                            item.setToolTip("Could not read initial value")
                            
                        self.var_list.addItem(item)
                except Exception as e:
                    print(f"Error processing variable {child.nodeid}: {str(e)}")
                    
            # Start live updates if there are any checked items
            any_checked = False
            for i in range(self.var_list.count()):
                if self.var_list.item(i).checkState() == Qt.Checked:
                    any_checked = True
                    break
            
            if any_checked:
                self.start_live_updates()
            else:
                self.stop_live_updates()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update variable list: {str(e)}")

    def start_recording(self):
        """Starts recording data from selected OPC UA variables."""
        # First check if any variables are selected
        self.selected_vars = {}
        for i in range(self.var_list.count()):
            item = self.var_list.item(i)
            if item.checkState():
                self.selected_vars[item.text()] = item.data(Qt.UserRole)
        
        if not self.selected_vars:
            QMessageBox.warning(self, "Warning", "Please select at least one variable to record.")
            return

        # Reset recording state
        self.record_count = 0
        self.record_data_list = []
        
        # Setup data table headers
        headers = ["timestamp"] + list(self.selected_vars.keys())
        self.data_table.setColumnCount(len(headers))
        self.data_table.setHorizontalHeaderLabels(headers)
        
        # Setup live values table
        self.setup_live_table()

        # Start the timer for recording
        interval_ms = self.interval_spin.value()
        self.record_timer.start(interval_ms)
        QMessageBox.information(self, "Recording", "Recording started.")

    def record_data(self):
        """Records selected variables' values and updates the live table."""
        if self.record_count >= self.records_spin.value():
            self.stop_recording()
            return

        current_time = datetime.now()
        row = {"timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
        
        for label, node_id in self.selected_vars.items():
            try:
                node = self.client.get_node(node_id)
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

    def stop_recording(self):
        """Stops the recording process."""
        self.record_timer.stop()
        
        # Auto-save if checkbox is checked and we have data
        if self.auto_save_checkbox.isChecked() and self.record_data_list:
            self.auto_save_recording()
        
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

    def auto_save_recording(self):
        """Automatically saves the recording to the Records directory."""
        try:
            records_dir = os.path.join("Records", self.name)
            if not os.path.exists(records_dir):
                os.makedirs(records_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"record_{timestamp}.csv"
            file_path = os.path.join(records_dir, filename)
            
            with open(file_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.record_data_list[0].keys())
                writer.writeheader()
                writer.writerows(self.record_data_list)
            print(f"Auto-saved recording to: {file_path}")
            
        except Exception as e:
            print(f"Error auto-saving recording: {str(e)}")
            QMessageBox.warning(self, "Auto-save Warning", 
                              f"Could not auto-save recording: {str(e)}")

    def on_variable_checked(self, item):
        """Handle when a variable checkbox is checked/unchecked."""
        var_name = item.text()
        node_id = item.data(Qt.UserRole)
        
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
        self.live_table.setColumnCount(7)  # Added one column for update checkbox
        self.live_table.setHorizontalHeaderLabels([
            "Real-time", "Variable", "Current Value", "Data Type", "Node ID", 
            "Access Level", "Description"
        ])
        
        # Store checkboxes in a dictionary
        self.live_update_checkboxes = {}
        
        for i, (var_name, node_id) in enumerate(self.selected_vars.items()):
            # Create and configure checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(True)  # Default to checked
            self.live_update_checkboxes[var_name] = checkbox
            # Create checkbox cell widget
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_widget.setLayout(checkbox_layout)
            
            self.live_table.setCellWidget(i, 0, checkbox_widget)
            self.live_table.setItem(i, 1, QTableWidgetItem(var_name))
            self.live_table.setItem(i, 2, QTableWidgetItem("Waiting..."))
            self.live_table.setItem(i, 3, QTableWidgetItem(""))
            self.live_table.setItem(i, 4, QTableWidgetItem(node_id))
            self.live_table.setItem(i, 5, QTableWidgetItem(""))
            self.live_table.setItem(i, 6, QTableWidgetItem(""))
        
        # Adjust column widths
        self.live_table.setColumnWidth(0, 70)  # Checkbox column
        self.live_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def start_live_updates(self):
        """Start live updates for selected variables."""
        if self.client:
            self.live_update_timer.start()
            print("Started live updates")

    def stop_live_updates(self):
        """Stop live updates."""
        self.live_update_timer.stop()
        print("Stopped live updates")

    def update_live_values(self):
        """Update the live values table with current values."""
        if not self.client:
            return
            
        for i, (var_name, node_id) in enumerate(self.selected_vars.items()):
            # Skip update if checkbox is unchecked
            checkbox = self.live_update_checkboxes.get(var_name)
            if not checkbox or not checkbox.isChecked():
                continue
                
            try:
                node = self.client.get_node(node_id)
                value = node.get_value()
                self.live_table.setItem(i, 2, QTableWidgetItem(str(value)))
                self.live_table.setItem(i, 3, QTableWidgetItem(type(value).__name__))
                
                # Get access level
                try:
                    access_level = node.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                    access_str = []
                    if access_level & ua.AccessLevel.CurrentRead:
                        access_str.append("Read")
                    if access_level & ua.AccessLevel.CurrentWrite:
                        access_str.append("Write")
                    self.live_table.setItem(i, 5, QTableWidgetItem(" & ".join(access_str)))
                except Exception:
                    self.live_table.setItem(i, 5, QTableWidgetItem("Unknown"))
                
                # Get description
                try:
                    desc = node.get_description().Text
                    self.live_table.setItem(i, 6, QTableWidgetItem(desc if desc else "No description"))
                except Exception:
                    self.live_table.setItem(i, 6, QTableWidgetItem("No description"))
                    
            except Exception as e:
                if checkbox.isChecked():  # Only update error message if checkbox is checked
                    self.live_table.setItem(i, 2, QTableWidgetItem(f"Error: {str(e)}"))
                    self.live_table.setItem(i, 3, QTableWidgetItem("Error"))
                    self.live_table.setItem(i, 5, QTableWidgetItem("Unknown"))
                    self.live_table.setItem(i, 6, QTableWidgetItem("Error"))

    def update_directory_list(self, directories):
        """Update the directory combo box with new directories."""
        self.dir_combo.clear()
        for path, node_id in directories.items():
            self.dir_combo.addItem(path, node_id)

class OPCUARecorder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Variable Recorder")
        self.client = None  # Client for browsing and recording
        self.browsed_variables = {}
        self.browsed_directories = {}
        self.init_ui()

    def init_ui(self):
        # Set window style and size
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QLabel {
                font-size: 11pt;
                color: #2c3e50;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11pt;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2574a9;
            }
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
                background: white;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                padding: 8px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom-color: white;
            }
            QTabBar::tab:hover {
                background: #f5f5f5;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Top bar with connection status and server URL
        top_layout = QHBoxLayout()
        top_layout.setSpacing(20)
        
        # Connection status LED in a frame
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel)
        status_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_led = QLabel()
        self.status_led.setFixedSize(16, 16)
        self.status_led.setStyleSheet(
            "QLabel { background-color: #e74c3c; border-radius: 8px; }"
        )
        status_label = QLabel("Server Status:")
        status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_led)
        top_layout.addWidget(status_frame)
        
        # Server URL selection in a frame
        url_frame = QFrame()
        url_frame.setFrameStyle(QFrame.StyledPanel)
        url_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        url_layout = QHBoxLayout(url_frame)
        url_layout.setContentsMargins(10, 5, 10, 5)
        url_label = QLabel("OPC UA Server URL:")
        url_label.setStyleSheet("font-weight: bold;")
        self.url_combo = QComboBox()
        self.url_combo.setEditable(True)
        self.url_combo.addItems([
            "opc.tcp://localhost:4840",
            "opc.tcp://192.168.101.10:4840"
        ])
        self.url_combo.setCurrentText("opc.tcp://localhost:4840")
        self.url_combo.setMinimumWidth(300)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_combo)
        top_layout.addWidget(url_frame, 1)
        
        main_layout.addLayout(top_layout)

        # Connect and Browse button
        self.connect_button = QPushButton("Connect and Browse")
        self.connect_button.clicked.connect(self.connect_and_browse)
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        main_layout.addWidget(self.connect_button)

        # Create main horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #bdc3c7;
                width: 2px;
            }
        """)

        # Left side - Tree view
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tree_frame = QFrame()
        tree_layout = QVBoxLayout(tree_frame)
        tree_label = QLabel("OPC UA Address Space")
        tree_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        tree_layout.addWidget(tree_label)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("")
        # Enable horizontal scrolling
        self.tree_widget.setHorizontalScrollMode(QTreeWidget.ScrollPerPixel)
        self.tree_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Allow items to expand horizontally
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tree_layout.addWidget(self.tree_widget)
        left_layout.addWidget(tree_frame)

        # Add left widget to main splitter
        main_splitter.addWidget(left_widget)

        # Right side - Tab widget for scenarios
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_scenario_tab)
        
        # Add "+" tab for creating new scenarios
        plus_tab = QWidget()
        plus_layout = QVBoxLayout(plus_tab)
        plus_label = QLabel("Click to add a new recording scenario")
        plus_label.setAlignment(Qt.AlignCenter)
        plus_layout.addWidget(plus_label)
        self.tab_widget.addTab(plus_tab, "+")
        self.tab_widget.tabBarClicked.connect(self.handle_tab_click)
        
        # Add right widget to main splitter
        main_splitter.addWidget(self.tab_widget)

        # Set the initial sizes of the splitter (30-70 split)
        main_splitter.setSizes([300, 700])
        
        # Add the main splitter to the layout
        main_layout.addWidget(main_splitter)

        # Create initial scenario
        self.add_new_scenario("Scenario 1")

    def handle_tab_click(self, index):
        """Handle tab clicks, especially the '+' tab."""
        if index == self.tab_widget.count() - 1:  # If '+' tab is clicked
            name, ok = QInputDialog.getText(self, "New Recording Scenario", 
                                         "Enter name for new scenario:")
            if ok and name:
                self.add_new_scenario(name)
            # Switch back to the previous tab or the new tab
            self.tab_widget.setCurrentIndex(max(0, self.tab_widget.count() - 2))

    def add_new_scenario(self, name):
        """Add a new recording scenario tab."""
        # Create new scenario
        scenario = RecordingScenario(self, name, self.client)
        
        # Insert the new tab before the '+' tab
        index = self.tab_widget.count() - 1
        self.tab_widget.insertTab(index, scenario, name)
        self.tab_widget.setCurrentIndex(index)
        
        # If we have browsed variables and directories, update the new scenario
        if self.browsed_variables:
            scenario.update_directory_list(self.browsed_directories)

    def close_scenario_tab(self, index):
        """Close a scenario tab."""
        if index != self.tab_widget.count() - 1:  # Don't close the '+' tab
            # Get the widget and check if it's recording
            widget = self.tab_widget.widget(index)
            if isinstance(widget, RecordingScenario) and widget.record_timer.isActive():
                reply = QMessageBox.question(self, "Close Scenario", 
                    "This scenario is currently recording. Are you sure you want to close it?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    return
                widget.stop_recording()
            
            self.tab_widget.removeTab(index)

    def connect_and_browse(self):
        """Connects to the OPC UA server and browses the address space."""
        # Disconnect existing client if any
        self.disconnect_client()
        
        # Clear existing items
        self.tree_widget.clear()
        self.browsed_variables = {}
        self.browsed_directories = {}
        
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
            
            # Browse from root node
            self.browse_nodes(root, root_item)
            
            # Update all existing scenarios with the new client and directories
            for i in range(self.tab_widget.count() - 1):  # Exclude '+' tab
                scenario = self.tab_widget.widget(i)
                if isinstance(scenario, RecordingScenario):
                    scenario.client = self.client
                    scenario.update_directory_list(self.browsed_directories)
            
            QMessageBox.information(self, "Success", "Connected to OPC UA server successfully!")
            
        except Exception as e:
            error_msg = f"Connection Error: {str(e)}\nType: {type(e)}"
            print(error_msg)
            QMessageBox.critical(self, "Connection Error", error_msg)
            self.update_connection_status(False)
            self.disconnect_client()

    def browse_nodes(self, node, parent_item):
        """Recursively browse nodes and add them to the tree."""
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
                    
                    # Build the full path for this node
                    path_parts = []
                    temp_item = child_item
                    while temp_item is not None:
                        path_parts.insert(0, temp_item.text(0))
                        temp_item = temp_item.parent()
                    full_path = '/'.join(path_parts)
                    
                    # If we're at or below PLC level, show all variables and directories
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
                                
                                # Add to variables dict
                                self.browsed_variables[browse_name] = child_id
                        except Exception as ve:
                            print(f"Error reading value for {browse_name}: {ve}")
                        
                        # Add to directories if it has children
                        try:
                            if len(child.get_children()) > 0:
                                self.browsed_directories[full_path] = child_id
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

    def update_connection_status(self, connected=False):
        """Update the connection status LED."""
        if connected:
            self.status_led.setStyleSheet(
                "QLabel { background-color: #27ae60; border-radius: 8px; }"
            )
        else:
            self.status_led.setStyleSheet(
                "QLabel { background-color: #e74c3c; border-radius: 8px; }"
            )

    def disconnect_client(self):
        """Safely disconnects the OPC UA client."""
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            finally:
                self.client = None
                self.update_connection_status(False)

    def closeEvent(self, event):
        """Ensures all clients are disconnected when the application closes."""
        # Stop all active recordings
        for i in range(self.tab_widget.count() - 1):  # Exclude '+' tab
            scenario = self.tab_widget.widget(i)
            if isinstance(scenario, RecordingScenario) and scenario.record_timer.isActive():
                scenario.stop_recording()
        
        self.disconnect_client()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OPCUARecorder()
    window.show()
    sys.exit(app.exec_())