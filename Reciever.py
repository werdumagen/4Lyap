import sys
import os
import time
import datetime
import logging
import serial
import serial.tools.list_ports
import numpy as np

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QLineEdit, QInputDialog, QFrame, QSplashScreen)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPalette, QPixmap

import pyqtgraph as pg


# ==========================================
# 0. РЕСУРСЫ (для упаковки в EXE)
# ==========================================
def resource_path(relative_path):
    """ Получает абсолютный путь к ресурсу для PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
pg.setConfigOption('background', '#2b2b2b')
pg.setConfigOption('foreground', '#ffffff')
pg.setConfigOptions(antialias=True)

log_filename = f"log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("=== APPLICATION STARTED ===")

LINE_COLORS = ['#FFFF00', '#00FFFF', '#00FF00', '#FF00FF', '#FFA500', '#FFFFFF']
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32


# ==========================================
# 2. АВТОПОИСК
# ==========================================
def check_port_for_data(port_name):
    print(f"Checking {port_name}...", end=" ", flush=True)
    ser = None
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1.5)
        ser.reset_input_buffer()
        time.sleep(1.5)

        for _ in range(3):
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue

                # Ищем наличие ! и чисел
                if '!' in line:
                    parts = line.split('!')
                    valid_nums = 0
                    for p in parts:
                        # Проверка на число (включая отрицательные)
                        if p.strip().replace('.', '', 1).isdigit():
                            valid_nums += 1
                        elif p.startswith('-') and p[1:].replace('.', '', 1).isdigit():
                            valid_nums += 1

                    if valid_nums > 0:
                        print(f"SUCCESS! ({valid_nums} values)")
                        return ser
            except Exception:
                pass

        print("NO DATA")
        ser.close()
        return None
    except Exception as e:
        print(f"FAIL ({e})")
        if ser: ser.close()
        return None


# ==========================================
# 3. GUI КЛАССЫ
# ==========================================
class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [datetime.datetime.fromtimestamp(value).strftime("%H:%M:%S") for value in values]


class MainWindow(QMainWindow):
    def __init__(self, window_width):
        super().__init__()
        self.setWindowTitle("TermoReceiver (Custom Format)")
        self.resize(1000, 750)

        self.serial_connection = None
        self.window_width = window_width
        self.y_min = 10.0
        self.y_max = 25.0

        self.x_data = []
        self.y_data = []
        self.lines = []

        self.init_csv()
        self.setup_ui()
        self.apply_dark_theme()

        self.robust_auto_find_port()

        self.timer = QTimer()
        self.timer.timeout.connect(self.run_app_cycle)
        self.timer.start(20)

    def init_csv(self):
        start_time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.csv_filename = f"{start_time_str}.csv"
        try:
            self.csv_file = open(self.csv_filename, mode='w', newline='', encoding='utf-8')
            # Заголовок тоже можно сделать похожим на формат
            self.csv_file.write("Date!Time Values...\n")
            self.csv_file.flush()
        except Exception:
            pass

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Control Panel
        control_layout = QHBoxLayout()
        control_frame = QFrame()
        control_frame.setStyleSheet("background-color: #353535; border-radius: 5px;")
        control_frame.setLayout(control_layout)
        main_layout.addWidget(control_frame)

        control_layout.addWidget(QLabel("Port:"))
        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(80)
        self.refresh_ports()
        control_layout.addWidget(self.combo_ports)

        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(self.manual_connect)
        btn_connect.setStyleSheet("background-color: #505050; color: white;")
        control_layout.addWidget(btn_connect)

        control_layout.addWidget(QLabel(" |  Y-Axis:"))
        self.input_ymin = QLineEdit(str(self.y_min))
        self.input_ymin.setFixedWidth(50)
        control_layout.addWidget(self.input_ymin)
        control_layout.addWidget(QLabel("-"))
        self.input_ymax = QLineEdit(str(self.y_max))
        self.input_ymax.setFixedWidth(50)
        control_layout.addWidget(self.input_ymax)

        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.apply_settings)
        btn_apply.setStyleSheet("background-color: #505050; color: white;")
        control_layout.addWidget(btn_apply)

        control_layout.addStretch()
        self.lbl_temp = QLabel("T: --.--")
        self.lbl_temp.setStyleSheet("font-size: 18px; font-weight: bold; color: #00FF00;")
        control_layout.addWidget(self.lbl_temp)

        # Plot
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(self.y_min, self.y_max)
        main_layout.addWidget(self.plot_widget)

        # Status
        self.lbl_status = QLabel("Status: Waiting...")
        self.lbl_status.setStyleSheet("color: gray;")
        main_layout.addWidget(self.lbl_status)

    def apply_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#2b2b2b"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#404040"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#505050"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#505050"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        self.setPalette(palette)

    def refresh_ports(self):
        self.combo_ports.clear()
        ports = sorted([p.device for p in serial.tools.list_ports.comports()])
        for i in range(1, 33):
            p = f"COM{i}"
            if p not in ports: ports.append(p)
        ports.sort(key=lambda x: int(x[3:]) if x.startswith("COM") and x[3:].isdigit() else x)
        self.combo_ports.addItems(ports)

    def manual_connect(self):
        port = self.combo_ports.currentText()
        self.connect_to_port(port)

    def robust_auto_find_port(self):
        logging.info("Auto-Discovery...")
        candidates = [p.device for p in serial.tools.list_ports.comports()]
        for i in range(1, MAX_COM_PORT_CHECK + 1):
            p = f"COM{i}"
            if p not in candidates: candidates.append(p)

        def sort_key(x):
            if x.startswith("COM") and x[3:].isdigit(): return int(x[3:])
            return x

        candidates = sorted(list(set(candidates)), key=sort_key)

        for attempt in range(2):
            for port in candidates:
                ser = check_port_for_data(port)
                if ser:
                    if self.serial_connection: self.serial_connection.close()
                    self.serial_connection = ser
                    self.combo_ports.setCurrentText(port)
                    self.setWindowTitle(f"TermoReceiver - {port}")
                    self.lbl_status.setText(f"Connected: {port}")
                    self.lbl_status.setStyleSheet("color: #00FF00;")
                    return
            QApplication.processEvents()

        self.lbl_status.setText("Auto-discovery failed. Select manually.")

    def connect_to_port(self, port):
        if self.serial_connection: self.serial_connection.close()
        try:
            self.serial_connection = serial.Serial(port, BAUD_RATE, timeout=1.5)
            self.serial_connection.reset_input_buffer()
            self.setWindowTitle(f"TermoReceiver - {port}")
            self.lbl_status.setText(f"Connected: {port}")
            self.lbl_status.setStyleSheet("color: #00FF00;")
        except Exception as e:
            self.lbl_status.setText(f"Error: {e}")

    def apply_settings(self):
        try:
            self.y_min = float(self.input_ymin.text())
            self.y_max = float(self.input_ymax.text())
            if self.y_min < self.y_max:
                self.plot_widget.setYRange(self.y_min, self.y_max)
        except:
            pass

    def run_app_cycle(self):
        if not self.serial_connection or not self.serial_connection.is_open: return

        has_data = False
        try:
            while self.serial_connection.in_waiting > 0:
                line = self.serial_connection.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue

                parts = line.split('!')
                vals = []
                for p in parts:
                    if p.strip().replace('.', '', 1).isdigit() or (
                            p.startswith('-') and p[1:].replace('.', '', 1).isdigit()):
                        try:
                            vals.append(float(p))
                        except:
                            pass

                if vals:
                    has_data = True
                    ts = time.time()
                    self.x_data.append(ts)

                    while len(self.y_data) < len(vals):
                        self.y_data.append([np.nan] * (len(self.x_data) - 1))
                        idx = len(self.lines)
                        pen = pg.mkPen(color=LINE_COLORS[idx % len(LINE_COLORS)], width=2)
                        self.lines.append(self.plot_widget.plot(pen=pen))

                    for i, v in enumerate(vals): self.y_data[i].append(v)
                    for i in range(len(vals), len(self.y_data)): self.y_data[i].append(np.nan)

                    if len(self.x_data) > self.window_width:
                        self.x_data = self.x_data[-self.window_width:]
                        for i in range(len(self.y_data)): self.y_data[i] = self.y_data[i][-self.window_width:]

                    # === НОВАЯ ЛОГИКА ФОРМАТИРОВАНИЯ ===
                    now = datetime.datetime.now()
                    # Дата
                    date_part = now.strftime('%Y-%m-%d')
                    # Время
                    time_part = now.strftime('%H:%M:%S.%f')

                    # Собираем timestamp с восклицательным знаком: "2026-02-14!14:19:17.000720"
                    timestamp_str = f"{date_part}!{time_part}"

                    # Собираем значения: "!32.33! !16.72!"
                    formatted_vals = [f"!{v}!" for v in vals]
                    values_str = " ".join(formatted_vals)

                    # Итоговая строка: "ДАТА!ВРЕМЯ !ЗНАЧ! !ЗНАЧ!\n"
                    full_line = f"{timestamp_str} {values_str}\n"

                    self.csv_file.write(full_line)
                    # ====================================

                    self.lbl_temp.setText("T: " + " | ".join([f"{v:.1f}" for v in vals]))
                    self.lbl_status.setText(f"Receiving... ({len(self.x_data)}) pts")

            if has_data:
                self.csv_file.flush()
                if self.x_data:
                    for i, line in enumerate(self.lines):
                        line.setData(self.x_data, self.y_data[i], connect='finite')
        except Exception as e:
            self.lbl_status.setText(f"Err: {e}")

    def closeEvent(self, e):
        if self.serial_connection: self.serial_connection.close()
        if self.csv_file: self.csv_file.close()
        e.accept()


# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Получаем правильный путь к картинке
    logo_path = resource_path("logo.png")

    if os.path.exists(logo_path):
        pixmap = QPixmap(logo_path)
        splash = QSplashScreen(pixmap)
        splash.show()

        start_time = time.time()
        while time.time() - start_time < 3:
            app.processEvents()
            time.sleep(0.01)
        splash.close()

    w, ok = QInputDialog.getInt(None, "Settings", "Window Width:", value=50, min=2)
    if ok:
        win = MainWindow(w)
        win.show()
        sys.exit(app.exec())