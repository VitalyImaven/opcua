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
        
        # Set the application-wide stylesheet for dialogs
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QMessageBox, QInputDialog {
                    background-color: #333333;
                }
                QMessageBox QLabel, QInputDialog QLabel {
                    color: #f0f0f0;
                }
                QMessageBox QPushButton, QInputDialog QPushButton {
                    background-color: #4a4a4a;
                    color: #f0f0f0;
                    border: 1px solid #5a5a5a;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
                    background-color: #5a5a5a;
                }
                QInputDialog QLineEdit {
                    background-color: #333333;
                    color: #f0f0f0;
                    border: 1px solid #4a4a4a;
                    padding: 5px;
                }
                QInputDialog QLineEdit:focus {
                    border: 1px solid #5a5a5a;
                }
                QFileDialog {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                }
                QFileDialog QLabel {
                    color: #e0e0e0;
                }
                QFileDialog QLineEdit {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                    border: 1px solid #3d3d3d;
                    padding: 5px;
                }
                QFileDialog QTreeView, QFileDialog QListView {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                }
            """)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Directory selection
        dir_frame = QFrame()
        dir_frame.setStyleSheet("""
            QFrame {
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        dir_layout = QVBoxLayout(dir_frame)
        dir_label = QLabel("Select Directory:")
        dir_label.setStyleSheet("font-weight: bold; color: #e0e0e0;")
        self.dir_combo = QComboBox()
        self.dir_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
                background: #2d2d2d;
                color: #e0e0e0;
            }
            QComboBox:hover {
                border: 1px solid #4d4d4d;
                background: #353535;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                selection-background-color: #404040;
                selection-color: #e0e0e0;
                color: #e0e0e0;
            }
            QComboBox QLineEdit {
                background: #2d2d2d;
                color: #e0e0e0;
                border: none;
                padding: 0px;
            }
        """)
        self.dir_combo.currentIndexChanged.connect(self.directory_changed)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_combo)
        layout.addWidget(dir_frame)

        # Variables list
        vars_list_label = QLabel("Select Variables to Record:")
        vars_list_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #e0e0e0;")
        layout.addWidget(vars_list_label)
        self.var_list = QListWidget()
        self.var_list.setStyleSheet("""
            QListWidget {
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:hover {
                background: #353535;
            }
            QListWidget::item:selected {
                background: #404040;
                color: #ffffff;
            }
        """)
        self.var_list.itemChanged.connect(self.on_variable_checked)
        layout.addWidget(self.var_list)

        # Live Values table
        live_label = QLabel("Live Values:")
        live_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #e0e0e0;")
        layout.addWidget(live_label)
        self.live_table = QTableWidget()
        self.live_table.setStyleSheet("""
            QTableWidget {
                background-color: #333333;
                border: 1px solid #4a4a4a;
                border-radius: 8px;
                color: #f0f0f0;
                gridline-color: #4a4a4a;
                alternate-background-color: #383838;
            }
            QTableWidget::item {
                background-color: transparent;
                color: #f0f0f0;
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #505050;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #f0f0f0;
                border: none;
                border-right: 1px solid #4a4a4a;
                border-bottom: 1px solid #4a4a4a;
                padding: 4px;
            }
            QTableCornerButton::section {
                background-color: #333333;
                border: none;
            }
            QHeaderView {
                background-color: #333333;
            }
            QTableWidget QWidget {
                background-color: transparent;
            }
        """)
        self.live_table.setAlternatingRowColors(True)
        layout.addWidget(self.live_table)

        # Recording controls in a frame
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 10px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QSpinBox {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
                background: #2d2d2d;
                color: #e0e0e0;
                selection-background-color: #404040;
                selection-color: #ffffff;
            }
            QSpinBox:hover {
                border: 1px solid #4d4d4d;
                background: #353535;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: #3d3d3d;
                border: none;
                border-radius: 2px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #4d4d4d;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #e0e0e0;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #e0e0e0;
            }
        """)
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
                background-color: #2d6da4;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d7db4;
            }
            QPushButton:pressed {
                background-color: #1d5d94;
            }
        """)
        
        self.stop_button = QPushButton("Stop Record")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #a43d3d;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b44d4d;
            }
            QPushButton:pressed {
                background-color: #942d2d;
            }
        """)
        
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        layout.addWidget(controls_frame)

        # Data table
        data_label = QLabel("Recorded Data:")
        data_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #e0e0e0;")
        layout.addWidget(data_label)
        self.data_table = QTableWidget()
        self.data_table.setStyleSheet("""
            QTableWidget {
                background: #333333;
                border: 1px solid #4a4a4a;
                border-radius: 8px;
                color: #f0f0f0;
                gridline-color: #4a4a4a;
                alternate-background-color: #404040;
            }
            QTableWidget::item {
                color: #f0f0f0;
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background: #505050;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #333333;
                color: #f0f0f0;
                border: none;
                border-right: 1px solid #4a4a4a;
                border-bottom: 1px solid #4a4a4a;
                padding: 4px;
            }
            QTableCornerButton::section {
                background: #333333;
                border: none;
            }
            QHeaderView {
                background: #333333;
            }
        """)
        self.data_table.setAlternatingRowColors(True)
        layout.addWidget(self.data_table)

        # Save controls
        save_controls = QHBoxLayout()
        self.auto_save_checkbox = QCheckBox("Auto-save to Records directory")
        self.auto_save_checkbox.setChecked(True)  # Set initial state to checked
        self.auto_save_checkbox.setStyleSheet("""
            QCheckBox {
                color: #f0f0f0;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #909090;
                background: #333333;
            }
            QCheckBox::indicator:checked {
                background: #4CAF50;
                border-color: #4CAF50;
            }
            QCheckBox::indicator:hover {
                border-color: #b0b0b0;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #45a049;
                border-color: #45a049;
            }
        """)
        save_controls.addWidget(self.auto_save_checkbox)
        
        self.save_button = QPushButton("Save CSV")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #a36f0d !important;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #a36f0d !important;
            }
            QPushButton:pressed {
                background-color: #a36f0d !important;
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
                
                # Handle structured data for recording
                if isinstance(value, (list, tuple)) and value and hasattr(value[0], '_fields_'):
                    # For array of structures, create separate columns for each field
                    for i, item in enumerate(value):
                        self._record_structure(row, item, f"{label}[{i}]")
                elif hasattr(value, '_fields_'):
                    # For single structure, create separate columns for each field
                    self._record_structure(row, value, label)
                else:
                    row[label] = value
                    
            except Exception as e:
                row[label] = f"Error: {e}"

        self.record_data_list.append(row)
        self.record_count += 1
        self.update_data_table()

    def _record_structure(self, row, struct, prefix):
        """Helper method to record structure fields recursively."""
        try:
            for field in struct._fields_:
                field_value = getattr(struct, field)
                if hasattr(field_value, '_fields_'):
                    # Handle nested structures
                    self._record_structure(row, field_value, f"{prefix}.{field}")
                else:
                    row[f"{prefix}.{field}"] = field_value
        except Exception as e:
            row[prefix] = f"Error recording structure: {str(e)}"

    def update_data_table(self):
        """Updates the data table with the recorded values."""
        if not self.record_data_list:
            return

        # Get all unique column headers from all records
        headers = set()
        for record in self.record_data_list:
            headers.update(record.keys())
        
        # Sort headers to group related fields together
        sorted_headers = ["timestamp"]
        remaining_headers = sorted(list(headers - {"timestamp"}))
        
        # Group fields by their base variable name
        header_groups = {}
        for header in remaining_headers:
            base_name = header.split('[')[0].split('.')[0]
            if base_name not in header_groups:
                header_groups[base_name] = []
            header_groups[base_name].append(header)
        
        # Add grouped headers to final list
        for base_name in sorted(header_groups.keys()):
            sorted_headers.extend(sorted(header_groups[base_name]))

        self.data_table.setColumnCount(len(sorted_headers))
        self.data_table.setHorizontalHeaderLabels(sorted_headers)
        self.data_table.setRowCount(len(self.record_data_list))
        
        # Set alternating row colors
        self.data_table.setAlternatingRowColors(True)
        
        # Populate table with data
        for row_idx, data_row in enumerate(self.record_data_list):
            for col_idx, header in enumerate(sorted_headers):
                value = data_row.get(header, "")
                # Format the value if it's not already a string
                if not isinstance(value, str):
                    value = self.format_value(value)
                item = QTableWidgetItem(str(value))
                item.setForeground(Qt.white)
                self.data_table.setItem(row_idx, col_idx, item)

        # Optimize column widths
        self.data_table.resizeColumnsToContents()
        # Set a maximum column width to prevent very wide columns
        for i in range(self.data_table.columnCount()):
            if self.data_table.columnWidth(i) > 300:
                self.data_table.setColumnWidth(i, 300)

    def stop_recording(self):
        """Stops the recording process."""
        self.record_timer.stop()
        
        # Auto-save if checkbox is checked and we have data
        print(f"Auto-save checkbox state: {self.auto_save_checkbox.isChecked()}")
        print(f"Record data list length: {len(self.record_data_list)}")
        
        if self.auto_save_checkbox.isChecked() and self.record_data_list:
            print("Attempting auto-save...")
            self.auto_save_recording()
        else:
            print("Auto-save conditions not met")
        
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
            print(f"Creating records directory: {records_dir}")
            
            if not os.path.exists(records_dir):
                os.makedirs(records_dir)
                print(f"Created directory: {records_dir}")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"record_{timestamp}.csv"
            file_path = os.path.join(records_dir, filename)
            print(f"Saving to file: {file_path}")
            
            with open(file_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.record_data_list[0].keys())
                writer.writeheader()
                writer.writerows(self.record_data_list)
            print(f"Successfully auto-saved recording to: {file_path}")
            
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
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #e0e0e0;
                    background: transparent;
                }
                QCheckBox::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 3px;
                    border: 1px solid #808080;
                    background-color: #2d2d2d !important;
                }
                QCheckBox::indicator:checked {
                    background-color: #b05cfa !important;
                    border-color: #b05cfa;
                }
                QCheckBox::indicator:hover {
                    border-color: #a0a0a0;
                }
                QCheckBox::indicator:checked:hover {
                    background-color: #b3b1b5 !important;
                    border-color: #b3b1b5;
                }
            """)
            self.live_update_checkboxes[var_name] = checkbox
            
            # Create checkbox cell widget with transparent background
            checkbox_widget = QWidget()
            checkbox_widget.setStyleSheet("""
                QWidget {
                    background: transparent;
                }
                QCheckBox {
                    color: #e0e0e0;
                    background: transparent;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #808080;
                    background-color: #2d2d2d !important;
                }
                QCheckBox::indicator:checked {
                    background-color: #139415 !important;
                    border-color: #139415;
                }
                QCheckBox::indicator:hover {
                    border-color: #a0a0a0;
                }
                QCheckBox::indicator:checked:hover {
                    background-color: #cc0000 !important;
                    border-color: #cc0000;
                }
            """)
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_widget.setLayout(checkbox_layout)
            
            self.live_table.setCellWidget(i, 0, checkbox_widget)
            
            # Create table items with proper styling
            for col, text in enumerate([var_name, "Waiting...", "", node_id, "", ""], start=1):
                item = QTableWidgetItem(text)
                item.setForeground(Qt.white)  # Set text color to white
                item.setBackground(Qt.transparent)  # Set transparent background
                self.live_table.setItem(i, col, item)
        
        # Set all columns to be interactively resizable
        header = self.live_table.horizontalHeader()
        for i in range(self.live_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        
        # Set initial column widths
        self.live_table.setColumnWidth(0, 70)  # Real-time checkbox
        self.live_table.setColumnWidth(1, 200)  # Variable name
        self.live_table.setColumnWidth(2, 150)  # Current Value
        self.live_table.setColumnWidth(3, 100)  # Data Type
        self.live_table.setColumnWidth(4, 200)  # Node ID
        self.live_table.setColumnWidth(5, 100)  # Access Level
        self.live_table.setColumnWidth(6, 200)  # Description

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
                
                # Format the value for display
                formatted_value = self.format_value(value)
                value_item = QTableWidgetItem(formatted_value)
                value_item.setForeground(Qt.white)
                self.live_table.setItem(i, 2, value_item)
                
                # Show detailed type information
                type_info = self.get_type_info(value)
                type_item = QTableWidgetItem(type_info)
                type_item.setForeground(Qt.white)
                self.live_table.setItem(i, 3, type_item)
                
                # Get access level
                try:
                    access_level = node.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                    access_str = []
                    if access_level & ua.AccessLevel.CurrentRead:
                        access_str.append("Read")
                    if access_level & ua.AccessLevel.CurrentWrite:
                        access_str.append("Write")
                    access_item = QTableWidgetItem(" & ".join(access_str))
                    access_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 5, access_item)
                except Exception:
                    access_item = QTableWidgetItem("Unknown")
                    access_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 5, access_item)
                
                # Get description
                try:
                    desc = node.get_description().Text
                    desc_item = QTableWidgetItem(desc if desc else "No description")
                    desc_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 6, desc_item)
                except Exception:
                    desc_item = QTableWidgetItem("No description")
                    desc_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 6, desc_item)
                    
            except Exception as e:
                if checkbox.isChecked():  # Only update error message if checkbox is checked
                    error_item = QTableWidgetItem(f"Error: {str(e)}")
                    error_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 2, error_item)
                    
                    type_item = QTableWidgetItem("Error")
                    type_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 3, type_item)
                    
                    access_item = QTableWidgetItem("Unknown")
                    access_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 5, access_item)
                    
                    desc_item = QTableWidgetItem("Error")
                    desc_item.setForeground(Qt.white)
                    self.live_table.setItem(i, 6, desc_item)

    def format_value(self, value):
        """Format a value for display, handling arrays and structures."""
        try:
            if isinstance(value, (list, tuple)):
                # Handle array of structures or simple array
                if value and hasattr(value[0], '_fields_'):  # Check if it's a structure
                    formatted_items = []
                    for idx, item in enumerate(value):
                        struct_items = []
                        for field in item._fields_:
                            field_value = getattr(item, field)
                            # Format nested structures recursively
                            if hasattr(field_value, '_fields_'):
                                nested_value = self.format_value(field_value)
                                struct_items.append(f"{field}: {nested_value}")
                            else:
                                struct_items.append(f"{field}: {field_value}")
                        formatted_items.append(f"[{idx}] {{{', '.join(struct_items)}}}")
                    return f"Array[{len(value)}]:\n" + '\n'.join(formatted_items)
                else:
                    # Format simple array with index numbers
                    formatted_items = [f"[{i}] {self.format_value(item)}" for i, item in enumerate(value)]
                    return f"Array[{len(value)}]:\n" + '\n'.join(formatted_items)
            elif hasattr(value, '_fields_'):  # Single structure
                struct_items = []
                for field in value._fields_:
                    field_value = getattr(value, field)
                    # Format nested structures recursively
                    if hasattr(field_value, '_fields_'):
                        nested_value = self.format_value(field_value)
                        struct_items.append(f"{field}: {nested_value}")
                    else:
                        struct_items.append(f"{field}: {field_value}")
                return f"{{{', '.join(struct_items)}}}"
            else:
                return str(value)
        except Exception as e:
            return f"Error formatting value: {str(e)}"

    def get_type_info(self, value):
        """Get detailed type information for a value."""
        try:
            if isinstance(value, (list, tuple)):
                if value and hasattr(value[0], '_fields_'):
                    struct_name = value[0].__class__.__name__
                    field_types = []
                    for field in value[0]._fields_:
                        field_value = getattr(value[0], field)
                        if hasattr(field_value, '_fields_'):
                            field_type = f"{field}: {field_value.__class__.__name__}"
                        else:
                            field_type = f"{field}: {type(field_value).__name__}"
                        field_types.append(field_type)
                    return f"Array[{len(value)}] of {struct_name}{{{', '.join(field_types)}}}"
                else:
                    base_type = type(value[0]).__name__ if value else "Empty"
                    return f"Array[{len(value)}] of {base_type}"
            elif hasattr(value, '_fields_'):
                struct_name = value.__class__.__name__
                field_types = []
                for field in value._fields_:
                    field_value = getattr(value, field)
                    if hasattr(field_value, '_fields_'):
                        field_type = f"{field}: {field_value.__class__.__name__}"
                    else:
                        field_type = f"{field}: {type(field_value).__name__}"
                    field_types.append(field_type)
                return f"{struct_name}{{{', '.join(field_types)}}}"
            else:
                return type(value).__name__
        except Exception as e:
            return f"Error getting type info: {str(e)}"

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
                background-color: #2b2b2b;
            }
            QLabel {
                font-size: 11pt;
                color: #f0f0f0;
            }
            /* Message Box and Input Dialog styling */
            QMessageBox, QInputDialog {
                background-color: #333333;
                color: #f0f0f0;
            }
            QMessageBox QLabel, QInputDialog QLabel {
                color: #f0f0f0;
            }
            QMessageBox QPushButton, QInputDialog QPushButton {
                background-color: #4a4a4a;
                color: #f0f0f0;
                border: 1px solid #5a5a5a;
                padding: 5px 15px;
                border-radius: 3px;
                min-width: 65px;
            }
            QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
                background-color: #5a5a5a;
            }
            QInputDialog QLineEdit {
                background-color: #333333;
                color: #f0f0f0;
                border: 1px solid #4a4a4a;
                padding: 5px;
                border-radius: 3px;
            }
            QInputDialog QLineEdit:focus {
                border: 1px solid #5a5a5a;
            }
            /* Rest of the existing styles */
            QPushButton {
                background-color: #404040;
                color: #f0f0f0;
                border: 1px solid #4a4a4a;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11pt;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #5a5a5a;
            }
            QTabWidget::pane {
                border: 1px solid #4a4a4a;
                background: #333333;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #333333;
                border: 1px solid #4a4a4a;
                padding: 8px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #f0f0f0;
            }
            QTabBar::tab:selected {
                background: #4a4a4a;
                border-bottom-color: #5a5a5a;
            }
            QTabBar::tab:hover {
                background: #404040;
            }
            QListWidget, QTableWidget, QTreeWidget {
                background: #333333;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                color: #f0f0f0;
            }
            QListWidget::item:hover, QTreeWidget::item:hover {
                background: #404040;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background: #505050;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #333333;
                color: #f0f0f0;
                border: none;
                border-right: 1px solid #4a4a4a;
                border-bottom: 1px solid #4a4a4a;
                padding: 4px;
            }
            QTableWidget {
                gridline-color: #4a4a4a;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QComboBox {
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 4px;
                background: #333333;
                color: #f0f0f0;
            }
            QComboBox:hover {
                border: 1px solid #5a5a5a;
                background: #404040;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #f0f0f0;
                margin-right: 5px;
            }
            QSpinBox {
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 4px;
                background: #333333;
                color: #f0f0f0;
            }
            QSpinBox:hover {
                border: 1px solid #5a5a5a;
                background: #404040;
            }
            QFrame {
                background: #333333;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
            }
            QSplitter::handle {
                background: #4a4a4a;
                width: 2px;
            }
            QScrollBar:vertical {
                border: none;
                background: #333333;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #4a4a4a;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5a5a5a;
            }
            QScrollBar:horizontal {
                border: none;
                background: #333333;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #4a4a4a;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #5a5a5a;
            }
            QCheckBox {
                color: #f0f0f0;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid #909090;
                background: #333333;
            }
            QCheckBox::indicator:checked {
                background: #4CAF50;
                border-color: #4CAF50;

            }
            QCheckBox::indicator:hover {
                border-color: #b0b0b0;
            }
            QCheckBox::indicator:checked:hover {
                background: #45a049;
                border-color: #45a049;
            }
        """)

        # Create main horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        # Left side widget - Address Space and Connection Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(10, 10, 10, 10)

        # Connection controls at the top
        connection_frame = QFrame()
        connection_layout = QVBoxLayout(connection_frame)
        connection_layout.setSpacing(10)

        # Server status
        status_layout = QHBoxLayout()
        self.status_led = QLabel()
        self.status_led.setFixedSize(16, 16)
        self.status_led.setStyleSheet("""
            QLabel {
                background-color: #e74c3c;
                border-radius: 8px;
                border: 2px solid #c0392b;
            }
        """)
        status_label = QLabel("Server Status:")
        status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_led)
        status_layout.addStretch()
        connection_layout.addLayout(status_layout)

        # Server URL
        url_label = QLabel("OPC UA Server URL:")
        url_label.setStyleSheet("font-weight: bold;")
        connection_layout.addWidget(url_label)
        self.url_combo = QComboBox()
        self.url_combo.setEditable(True)
        self.url_combo.addItems([
            "opc.tcp://192.168.101.10:4840",
            "opc.tcp://localhost:4840"
        ])
        self.url_combo.setCurrentText("opc.tcp://192.168.101.10:4840")
        self.url_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
                background: #2d2d2d;
                color: #f0f0f0;
            }
            QComboBox:hover {
                border: 1px solid #4d4d4d;
                background: #353535;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #f0f0f0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #f0f0f0;
            }
            QComboBox QAbstractItemView::item {
                background: #2d2d2d;
                color: #f0f0f0;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #404040;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #353535;
                color: #ffffff;
            }
            QComboBox QLineEdit {
                background: #2d2d2d;
                color: #f0f0f0;
                border: none;
                padding: 0px;
            }
        """)
        connection_layout.addWidget(self.url_combo)

        # Connect button
        self.connect_button = QPushButton("Connect and Browse")
        self.connect_button.clicked.connect(self.connect_and_browse)
        connection_layout.addWidget(self.connect_button)
        
        left_layout.addWidget(connection_frame)

        # Address space tree
        tree_frame = QFrame()
        tree_layout = QVBoxLayout(tree_frame)
        tree_label = QLabel("OPC UA Address Space")
        tree_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        tree_layout.addWidget(tree_label)
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("")
        self.tree_widget.setHorizontalScrollMode(QTreeWidget.ScrollPerPixel)
        self.tree_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #f0f0f0;
            }
            QTreeWidget::item {
                color: #f0f0f0;
                padding: 4px;
                background-color: transparent;
            }
            QTreeWidget::item:hover {
                background-color: #353535;
            }
            QTreeWidget::item:selected {
                background-color: #404040;
                color: #ffffff;
            }
            QTreeWidget::branch {
                background-color: transparent;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                border-style: solid;
                border-width: 3px;
                border-color: transparent transparent transparent #ffffff;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                border-image: none;
                border-style: solid;
                border-width: 3px;
                border-color: #ffffff transparent transparent transparent;
            }
        """)
        tree_layout.addWidget(self.tree_widget)
        
        left_layout.addWidget(tree_frame)

        # Right side widget - Recording Scenarios
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(15)
        right_layout.setContentsMargins(10, 10, 10, 10)

        # Tab widget for scenarios
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
        
        right_layout.addWidget(self.tab_widget)

        # Add widgets to main splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)

        # Set the initial sizes of the splitter (30-70 split)
        main_splitter.setSizes([300, 900])

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