import sys
import csv
import os
from datetime import datetime
from opcua import Client, ua
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QTreeWidget, QTreeWidgetItem, QComboBox, QListWidget,
    QListWidgetItem, QSpinBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QFrame, QSplitter, QHeaderView, QCheckBox, QTabWidget, QInputDialog, QMenu, QAction
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QColor, QFont
from src.perf_benchmark import PerformanceBenchmark

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
                    background-color: #16213e;
                }
                QMessageBox QLabel, QInputDialog QLabel {
                    color: #e0e0e0;
                }
                QMessageBox QPushButton, QInputDialog QPushButton {
                    background-color: #0f3460;
                    color: #e0e0e0;
                    border: 1px solid #2a3a5a;
                    padding: 6px 18px;
                    border-radius: 6px;
                }
                QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
                    background-color: #1a5a8a;
                }
                QInputDialog QLineEdit {
                    background-color: #16213e;
                    color: #e0e0e0;
                    border: 1px solid #2a3a5a;
                    padding: 6px;
                    border-radius: 6px;
                }
                QInputDialog QLineEdit:focus {
                    border: 1px solid #e94560;
                }
                QFileDialog {
                    background-color: #1a1a2e;
                    color: #e0e0e0;
                }
                QFileDialog QLabel {
                    color: #e0e0e0;
                }
                QFileDialog QLineEdit {
                    background-color: #16213e;
                    color: #e0e0e0;
                    border: 1px solid #2a3a5a;
                    padding: 6px;
                }
                QFileDialog QTreeView, QFileDialog QListView {
                    background-color: #16213e;
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
                background: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        dir_layout = QVBoxLayout(dir_frame)
        dir_label = QLabel("Select Directory:")
        dir_label.setStyleSheet("font-weight: bold; color: #e0e0e0;")
        self.dir_combo = QComboBox()
        self.dir_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #2a3a5a;
                border-radius: 6px;
                padding: 6px;
                background: #0f2940;
                color: #e0e0e0;
            }
            QComboBox:hover {
                border: 1px solid #3a5a8a;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #8899aa;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #16213e;
                border: 1px solid #2a3a5a;
                selection-background-color: #0f3460;
                selection-color: #e0e0e0;
                color: #e0e0e0;
            }
            QComboBox QLineEdit {
                background: #0f2940;
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
                background: #0f2940;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                color: #e0e0e0;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:hover {
                background: #1a3050;
            }
            QListWidget::item:selected {
                background: #0f3460;
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
                background-color: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                color: #f0f0f0;
                gridline-color: #2a3a5a;
                alternate-background-color: #1a2a45;
            }
            QTableWidget::item {
                background-color: transparent;
                color: #f0f0f0;
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #0f3460;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0f2940;
                color: #8899aa;
                border: none;
                border-right: 1px solid #2a3a5a;
                border-bottom: 1px solid #2a3a5a;
                padding: 4px;
            }
            QTableCornerButton::section {
                background-color: #0f2940;
                border: none;
            }
            QHeaderView {
                background-color: #0f2940;
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
                background: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QSpinBox {
                border: 1px solid #2a3a5a;
                border-radius: 6px;
                padding: 4px;
                background: #0f2940;
                color: #e0e0e0;
                selection-background-color: #0f3460;
                selection-color: #ffffff;
            }
            QSpinBox:hover {
                border: 1px solid #3a5a8a;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: #2a3a5a;
                border: none;
                border-radius: 2px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #3a5a8a;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #8899aa;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #8899aa;
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
                background-color: #0f3460;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #e94560;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #c73650;
            }
        """)
        
        self.stop_button = QPushButton("Stop Record")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #ff6b81;
            }
            QPushButton:pressed {
                background-color: #c73650;
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
                background: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                color: #f0f0f0;
                gridline-color: #2a3a5a;
                alternate-background-color: #1a2a45;
            }
            QTableWidget::item {
                color: #f0f0f0;
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background: #0f3460;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #0f2940;
                color: #8899aa;
                border: none;
                border-right: 1px solid #2a3a5a;
                border-bottom: 1px solid #2a3a5a;
                padding: 4px;
            }
            QTableCornerButton::section {
                background: #0f2940;
                border: none;
            }
            QHeaderView {
                background: #0f2940;
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
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #3a5a8a;
                background: #0f2940;
            }
            QCheckBox::indicator:checked {
                background: #e94560;
                border-color: #e94560;
            }
            QCheckBox::indicator:hover {
                border-color: #5a8aba;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #ff6680;
                border-color: #ff6680;
            }
        """)
        save_controls.addWidget(self.auto_save_checkbox)
        
        self.save_button = QPushButton("Save CSV")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #0f3460;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #e94560;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #c73650;
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
                    border: 2px solid #3a5a8a;
                    background-color: #0f2940 !important;
                }
                QCheckBox::indicator:checked {
                    background-color: #e94560 !important;
                    border-color: #e94560;
                }
                QCheckBox::indicator:hover {
                    border-color: #5a8aba;
                }
                QCheckBox::indicator:checked:hover {
                    background-color: #ff6680 !important;
                    border-color: #ff6680;
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
                    border: 2px solid #3a5a8a;
                    background-color: #0f2940 !important;
                }
                QCheckBox::indicator:checked {
                    background-color: #00e676 !important;
                    border-color: #00e676;
                }
                QCheckBox::indicator:hover {
                    border-color: #5a8aba;
                }
                QCheckBox::indicator:checked:hover {
                    background-color: #e94560 !important;
                    border-color: #e94560;
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
            * { font-family: 'Segoe UI', sans-serif; }
            QMainWindow { background-color: #1a1a2e; }
            QLabel { font-size: 10pt; color: #e0e0e0; }
            QMessageBox, QInputDialog { background-color: #16213e; color: #e0e0e0; }
            QMessageBox QLabel, QInputDialog QLabel { color: #e0e0e0; }
            QMessageBox QPushButton, QInputDialog QPushButton {
                background-color: #0f3460; color: #e0e0e0;
                border: 1px solid #1a4a7a; padding: 6px 18px;
                border-radius: 6px; min-width: 70px;
            }
            QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
                background-color: #1a5a8a;
            }
            QInputDialog QLineEdit {
                background-color: #16213e; color: #e0e0e0;
                border: 1px solid #2a4a6a; padding: 6px; border-radius: 6px;
            }
            QPushButton {
                background-color: #0f3460; color: #e0e0e0;
                border: none; padding: 8px 16px;
                border-radius: 6px; font-size: 10pt;
            }
            QPushButton:hover { background-color: #1a5a8a; }
            QPushButton:pressed { background-color: #0a2640; }
            QTabWidget::pane {
                border: 1px solid #2a3a5a;
                background: #16213e;
                border-radius: 8px;
                top: -1px;
            }
            QTabBar::tab {
                background: #0f2940;
                border: 1px solid #2a3a5a;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                color: #8899aa;
                font-size: 10pt;
            }
            QTabBar::tab:selected {
                background: #16213e;
                color: #e94560;
                border-bottom-color: #16213e;
                font-weight: bold;
            }
            QTabBar::tab:hover { background: #1a3050; color: #e0e0e0; }
            QListWidget, QTableWidget, QTreeWidget {
                background: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
                color: #e0e0e0;
            }
            QListWidget::item:hover, QTreeWidget::item:hover { background: #1a3050; }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background: #0f3460; color: #ffffff;
            }
            QHeaderView::section {
                background: #0f2940;
                color: #8899aa;
                border: none;
                border-right: 1px solid #2a3a5a;
                border-bottom: 1px solid #2a3a5a;
                padding: 6px 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QTableWidget { gridline-color: #2a3a5a; }
            QTableWidget::item { padding: 4px; }
            QComboBox {
                border: 1px solid #2a3a5a;
                border-radius: 6px;
                padding: 6px 8px;
                background: #16213e;
                color: #e0e0e0;
            }
            QComboBox:hover { border: 1px solid #3a5a8a; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #8899aa;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #16213e; border: 1px solid #2a3a5a;
                selection-background-color: #0f3460; color: #e0e0e0;
            }
            QSpinBox {
                border: 1px solid #2a3a5a;
                border-radius: 6px;
                padding: 4px 8px;
                background: #16213e;
                color: #e0e0e0;
            }
            QSpinBox:hover { border: 1px solid #3a5a8a; }
            QFrame {
                background: #16213e;
                border: 1px solid #2a3a5a;
                border-radius: 8px;
            }
            QSplitter::handle { background: #2a3a5a; width: 2px; }
            QScrollBar:vertical {
                border: none; background: #1a1a2e; width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #2a3a5a; min-height: 20px; border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #3a5a8a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                border: none; background: #1a1a2e; height: 8px;
            }
            QScrollBar::handle:horizontal {
                background: #2a3a5a; min-width: 20px; border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover { background: #3a5a8a; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QCheckBox { color: #e0e0e0; spacing: 6px; }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 2px solid #3a5a8a;
                background: #0f2940;
            }
            QCheckBox::indicator:checked {
                background: #e94560;
                border-color: #e94560;
            }
            QCheckBox::indicator:hover { border-color: #5a8aba; }
            QCheckBox::indicator:checked:hover {
                background: #ff6680; border-color: #ff6680;
            }
            QLineEdit {
                background: #16213e; color: #e0e0e0;
                border: 1px solid #2a3a5a; border-radius: 6px;
                padding: 6px 10px; font-size: 10pt;
            }
            QLineEdit:focus { border: 1px solid #e94560; }
        """)

        # Create main horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        # Left side widget - Address Space and Connection Controls
        left_widget = QWidget()
        left_widget.setStyleSheet("QWidget { background: transparent; border: none; }")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 4, 8)

        # Connection controls
        connection_frame = QFrame()
        connection_frame.setStyleSheet("""
            QFrame { background: #16213e; border: 1px solid #2a3a5a; border-radius: 10px; }
        """)
        connection_layout = QVBoxLayout(connection_frame)
        connection_layout.setSpacing(8)
        connection_layout.setContentsMargins(12, 12, 12, 12)

        # Status row
        status_layout = QHBoxLayout()
        self.status_led = QLabel()
        self.status_led.setFixedSize(12, 12)
        self.status_led.setStyleSheet("""
            QLabel {
                background-color: #e94560;
                border-radius: 6px;
                border: none;
            }
        """)
        status_label = QLabel("Status")
        status_label.setStyleSheet("font-weight: bold; font-size: 9pt; color: #8899aa;")
        status_layout.addWidget(self.status_led)
        status_layout.addWidget(status_label)
        status_layout.addStretch()
        connection_layout.addLayout(status_layout)

        # URL
        self.url_combo = QComboBox()
        self.url_combo.setEditable(True)
        self.url_combo.addItems([
            "opc.tcp://192.168.101.10:4840",
            "opc.tcp://localhost:4840"
        ])
        self.url_combo.setCurrentText("opc.tcp://192.168.101.10:4840")
        connection_layout.addWidget(self.url_combo)

        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e94560, stop:1 #c23152);
                color: white; border: none; padding: 10px;
                border-radius: 8px; font-size: 11pt; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff5a75, stop:1 #d24162);
            }
            QPushButton:pressed { background: #a02040; }
        """)
        self.connect_button.clicked.connect(self.connect_and_browse)
        connection_layout.addWidget(self.connect_button)
        
        left_layout.addWidget(connection_frame)

        # Tree section
        tree_frame = QFrame()
        tree_frame.setStyleSheet("""
            QFrame { background: #16213e; border: 1px solid #2a3a5a; border-radius: 10px; }
        """)
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(6)

        tree_header = QLabel("Address Space")
        tree_header.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e94560; border: none;")
        tree_layout.addWidget(tree_header)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("  Search variables...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #0f2940; color: #e0e0e0;
                border: 1px solid #2a3a5a; border-radius: 8px;
                padding: 8px 12px; font-size: 10pt;
            }
            QLineEdit:focus { border: 1px solid #e94560; }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        tree_layout.addWidget(self.search_input)

        # Action buttons
        btn_row = QHBoxLayout()
        self.add_to_bench_btn = QPushButton("+ Add to Benchmark")
        self.add_to_bench_btn.setStyleSheet("""
            QPushButton {
                background: #0f3460; color: #e0e0e0; border: 1px solid #2a4a6a;
                padding: 6px 14px; border-radius: 6px; font-size: 9pt;
            }
            QPushButton:hover { background: #1a5a8a; border-color: #3a6a9a; }
        """)
        self.add_to_bench_btn.clicked.connect(self._add_selected_to_benchmark)
        btn_row.addWidget(self.add_to_bench_btn)
        btn_row.addStretch()
        tree_layout.addLayout(btn_row)
        
        # Tree widget with checkboxes
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Type"])
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_widget.setHorizontalScrollMode(QTreeWidget.ScrollPerPixel)
        self.tree_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_widget.setAnimated(True)
        self.tree_widget.setIndentation(18)
        self.tree_widget.header().setStretchLastSection(True)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree_widget.setColumnWidth(1, 70)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._tree_context_menu)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #0f2940;
                border: 1px solid #1a3a5a;
                border-radius: 8px;
                color: #d4d4d4;
                font-family: 'Segoe UI', Consolas, sans-serif;
                font-size: 10pt;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 6px;
                border-radius: 4px;
                margin: 1px 2px;
            }
            QTreeWidget::item:hover {
                background-color: #162850;
            }
            QTreeWidget::item:selected {
                background-color: #0f3460;
                color: #ffffff;
                border: 1px solid #e94560;
                border-radius: 4px;
            }
            QTreeWidget::branch {
                background-color: transparent;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #5a7a9a;
                margin: 6px 4px;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 5px solid #e94560;
                margin: 6px 4px;
            }
            QHeaderView::section {
                background-color: #0a1f35;
                color: #5a7a9a;
                border: none;
                border-bottom: 2px solid #e94560;
                padding: 6px 10px;
                font-size: 9pt;
                font-weight: bold;
                text-transform: uppercase;
            }
        """)
        tree_layout.addWidget(self.tree_widget)
        
        left_layout.addWidget(tree_frame, 1)

        # Right side widget - Recording Scenarios
        right_widget = QWidget()
        right_widget.setStyleSheet("QWidget { background: transparent; border: none; }")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(4, 8, 8, 8)

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

        # Create Performance Benchmark tab (always first)
        self.benchmark_tab = PerformanceBenchmark(self, self.client)
        self.tab_widget.insertTab(0, self.benchmark_tab, "Performance")

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
        if index == 0:  # Don't close the Performance tab
            return
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
            
            self.client.connect()
            print("Successfully connected to server")
            self.update_connection_status(True)
            
            # Get root node and browse only the path Root -> Objects -> PLC
            root = self.client.get_root_node()
            root_item = QTreeWidgetItem(["Root"])
            root_item.setData(0, 1, root.nodeid.to_string())
            self.tree_widget.addTopLevelItem(root_item)
            
            # Navigate to PLC node quickly: Root -> Objects -> PLC
            try:
                objects_node = root.get_child(["0:Objects"])
                objects_item = QTreeWidgetItem(["Objects"])
                objects_item.setData(0, 1, objects_node.nodeid.to_string())
                root_item.addChild(objects_item)
                
                plc_node = None
                for child in objects_node.get_children():
                    name = child.get_display_name().Text
                    if name == "PLC":
                        plc_node = child
                        break
                
                if plc_node:
                    plc_item = QTreeWidgetItem(["PLC"])
                    plc_item.setData(0, 1, plc_node.nodeid.to_string())
                    objects_item.addChild(plc_item)
                    
                    # Browse first level under PLC (lazy - don't go deeper)
                    self._browse_one_level(plc_node, plc_item)
                    
                    plc_item.setExpanded(True)
                    objects_item.setExpanded(True)
                    root_item.setExpanded(True)
                else:
                    # No PLC node found, browse Objects one level
                    self._browse_one_level(objects_node, objects_item)
                    objects_item.setExpanded(True)
                    root_item.setExpanded(True)
                    
            except Exception as e:
                print(f"Error navigating to PLC: {e}")
                # Fallback: browse root one level
                self._browse_one_level(root, root_item)
                root_item.setExpanded(True)
            
            # Connect lazy expand signal (disconnect first to avoid duplicates)
            try:
                self.tree_widget.itemExpanded.disconnect(self._on_item_expanded)
            except TypeError:
                pass
            self.tree_widget.itemExpanded.connect(self._on_item_expanded)
            
            # Update all existing scenarios with the new client and directories
            for i in range(self.tab_widget.count() - 1):  # Exclude '+' tab
                scenario = self.tab_widget.widget(i)
                if isinstance(scenario, RecordingScenario):
                    scenario.client = self.client
                    scenario.update_directory_list(self.browsed_directories)

            # Update benchmark tab
            self.benchmark_tab.client = self.client
            self.benchmark_tab.update_directory_list(self.browsed_directories)
            
            # Auto-discover opctest variables and add to benchmark
            self._auto_add_opctest_vars()
            
            QMessageBox.information(self, "Success", "Connected to OPC UA server successfully!")
            
        except Exception as e:
            error_msg = f"Connection Error: {str(e)}\nType: {type(e)}"
            print(error_msg)
            QMessageBox.critical(self, "Connection Error", error_msg)
            self.update_connection_status(False)
            self.disconnect_client()

    def _auto_add_opctest_vars(self):
        """Auto-discover opctest1..opctest200 global variables and add to benchmark."""
        if not self.client:
            return
        added = 0
        failed = 0
        # B&R global variables are at ns=6;s=::AsGlobalPV:varname
        # Also try the IO task name pattern ns=6;s=::IOSimulat:varname
        prefixes = ["::AsGlobalPV:", "::IOSimulat:", "::gMainSimo:"]
        found_prefix = None

        # Probe first variable to find the right prefix
        for prefix in prefixes:
            node_path = f"ns=6;s={prefix}opctest1"
            try:
                node = self.client.get_node(node_path)
                _ = node.get_value()
                found_prefix = prefix
                print(f"Found opctest vars at prefix: {prefix}")
                break
            except Exception:
                continue

        if not found_prefix:
            print("opctest vars not found at any known prefix, skipping auto-add")
            return

        for i in range(1, 201):
            var_name = f"opctest{i}"
            node_path = f"ns=6;s={found_prefix}{var_name}"
            try:
                node = self.client.get_node(node_path)
                _ = node.get_value()  # Verify it's readable
                if self.benchmark_tab.add_variable(var_name, node_path):
                    added += 1
            except Exception:
                failed += 1

        if added > 0:
            print(f"Auto-added {added} opctest variables to benchmark (prefix: {found_prefix})")
        if failed > 0:
            print(f"  ({failed} opctest variables not found/readable)")

    def _browse_one_level(self, node, parent_item):
        """Browse one level of children and add placeholder items for expandable nodes."""
        try:
            children = node.get_children()
            for child in children:
                try:
                    browse_name = child.get_display_name().Text
                    child_id = child.nodeid.to_string()
                    node_class = child.get_node_class()
                    
                    is_variable = (node_class == ua.NodeClass.Variable)
                    type_label = "Variable" if is_variable else "Folder"
                    
                    child_item = QTreeWidgetItem([browse_name, type_label])
                    child_item.setData(0, 1, child_id)
                    child_item.setData(0, Qt.UserRole + 1, int(node_class) if node_class else 0)
                    
                    # Color-code: variables = cyan, folders = warm yellow
                    if is_variable:
                        child_item.setForeground(0, QColor("#4fc3f7"))  # light blue
                        child_item.setForeground(1, QColor("#66bb6a"))  # green
                    else:
                        child_item.setForeground(0, QColor("#ffcc80"))  # warm orange
                        child_item.setForeground(1, QColor("#5a7a9a"))
                    
                    parent_item.addChild(child_item)
                    
                    # Build full path
                    path_parts = []
                    temp_item = child_item
                    while temp_item is not None:
                        path_parts.insert(0, temp_item.text(0))
                        temp_item = temp_item.parent()
                    full_path = '/'.join(path_parts)
                    
                    if is_variable:
                        self.browsed_variables[browse_name] = child_id
                    else:
                        self.browsed_directories[full_path] = child_id
                        dummy = QTreeWidgetItem(["Loading...", ""])
                        dummy.setData(0, 1, "__placeholder__")
                        dummy.setForeground(0, QColor("#666666"))
                        child_item.addChild(dummy)
                        
                except Exception as e:
                    print(f"Error browsing child: {e}")
                    continue
        except Exception as e:
            print(f"Error getting children: {e}")

    def _on_item_expanded(self, item):
        """Lazy load children when a tree item is expanded."""
        if not self.client:
            return
        # Check if this item has a placeholder child
        if item.childCount() == 1 and item.child(0).data(0, 1) == "__placeholder__":
            # Remove placeholder
            item.removeChild(item.child(0))
            # Browse this node's children
            node_id = item.data(0, 1)
            if node_id:
                node = self.client.get_node(node_id)
                self._browse_one_level(node, item)

    def browse_nodes(self, node, parent_item):
        """Legacy recursive browse - no longer used for initial load."""
        self._browse_one_level(node, parent_item)

    def _on_search_changed(self, text):
        """Filter tree items based on search text."""
        if not text:
            # Show all items
            self._set_all_visible(self.tree_widget.invisibleRootItem(), True)
            return
        
        text_lower = text.lower()
        self._filter_tree(self.tree_widget.invisibleRootItem(), text_lower)

    def _filter_tree(self, item, text):
        """Recursively filter tree items. Returns True if this item or any child matches."""
        match = False
        for i in range(item.childCount()):
            child = item.child(i)
            child_match = text in child.text(0).lower()
            # Check children recursively
            descendant_match = self._filter_tree(child, text)
            visible = child_match or descendant_match
            child.setHidden(not visible)
            if child_match:
                # Expand parents to show match
                parent = child.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
            if visible:
                match = True
        return match

    def _set_all_visible(self, item, visible):
        """Set all tree items visible/hidden."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setHidden(not visible)
            self._set_all_visible(child, visible)

    def _tree_context_menu(self, position):
        """Show context menu on right-click in tree."""
        items = self.tree_widget.selectedItems()
        if not items:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #16213e; color: #e0e0e0;
                border: 1px solid #2a3a5a; border-radius: 8px; padding: 4px;
            }
            QMenu::item { padding: 8px 24px; border-radius: 4px; }
            QMenu::item:selected { background-color: #0f3460; color: #e94560; }
        """)
        
        # Count variables in selection
        var_items = [it for it in items if it.text(1) == "Variable"]
        folder_items = [it for it in items if it.text(1) != "Variable" and it.data(0, 1) != "__placeholder__"]
        
        if var_items:
            add_action = menu.addAction(f"Add {len(var_items)} variable(s) to Benchmark")
            add_action.triggered.connect(lambda: self._add_items_to_benchmark(var_items))
        
        if folder_items:
            add_folder_action = menu.addAction(f"Add all variables from {len(folder_items)} folder(s)")
            add_folder_action.triggered.connect(lambda: self._add_folders_to_benchmark(folder_items))
        
        if var_items or folder_items:
            menu.exec_(self.tree_widget.viewport().mapToGlobal(position))

    def _add_selected_to_benchmark(self):
        """Add selected tree items to benchmark variable list."""
        items = self.tree_widget.selectedItems()
        if not items:
            QMessageBox.information(self, "No Selection", 
                "Select variables in the tree first.\nUse Ctrl+Click for multiple selection.")
            return
        
        var_items = [it for it in items if it.text(1) == "Variable"]
        folder_items = [it for it in items if it.text(1) != "Variable" 
                       and it.data(0, 1) and it.data(0, 1) != "__placeholder__"]
        
        if var_items:
            self._add_items_to_benchmark(var_items)
        if folder_items:
            self._add_folders_to_benchmark(folder_items)
        
        if not var_items and not folder_items:
            QMessageBox.information(self, "No Variables", 
                "Select variable nodes (blue) or folder nodes to add.")

    def _add_items_to_benchmark(self, items):
        """Add specific variable items to the benchmark tab."""
        added = 0
        for item in items:
            node_id = item.data(0, 1)
            if not node_id:
                continue
            # Build full path
            path_parts = []
            temp = item
            while temp:
                path_parts.insert(0, temp.text(0))
                temp = temp.parent()
            full_path = '/'.join(path_parts)
            
            if self.benchmark_tab.add_variable(full_path, node_id):
                added += 1
        
        if added > 0:
            # Switch to Performance tab
            self.tab_widget.setCurrentIndex(0)
            print(f"Added {added} variable(s) to benchmark")

    def _add_folders_to_benchmark(self, folder_items):
        """Add all variables from folders to benchmark."""
        if not self.client:
            return
        added = 0
        for folder_item in folder_items:
            node_id = folder_item.data(0, 1)
            if not node_id:
                continue
            try:
                node = self.client.get_node(node_id)
                children = node.get_children()
                for child in children:
                    try:
                        if child.get_node_class() == ua.NodeClass.Variable:
                            name = child.get_display_name().Text
                            # Build path
                            path_parts = []
                            temp = folder_item
                            while temp:
                                path_parts.insert(0, temp.text(0))
                                temp = temp.parent()
                            full_path = '/'.join(path_parts) + '/' + name
                            cid = child.nodeid.to_string()
                            if self.benchmark_tab.add_variable(full_path, cid):
                                added += 1
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error browsing folder: {e}")
        
        if added > 0:
            self.tab_widget.setCurrentIndex(0)
            print(f"Added {added} variable(s) from folder(s) to benchmark")

    def update_connection_status(self, connected=False):
        """Update the connection status LED."""
        if connected:
            self.status_led.setStyleSheet(
                "QLabel { background-color: #00e676; border-radius: 6px; border: none; }"
            )
        else:
            self.status_led.setStyleSheet(
                "QLabel { background-color: #e94560; border-radius: 6px; border: none; }"
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