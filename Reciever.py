import sys
import os
import time
import datetime
import csv
import logging
import serial
import serial.tools.list_ports
import numpy as np

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QLineEdit, QMessageBox, QInputDialog, QFrame)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QPalette

import pyqtgraph as pg

# ==========================================
# 0. НАСТРОЙКИ И ЛОГИРОВАНИЕ
# ==========================================
# Настройка темной темы для PyQtGraph (глобально)
pg.setConfigOption('background', '#2b2b2b')
pg.setConfigOption('foreground', '#ffffff')
pg.setConfigOptions(antialias=True)  # Сглаживание линий

log_filename = f"log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("=== APPLICATION STARTED (PyQt6 + PyQtGraph) ===")

# Цвета линий (как в прошлом коде)
LINE_COLORS = ['#FFFF00', '#00FFFF', '#00FF00', '#FF00FF', '#FFA500', '#FFFFFF']  # Yellow, Cyan, Green...


# ==========================================
# 1. ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ
# ==========================================
class TimeAxisItem(pg.AxisItem):
    """
    Кастомная ось X для отображения времени в формате HH:MM:SS.
    Принимает timestamp (float) и превращает его в строку.
    """

    def tickStrings(self, values, scale, spacing):
        return [datetime.datetime.fromtimestamp(value).strftime("%H:%M:%S") for value in values]


# ==========================================
# 2. ОСНОВНОЕ ОКНО
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self, window_width):
        super().__init__()

        self.setWindowTitle("TermoReceiver (GPU Accelerated)")
        self.resize(1000, 750)

        # --- Переменные состояния ---
        self.serial_connection = None
        self.window_width = window_width
        self.y_min = 10.0
        self.y_max = 25.0

        # Буферы данных (храним данные для графика)
        # x_data - список timestamp
        # y_data - список списков (каналов)
        self.x_data = []
        self.y_data = []
        self.lines = []  # Ссылки на объекты линий PyQtGraph

        # CSV
        self.init_csv()

        # --- GUI Setup ---
        self.setup_ui()
        self.apply_dark_theme()

        # --- Таймер основного цикла (вместо while True) ---
        # 20 мс = 50 FPS. Для PyQtGraph это легкая разминка.
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_app_cycle)
        self.timer.start(20)

        # Авто-подключение при старте
        self.auto_find_port()

    def init_csv(self):
        start_time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.csv_filename = f"{start_time_str}.csv"
        try:
            self.csv_file = open(self.csv_filename, mode='w', newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.csv_file, delimiter=',')
            self.csv_writer.writerow(["System Time", "Values..."])
            self.csv_file.flush()
            logging.info(f"CSV created: {self.csv_filename}")
        except Exception as e:
            logging.error(f"CSV Error: {e}")

    def setup_ui(self):
        # Основной контейнер
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # --- 1. ВЕРХНЯЯ ПАНЕЛЬ УПРАВЛЕНИЯ ---
        control_layout = QHBoxLayout()

        # Рамка для панели
        control_frame = QFrame()
        control_frame.setFrameShape(QFrame.Shape.StyledPanel)
        control_frame.setLayout(control_layout)
        control_frame.setStyleSheet("background-color: #353535; border-radius: 5px;")
        main_layout.addWidget(control_frame)

        # Выбор порта
        control_layout.addWidget(QLabel("Port:"))
        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(80)
        self.refresh_ports()
        control_layout.addWidget(self.combo_ports)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.manual_connect)
        self.btn_connect.setStyleSheet("background-color: #505050; color: white;")
        control_layout.addWidget(self.btn_connect)

        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        control_layout.addWidget(line)

        # Настройки оси Y
        control_layout.addWidget(QLabel("Y-Axis:"))
        self.input_ymin = QLineEdit(str(self.y_min))
        self.input_ymin.setFixedWidth(50)
        control_layout.addWidget(self.input_ymin)

        control_layout.addWidget(QLabel("-"))

        self.input_ymax = QLineEdit(str(self.y_max))
        self.input_ymax.setFixedWidth(50)
        control_layout.addWidget(self.input_ymax)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply_settings)
        self.btn_apply.setStyleSheet("background-color: #505050; color: white;")
        control_layout.addWidget(self.btn_apply)

        control_layout.addStretch()  # Пружина, чтобы сдвинуть температуру вправо

        # Текущая температура (Крупно)
        self.lbl_temp = QLabel("T: --.--")
        self.lbl_temp.setStyleSheet("font-size: 18px; font-weight: bold; color: #00FF00;")
        control_layout.addWidget(self.lbl_temp)

        # --- 2. ГРАФИК (PyQtGraph) ---
        # Используем кастомную ось времени
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(self.y_min, self.y_max)
        self.plot_widget.getPlotItem().layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(self.plot_widget)

        # --- 3. СТАТУС БАР ---
        self.lbl_status = QLabel("Status: Waiting...")
        self.lbl_status.setStyleSheet("color: gray; font-family: Consolas;")
        main_layout.addWidget(self.lbl_status)

    def apply_dark_theme(self):
        # Общая палитра для окна (Qt Style)
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
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff0000"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#2a82da"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2a82da"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)

    # --- ЛОГИКА ПОРТОВ ---
    def refresh_ports(self):
        self.combo_ports.clear()
        ports = sorted([p.device for p in serial.tools.list_ports.comports()])
        # Добавляем COM1..32 на всякий случай
        for i in range(1, 33):
            p = f"COM{i}"
            if p not in ports: ports.append(p)

        # Сортировка
        ports.sort(key=lambda x: int(x[3:]) if x.startswith("COM") and x[3:].isdigit() else x)
        self.combo_ports.addItems(ports)

    def manual_connect(self):
        port = self.combo_ports.currentText()
        logging.info(f"Manual connection to {port}")
        self.connect_port(port)

    def connect_port(self, port_name):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

        try:
            self.serial_connection = serial.Serial(port_name, 9600, timeout=1.5)
            self.serial_connection.reset_input_buffer()
            self.setWindowTitle(f"TermoReceiver - {port_name}")
            self.lbl_status.setText(f"Connected to {port_name}")
            self.lbl_status.setStyleSheet("color: #00FF00;")
        except Exception as e:
            logging.error(f"Connection error: {e}")
            self.lbl_status.setText(f"Error: {e}")
            self.lbl_status.setStyleSheet("color: #FF5555;")
            self.serial_connection = None

    def auto_find_port(self):
        logging.info("Auto-discovery started...")
        sys_ports = [p.device for p in serial.tools.list_ports.comports()]
        for port in sys_ports:
            if self.check_port(port):
                self.connect_port(port)
                self.combo_ports.setCurrentText(port)
                return
        logging.warning("Auto-discovery failed.")

    def check_port(self, port):
        # Быстрая проверка: открыть, подождать, прочитать
        try:
            s = serial.Serial(port, 9600, timeout=1.5)
            time.sleep(1.5)  # Ждем инициализации Arduino
            if s.in_waiting > 0:
                s.close()
                return True
            s.close()
        except:
            pass
        return False

    def apply_settings(self):
        try:
            self.y_min = float(self.input_ymin.text())
            self.y_max = float(self.input_ymax.text())

            if self.y_min >= self.y_max:
                return

            self.plot_widget.setYRange(self.y_min, self.y_max)
            logging.info(f"Settings applied: Y={self.y_min}:{self.y_max}")
        except ValueError:
            pass

    # --- ГЛАВНЫЙ ЦИКЛ (Вызывается таймером) ---
    def run_app_cycle(self):
        if not self.serial_connection or not self.serial_connection.is_open:
            return

        has_new_data = False
        try:
            while self.serial_connection.in_waiting > 0:
                raw = self.serial_connection.readline()
                try:
                    line = raw.decode('utf-8').strip()
                except:
                    line = ""

                if not line: continue

                # Парсинг "val1!val2!val3"
                parts = line.split('!')
                vals = []
                for p in parts:
                    if p.strip():
                        try:
                            vals.append(float(p))
                        except:
                            pass

                if vals:
                    has_new_data = True
                    current_ts = time.time()  # Текущее время (float)

                    self.x_data.append(current_ts)

                    # Синхронизация количества линий
                    while len(self.y_data) < len(vals):
                        # Создаем новый буфер для канала
                        # Заполняем NaN, чтобы длина совпадала с X
                        new_chan = [np.nan] * (len(self.x_data) - 1)
                        self.y_data.append(new_chan)

                        # Создаем новую линию на графике
                        idx = len(self.lines)
                        color_hex = LINE_COLORS[idx % len(LINE_COLORS)]
                        # pen=width -> толщина линии
                        pen = pg.mkPen(color=color_hex, width=2)
                        plot_item = self.plot_widget.plot(pen=pen)
                        self.lines.append(plot_item)

                    # Добавляем данные
                    for i, val in enumerate(vals):
                        self.y_data[i].append(val)

                    # Если каналов меньше, чем было раньше
                    for i in range(len(vals), len(self.y_data)):
                        self.y_data[i].append(np.nan)

                    # Обрезаем старые данные (Ring Buffer)
                    if len(self.x_data) > self.window_width:
                        excess = len(self.x_data) - self.window_width
                        self.x_data = self.x_data[excess:]
                        for i in range(len(self.y_data)):
                            self.y_data[i] = self.y_data[i][excess:]

                    # CSV
                    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                    csv_row = [now_str] + [f"!{v}!" for v in vals]
                    self.csv_writer.writerow(csv_row)

                    # GUI Text Update
                    txt = " | ".join([f"{v:.1f}" for v in vals])
                    self.lbl_temp.setText(f"T: {txt}")
                    self.lbl_status.setText(f"Receiving data... ({len(self.x_data)} pts)")

            if has_new_data:
                self.update_plot()
                self.csv_file.flush()

        except Exception as e:
            self.lbl_status.setText(f"Error: {e}")

    def update_plot(self):
        # PyQtGraph очень быстрый, просто передаем массивы
        # x_data - время, y_data[i] - значения
        if not self.x_data: return

        for i, line in enumerate(self.lines):
            # connect='finite' позволяет корректно рисовать разрывы (NaN) если будут
            line.setData(self.x_data, self.y_data[i], connect='finite')

    def closeEvent(self, event):
        # Закрытие приложения
        if self.serial_connection:
            self.serial_connection.close()
        if self.csv_file:
            self.csv_file.close()
        event.accept()


# ==========================================
# 3. ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. Диалог при старте (Ширина окна)
    # Возвращает (int, ok)
    width, ok = QInputDialog.getInt(
        None,
        "Display Settings",
        "Enter window width (points):",
        value=50,
        min=2,
        max=10000
    )

    if not ok:
        sys.exit()  # Если нажали Cancel - выход

    window = MainWindow(window_width=width)
    window.show()

    sys.exit(app.exec())