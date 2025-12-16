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

# Настройки по умолчанию
current_y_min = 15.0
current_y_max = 35.0
current_window_width = 50  # Начальное количество точек

# Хранилище ВСЕЙ истории сессии (чтобы можно было отмотать назад)
full_history_x = []
full_history_y = []


# ==========================================
# 1. ПОИСК ПОРТА
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
# 2. ПОДГОТОВКА ФАЙЛОВ И ПОРТА
# ==========================================

serial_connection = find_correct_port()

if serial_connection is None:
    print("Датчик не найден. Запустите Sender и проверьте порты.")
    input("Нажмите Enter для выхода...")
    exit()

# Генерируем имя файла
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{start_time_str}.csv"
print(f"Файл данных: {filename}")

csv_file = open(filename, mode='w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file, delimiter=',')
csv_writer.writerow(["System Time", "Temperature"])
csv_file.flush()

# ==========================================
# 3. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС
# ==========================================

root = tk.Tk()
root.title(f"PRO Monitor ({serial_connection.port})")
root.geometry("1000x700")

# --- ПАНЕЛЬ НАСТРОЕК ---
control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

lbl_settings = tk.Label(control_frame, text="ОСИ:", font=("Arial", 10, "bold"))
lbl_settings.pack(side=tk.LEFT, padx=10)

# Настройки Y
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

# Настройки X (Глубина просмотра)
frame_x = tk.Frame(control_frame)
frame_x.pack(side=tk.LEFT, padx=10)

tk.Label(frame_x, text="Окно просмотра (точек):").pack(side=tk.LEFT)
entry_width_x = tk.Entry(frame_x, width=8)
entry_width_x.insert(0, str(current_window_width))
entry_width_x.pack(side=tk.LEFT, padx=2)


# Кнопка Применить
def apply_settings():
    global current_y_min, current_y_max, current_window_width
    try:
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())

        if new_min >= new_max:
            print("Ошибка: Min Y должен быть меньше Max Y")
            return
        if new_width < 2:
            print("Ошибка: Ширина X должна быть > 1")
            return

        current_y_min = new_min
        current_y_max = new_max
        current_window_width = new_width

        print(f"Обновлено: Y[{new_min}:{new_max}], Окно={new_width} точек")

    except ValueError:
        print("Ошибка: Введите корректные числа")


btn_apply = tk.Button(control_frame, text="Применить / Обновить", command=apply_settings, bg="#dddddd",
                      relief=tk.RAISED)
btn_apply.pack(side=tk.LEFT, padx=15)

# Индикатор
lbl_current_temp = tk.Label(control_frame, text="T: --.-- °C", font=("Arial", 16, "bold"), fg="darkred")
lbl_current_temp.pack(side=tk.RIGHT, padx=20)

# --- ГРАФИК ---
# Увеличиваем нижний отступ (bottom=0.2), чтобы влезли вертикальные подписи
fig = Figure(figsize=(5, 4), dpi=100)
fig.subplots_adjust(bottom=0.25)
ax = fig.add_subplot(111)

ax.grid(True, linestyle='--', alpha=0.7)
ax.set_ylabel("Температура (°C)")
line, = ax.plot([], [], 'r.-', linewidth=1.5, markersize=4)  # Добавил точки (markers) для наглядности

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)


# ==========================================
# 4. ЛОГИКА ОБНОВЛЕНИЯ И ОТРИСОВКИ
# ==========================================
def update_graph(frame):
    # 1. Читаем данные (если есть) и пополняем ОБЩУЮ историю
    while serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            now_str = datetime.now().strftime('%H:%M:%S')
            full_time_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # Добавляем в БЕЗЛИМИТНЫЙ буфер (историю)
            full_history_y.append(val)
            full_history_x.append(now_str)

            # Пишем в файл
            csv_writer.writerow([full_time_csv, val])

            lbl_current_temp.config(text=f"T: {val:.2f} °C")

        except ValueError:
            pass
        except Exception as e:
            print(f"Err: {e}")

    # Принудительная запись на диск (чтобы данные не пропали при сбое)
    csv_file.flush()

    # 2. Формируем "Окно просмотра" (View Window)
    # Берем срез данных из полной истории на основе настройки `current_window_width`
    if not full_history_x:
        return line,

    # Если истории меньше, чем ширина окна, показываем всё что есть
    start_index = max(0, len(full_history_x) - current_window_width)

    view_x = full_history_x[start_index:]
    view_y = full_history_y[start_index:]

    # Отрисовка линии
    line.set_data(range(len(view_x)), view_y)

    # Настройка осей
    ax.set_xlim(0, len(view_x) - 1)
    ax.set_ylim(current_y_min, current_y_max)

    # 3. УМНЫЕ ПОДПИСИ (Smart Labels)
    # Задача: показать как можно больше меток времени, но чтобы они не наезжали друг на друга.

    num_points = len(view_x)

    if num_points > 0:
        # А. Рассчитываем размер шрифта
        # Чем больше точек, тем меньше шрифт. Минимум 6pt, Максимум 10pt.
        # Формула эмпирическая.
        font_size = 10
        if num_points > 30: font_size = 9
        if num_points > 60: font_size = 8
        if num_points > 100: font_size = 7
        if num_points > 150: font_size = 6

        # Б. Рассчитываем шаг (step), чтобы текст не слипся
        # Допустим, одна вертикальная надпись занимает около 15-20 пикселей ширины (включая отступ)
        # Ширина графика в пикселях примерно известна (canvas width) или берем примерное кол-во слотов.

        # Примерная емкость экрана (сколько вертикальных надписей влезет в ряд)
        max_labels_on_screen = 80  # Для шрифта 8pt

        step = 1
        if num_points > max_labels_on_screen:
            # Если точек 500, а влезает 80, то шаг = 500 // 80 = 6
            step = num_points // max_labels_on_screen + 1

        # В. Установка тиков
        # Выбираем индексы для показа
        tick_indices = list(range(0, num_points, step))
        # Всегда добавляем последнюю точку, чтобы видеть актуальное время
        if (num_points - 1) not in tick_indices:
            tick_indices.append(num_points - 1)

        tick_labels = [view_x[i] for i in tick_indices]

        ax.set_xticks(tick_indices)
        ax.set_xticklabels(tick_labels, rotation=90, fontsize=font_size)

    return line,


# ==========================================
# 5. ЗАПУСК
# ==========================================
ani = animation.FuncAnimation(fig, update_graph,
                              interval=200)  # Чуть медленнее (200мс) для экономии ресурсов при перерисовке текста


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