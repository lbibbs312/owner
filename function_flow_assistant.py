import sys
import os
import subprocess
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import pyqtgraph as pg


class ModernDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Modern Function Flow Assistant")
        self.setGeometry(100, 100, 800, 600)

        # Main layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        # Header
        header = QLabel("Function Flow Assistant Dashboard", self)
        header.setFont(QFont("Arial", 20))
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # Command Input
        self.command_label = QLabel("Enter Command:", self)
        main_layout.addWidget(self.command_label)

        self.command_input = QLineEdit(self)
        main_layout.addWidget(self.command_input)

        # Graph Section
        self.graph_widget = pg.PlotWidget()
        main_layout.addWidget(self.graph_widget)
        self.add_graph_animation()

        # Buttons Section
        button_layout = QHBoxLayout()

        self.generate_button = QPushButton("Generate Script", self)
        self.generate_button.clicked.connect(self.generate_script)
        button_layout.addWidget(self.generate_button)

        self.vscode_button = QPushButton("Open VS Code", self)
        self.vscode_button.clicked.connect(self.open_vscode)
        button_layout.addWidget(self.vscode_button)

        self.folder_button = QPushButton("Open Scripts Folder", self)
        self.folder_button.clicked.connect(self.open_folder)
        button_layout.addWidget(self.folder_button)

        self.terminal_button = QPushButton("Open Terminal", self)
        self.terminal_button.clicked.connect(self.open_terminal)
        button_layout.addWidget(self.terminal_button)

        self.exit_button = QPushButton("Exit", self)
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)

        main_layout.addLayout(button_layout)

    def add_graph_animation(self):
        """Add animated graph updates."""
        self.data_x = list(range(100))
        self.data_y = [0] * 100

        self.plot = self.graph_widget.plot(self.data_x, self.data_y, pen="g")
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graph)
        self.timer.start(100)

    def update_graph(self):
        """Simulate dynamic graph data."""
        self.data_y = self.data_y[1:] + [pg.np.random.randint(0, 10)]
        self.plot.setData(self.data_x, self.data_y)

    def generate_script(self):
        """Send a command to the local server to generate a script."""
        command = self.command_input.text()
        if not command:
            QMessageBox.warning(self, "Input Error", "Please enter a command.")
            return

        payload = {
            "file_name": "custom_script.py",
            "content": f"# This script was generated for: {command}\nprint('Hello from Function Flow Assistant!')"
        }

        try:
            response = requests.post("http://127.0.0.1:5000/write-script", json=payload)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", f"Script '{payload['file_name']}' generated successfully!")
            else:
                error = response.json().get("error", "Unknown error")
                QMessageBox.critical(self, "Server Error", f"Error: {error}")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Connection Error", f"Could not connect to server: {e}")

    def open_vscode(self):
        """Open Visual Studio Code."""
        try:
            subprocess.Popen(["code"])
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "VS Code is not installed or not in PATH.")

    def open_folder(self):
        """Open the GeneratedScripts folder."""
        folder_path = os.path.expanduser("~/Documents/GeneratedScripts")
        if os.path.exists(folder_path):
            os.startfile(folder_path)
        else:
            QMessageBox.critical(self, "Error", f"Folder not found: {folder_path}")

    def open_terminal(self):
        """Open a terminal window."""
        try:
            subprocess.Popen(["cmd"])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open terminal: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dashboard = ModernDashboard()
    dashboard.show()
    sys.exit(app.exec_())
