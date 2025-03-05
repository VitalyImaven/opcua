# OPC UA Variable Recorder

A Python application for recording values from OPC UA servers with a graphical user interface.

## Features

- Connect to OPC UA servers
- Browse OPC UA address space
- Select variables to monitor
- Record values at specified intervals
- Live value display
- Export data to CSV

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd opc-ua-recorder
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```

2. Enter the OPC UA server URL (default: opc.tcp://localhost:4840)
3. Click "Connect and Browse" to explore the server's address space
4. Select variables to record from the list
5. Set the recording interval and number of records
6. Click "Start Record" to begin recording
7. Use "Save CSV" to export the recorded data

## Requirements

- Python 3.6+
- opcua
- PyQt5 