import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation
from datetime import datetime
import time
import csv
import os

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ ---
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32

# Переменные для управления осями (значения по умолчанию)
current_y_min = 15.0
current_y_max = 35.0
current_window_width = 50  # Сколько точек показывать по оси X


# ==========================================
# 1. ЛОГИКА ПОИСКА ПОРТА
# ==========================================
def check_port_for_data(port_name):
    print(f"   [...] Проверка {port_name}...", end=" ", flush=True)
    ser = None
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1.5)
        ser.reset_input_buffer()
        time.sleep(1.1)

        if ser.in_waiting == 0:
            print("ПУСТО")
            ser.close()
            return None

        attempts = 4
        valid_floats = 0
        for _ in range(attempts):
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue
                float(line)
                valid_floats += 1
            except ValueError:
                pass

        if valid_floats >= 2:
            print(f"УСПЕХ! (Чисел: {valid_floats})")
            return ser
        else:
            print(f"МУСОР")
            ser.close()
            return None

    except serial.SerialException:
        print("ЗАНЯТ/НЕТ")
        if ser: ser.close()
        return None
    except Exception:
        if ser: ser.close()
        return None


def find_correct_port():
    print("=" * 40)
    print("ПОИСК ДАТЧИКА...")
    system_ports = [p.device for p in serial.tools.list_ports.comports()]
    candidates = []
    candidates.extend(system_ports)
    for i in range(1, MAX_COM_PORT_CHECK + 1):
        p_name = f"COM{i}"
        if p_name not in candidates:
            candidates.append(p_name)

    final_list = []
    seen = set()
    for x in candidates:
        if x not in seen:
            final_list.append(x)
            seen.add(x)

    for port in final_list:
        found_serial = check_port_for_data(port)
        if found_serial:
            return found_serial
    return None


# ==========================================
# 2. ПОДГОТОВКА
# ==========================================

serial_connection = find_correct_port()

if serial_connection is None:
    print("Датчик не найден. Запустите Sender и проверьте порты.")
    input("Нажмите Enter для выхода...")
    exit()

# Создание CSV
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{start_time_str}.csv"
print(f"Файл данных: {filename}")

csv_file = open(filename, mode='w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file, delimiter=',')
csv_writer.writerow(["System Time", "Temperature"])
csv_file.flush()

# Данные для графика
x_data = []
y_data = []

# ==========================================
# 3. GUI ИНТЕРФЕЙС
# ==========================================

root = tk.Tk()
root.title(f"Монитор температуры ({serial_connection.port})")
root.geometry("900x600")

# --- ВЕРХНЯЯ ПАНЕЛЬ НАСТРОЕК ---
control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

# Лейбл заголовка
lbl_settings = tk.Label(control_frame, text="Настройки осей:", font=("Arial", 10, "bold"))
lbl_settings.pack(side=tk.LEFT, padx=10)

# 1. Настройки Y (Температура)
frame_y = tk.Frame(control_frame)
frame_y.pack(side=tk.LEFT, padx=10)

tk.Label(frame_y, text="Min Y:").pack(side=tk.LEFT)
entry_min_y = tk.Entry(frame_y, width=5)
entry_min_y.insert(0, str(current_y_min))
entry_min_y.pack(side=tk.LEFT, padx=2)

tk.Label(frame_y, text="Max Y:").pack(side=tk.LEFT)
entry_max_y = tk.Entry(frame_y, width=5)
entry_max_y.insert(0, str(current_y_max))
entry_max_y.pack(side=tk.LEFT, padx=2)

# Разделитель
ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

# 2. Настройки X (Ширина окна)
frame_x = tk.Frame(control_frame)
frame_x.pack(side=tk.LEFT, padx=10)

tk.Label(frame_x, text="Точек (X):").pack(side=tk.LEFT)
entry_width_x = tk.Entry(frame_x, width=5)
entry_width_x.insert(0, str(current_window_width))
entry_width_x.pack(side=tk.LEFT, padx=2)


# 3. Кнопка Применить
def apply_settings():
    global current_y_min, current_y_max, current_window_width
    try:
        # Считываем значения
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())

        # Проверка на адекватность
        if new_min >= new_max:
            print("Ошибка: Min Y должен быть меньше Max Y")
            return
        if new_width < 2:
            print("Ошибка: Ширина X должна быть > 1")
            return

        # Применяем
        current_y_min = new_min
        current_y_max = new_max
        current_window_width = new_width

        # Обрезаем данные, если новое окно меньше текущего количества точек
        if len(y_data) > current_window_width:
            del y_data[:len(y_data) - current_window_width]
            del x_data[:len(x_data) - current_window_width]

        print(f"Настройки обновлены: Y[{new_min}:{new_max}], X_width={new_width}")

    except ValueError:
        print("Ошибка: Введите корректные числа")


btn_apply = tk.Button(control_frame, text="Применить", command=apply_settings, bg="#dddddd", relief=tk.RAISED)
btn_apply.pack(side=tk.LEFT, padx=15)

# Текущее значение справа
lbl_current_temp = tk.Label(control_frame, text="T: --.-- °C", font=("Arial", 14, "bold"), fg="blue")
lbl_current_temp.pack(side=tk.RIGHT, padx=20)

# --- ГРАФИК ---
fig = Figure(figsize=(5, 4), dpi=100)
ax = fig.add_subplot(111)

ax.grid(True, linestyle='--', alpha=0.7)
ax.set_ylabel("Температура (°C)")
ax.set_xlabel("Время")
line, = ax.plot([], [], 'r-', linewidth=2)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)


# ==========================================
# 4. ФУНКЦИЯ ОБНОВЛЕНИЯ
# ==========================================
def update_graph(frame):
    # Чтение
    if serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            now_str = datetime.now().strftime('%H:%M:%S')
            full_time_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            y_data.append(val)
            x_data.append(now_str)

            # Используем переменную current_window_width вместо константы
            if len(y_data) > current_window_width:
                y_data.pop(0)
                x_data.pop(0)

            csv_writer.writerow([full_time_csv, val])
            csv_file.flush()

            lbl_current_temp.config(text=f"T: {val:.2f} °C")

        except ValueError:
            pass
        except Exception as e:
            print(f"Err: {e}")

    # Отрисовка
    line.set_data(range(len(y_data)), y_data)

    # ПРИМЕНЕНИЕ НАСТРОЕК ОСЕЙ
    # Ось X всегда от 0 до ширины окна
    ax.set_xlim(0, current_window_width)
    # Ось Y жестко задается пользователем
    ax.set_ylim(current_y_min, current_y_max)

    # Подписи оси X
    ax.set_xticks(range(len(x_data)))
    ax.set_xticklabels(x_data, rotation=45, ha='right')

    # Умное прореживание подписей (чем больше точек, тем реже подписи)
    step = max(1, len(x_data) // 10)
    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % step != 0 and i != len(x_data) - 1:
            label.set_visible(False)
        else:
            label.set_visible(True)

    return line,


# ==========================================
# 5. ЗАПУСК
# ==========================================
ani = animation.FuncAnimation(fig, update_graph, interval=100)


def on_closing():
    try:
        serial_connection.close()
        csv_file.close()
    except:
        pass
    root.quit()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_closing)

print("GUI запущен...")
tk.mainloop()