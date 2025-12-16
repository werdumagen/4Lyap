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
MAX_POINTS = 50  # Начальная ширина окна (количество точек)
MAX_COM_PORT_CHECK = 32

# Глобальные переменные для управления масштабом
y_min_manual = 20.0
y_max_manual = 30.0
auto_scale_y = True  # По умолчанию включен автоскейл


# ==========================================
# 1. ЛОГИКА ПОИСКА ПОРТА (Без изменений)
# ==========================================
def check_port_for_data(port_name):
    # Используем print для отладки в консоль, пока GUI не запущен
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
# 2. ПОДГОТОВКА (Порт и CSV)
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
# 3. GUI ИНТЕРФЕЙС (TKINTER)
# ==========================================

# Создаем главное окно
root = tk.Tk()
root.title(f"Монитор температуры ({serial_connection.port})")
root.geometry("900x600")

# --- ВЕРХНЯЯ ПАНЕЛЬ НАСТРОЕК ---
control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

# Элементы управления
lbl_settings = tk.Label(control_frame, text="Настройки осей:", font=("Arial", 10, "bold"))
lbl_settings.pack(side=tk.LEFT, padx=5)

# Чекбокс авто-масштаба
var_autoscale = tk.BooleanVar(value=True)
chk_auto = tk.Checkbutton(control_frame, text="Авто-Y", variable=var_autoscale)
chk_auto.pack(side=tk.LEFT, padx=10)

# Поля ручного ввода Y
lbl_min = tk.Label(control_frame, text="Min Y:")
lbl_min.pack(side=tk.LEFT)
entry_min = tk.Entry(control_frame, width=5)
entry_min.insert(0, "20")
entry_min.pack(side=tk.LEFT, padx=2)

lbl_max = tk.Label(control_frame, text="Max Y:")
lbl_max.pack(side=tk.LEFT)
entry_max = tk.Entry(control_frame, width=5)
entry_max.insert(0, "35")
entry_max.pack(side=tk.LEFT, padx=2)


# Кнопка применения
def apply_settings():
    global y_min_manual, y_max_manual, auto_scale_y
    auto_scale_y = var_autoscale.get()
    try:
        y_min_manual = float(entry_min.get())
        y_max_manual = float(entry_max.get())
    except ValueError:
        print("Ошибка: введите числа в поля Min/Max")


btn_apply = tk.Button(control_frame, text="Применить", command=apply_settings, bg="#dddddd")
btn_apply.pack(side=tk.LEFT, padx=10)

# Текущее значение (Label)
lbl_current_temp = tk.Label(control_frame, text="T: --.-- °C", font=("Arial", 14, "bold"), fg="blue")
lbl_current_temp.pack(side=tk.RIGHT, padx=20)

# --- ГРАФИК (Embedding Matplotlib) ---
# Создаем фигуру Matplotlib (без pyplot интерфейса)
fig = Figure(figsize=(5, 4), dpi=100)
ax = fig.add_subplot(111)

# Настройка стиля
ax.grid(True, linestyle='--', alpha=0.7)
ax.set_ylabel("Температура (°C)")
ax.set_xlabel("Время")
line, = ax.plot([], [], 'r-', linewidth=2)

# Встраиваем фигуру в Tkinter
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)


# ВАЖНО: Мы НЕ добавляем NavigationToolbar2Tk, чтобы убрать кнопки снизу.

# ==========================================
# 4. ФУНКЦИЯ ОБНОВЛЕНИЯ
# ==========================================
def update_graph(frame):
    # Чтение данных
    if serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            # Время
            now_str = datetime.now().strftime('%H:%M:%S')
            full_time_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # Данные в память
            y_data.append(val)
            x_data.append(now_str)

            if len(y_data) > MAX_POINTS:
                y_data.pop(0)
                x_data.pop(0)

            # CSV
            csv_writer.writerow([full_time_csv, val])
            csv_file.flush()

            # Обновляем текст в GUI (справа сверху)
            lbl_current_temp.config(text=f"T: {val:.2f} °C")

        except ValueError:
            pass
        except Exception as e:
            print(f"Err: {e}")

    # Отрисовка линии
    line.set_data(range(len(y_data)), y_data)

    # Настройка осей
    ax.set_xlim(0, MAX_POINTS)

    # Логика масштабирования Y
    if auto_scale_y:
        if y_data:
            curr_min, curr_max = min(y_data), max(y_data)
            margin = (curr_max - curr_min) * 0.1 if curr_max != curr_min else 1.0
            ax.set_ylim(curr_min - margin, curr_max + margin)
        else:
            ax.set_ylim(0, 50)
    else:
        # Ручной режим (берем значения из переменных)
        ax.set_ylim(y_min_manual, y_max_manual)

    # Подписи оси X
    ax.set_xticks(range(len(x_data)))
    ax.set_xticklabels(x_data, rotation=45, ha='right')

    # Прореживание меток
    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % 5 != 0 and i != len(x_data) - 1:
            label.set_visible(False)

    return line,


# ==========================================
# 5. ЗАПУСК
# ==========================================

# Анимация
ani = animation.FuncAnimation(fig, update_graph, interval=100)


# Функция корректного закрытия
def on_closing():
    print("\nЗавершение работы...")
    try:
        serial_connection.close()
        csv_file.close()
        print(f"Файл сохранен: {os.path.abspath(filename)}")
    except:
        pass
    root.quit()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_closing)

print("Запуск графического интерфейса...")
tk.mainloop()