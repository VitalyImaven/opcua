import sys
from PyQt5.QtWidgets import QApplication
from src.opc_recorder import OPCUARecorder

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OPCUARecorder()
    window.show()
    sys.exit(app.exec_()) 