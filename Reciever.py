import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime
import time
import csv
import os

# --- НАСТРОЙКИ ---
BAUD_RATE = 9600
MAX_POINTS = 50  # Ширина окна графика
MAX_COM_PORT_CHECK = 32


# ==========================================
# 1. БЛОК ПОИСКА ПОРТА (Тот же, что и был)
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
            print(f"УСПЕХ! (Найдено чисел: {valid_floats})")
            return ser
        else:
            print(f"МУСОР")
            ser.close()
            return None

    except serial.SerialException:
        print("ОШИБКА (Занят/Нет)")
        if ser: ser.close()
        return None
    except Exception:
        if ser: ser.close()
        return None


def find_correct_port():
    print("=" * 40)
    print("ПОИСК АКТИВНОГО COM-ПОРТА")
    print("=" * 40)
    system_ports = [p.device for p in serial.tools.list_ports.comports()]
    candidates = []
    candidates.extend(system_ports)
    for i in range(1, MAX_COM_PORT_CHECK + 1):
        p_name = f"COM{i}"
        if p_name not in candidates:
            candidates.append(p_name)

    # Сортировка и удаление дублей
    final_list = []
    seen = set()
    for x in candidates:
        if x not in seen:
            final_list.append(x)
            seen.add(x)

    for port in final_list:
        found_serial = check_port_for_data(port)
        if found_serial:
            print("-" * 40)
            print(f"!!! ДАТЧИК ОБНАРУЖЕН НА {port} !!!")
            return found_serial
    return None


# ==========================================
# 2. ОСНОВНОЙ КОД
# ==========================================

# 1. Ищем порт
serial_connection = find_correct_port()

if serial_connection is None:
    print("Датчик не найден. Проверьте Sender.")
    input("Enter для выхода...")
    exit()

# 2. Создаем CSV файл
# Генерируем имя файла: ГГГГ-ММ-ДД_ЧЧ-ММ-СС.csv
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{start_time_str}.csv"

print(f"Создание файла данных: {filename}")

# Открываем файл. newline='' нужен для корректной работы модуля csv в Windows
csv_file = open(filename, mode='w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file, delimiter=',')  # Используем запятую как разделитель

# Пишем заголовки
csv_writer.writerow(["System Time", "Temperature"])
csv_file.flush()  # Сохраняем заголовки на диск сразу

# 3. Настройка графика
x_data = []
y_data = []

fig, ax = plt.subplots()
line, = ax.plot([], [], 'r-', linewidth=2, label='Температура')
ax.set_title(f'Запись в {filename} (Порт {serial_connection.port})')
ax.set_xlabel('Время')
ax.set_ylabel('T (°C)')
ax.legend()
ax.grid(True)
text_temp = ax.text(0.02, 0.95, '', transform=ax.transAxes, fontsize=12, verticalalignment='top')


def update(frame):
    # Читаем данные из порта
    if serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            # Получаем текущее время
            current_time = datetime.now().strftime('%H:%M:%S')
            full_time_for_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Время с миллисекундами

            # 1. Обновляем списки для графика
            y_data.append(val)
            x_data.append(current_time)

            if len(y_data) > MAX_POINTS:
                y_data.pop(0)
                x_data.pop(0)

            # 2. ПИШЕМ В ФАЙЛ
            # Пишем строку: [Время, Температура]
            csv_writer.writerow([full_time_for_csv, val])

            # ВАЖНО: flush() заставляет Python немедленно записать данные на диск,
            # а не держать их в памяти. Так данные сохранятся даже при вылете программы.
            csv_file.flush()

            # Обновляем текст на графике
            text_temp.set_text(f"{val}°C")

        except ValueError:
            pass
        except Exception as e:
            print(f"Ошибка чтения/записи: {e}")

    # Перерисовка графика
    line.set_data(range(len(y_data)), y_data)
    ax.set_xlim(0, MAX_POINTS)
    if y_data:
        ax.set_ylim(min(y_data) - 2, max(y_data) + 2)
    else:
        ax.set_ylim(0, 50)

    ax.set_xticks(range(len(x_data)))
    ax.set_xticklabels(x_data, rotation=45, ha='right')

    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % 5 != 0 and i != len(x_data) - 1:
            label.set_visible(False)

    return line, text_temp


try:
    print("Запись данных началась. Закройте окно графика для остановки.")
    ani = animation.FuncAnimation(fig, update, interval=100)
    plt.tight_layout()
    plt.show()
finally:
    # Этот блок выполнится при закрытии окна
    serial_connection.close()
    csv_file.close()  # Закрываем файл корректно
    print(f"\nРабота завершена. Данные сохранены в: {os.path.abspath(filename)}")