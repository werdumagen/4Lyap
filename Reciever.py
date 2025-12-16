import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime
import time

# --- НАСТРОЙКИ ---
BAUD_RATE = 9600
MAX_POINTS = 50  # Ширина окна графика
MAX_COM_PORT_CHECK = 32  # До какого номера проверять (COM1...COM32)


def check_port_for_data(port_name):
    """
    Пытается открыть конкретный порт и проверить, идут ли оттуда числа.
    Возвращает объект порта, если успешно, или None.
    """
    print(f"   [...] Проверка {port_name}...", end=" ", flush=True)

    ser = None
    try:
        # Открываем с таймаутом 1.5 секунды
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1.5)

        # Чистим буфер от старого мусора
        ser.reset_input_buffer()

        # Даем немного времени на накопление данных
        time.sleep(1.1)

        if ser.in_waiting == 0:
            print("ПУСТО (нет данных)")
            ser.close()
            return None

        # Пробуем прочитать несколько строк
        attempts = 4
        valid_floats = 0

        for _ in range(attempts):
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue

                # Главная проверка: это число?
                float(line)
                valid_floats += 1
            except ValueError:
                pass  # Это не число

        # Если хотя бы 2 раза успешно распознали число - это наш клиент
        if valid_floats >= 2:
            print(f"УСПЕХ! (Найдено чисел: {valid_floats})")
            return ser
        else:
            print(f"МУСОР (Данные не похожи на температуру)")
            ser.close()
            return None

    except serial.SerialException:
        print("ОШИБКА (Порт занят или не существует)")
        if ser: ser.close()
        return None
    except Exception as e:
        print(f"СБОЙ: {e}")
        if ser: ser.close()
        return None


def find_correct_port():
    """Главная функция поиска"""
    print("=" * 40)
    print("ПОИСК АКТИВНОГО COM-ПОРТА С ДАТЧИКОМ")
    print("=" * 40)

    # 1. Сначала получаем список портов от системы
    system_ports = [p.device for p in serial.tools.list_ports.comports()]
    print(f"Система сообщает о портах: {system_ports if system_ports else 'Ничего не найдено'}")

    # 2. Формируем список кандидатов на проверку.
    # Добавляем системные порты + принудительно COM1-COM32 (на случай скрытых виртуальных портов)
    candidates = []

    # Добавляем найденные системой
    candidates.extend(system_ports)

    # Добавляем "брутфорс" список (исключая дубликаты), если хотим надежности
    # Часто виртуальные порты не показываются в list_ports, но открываются вручную
    for i in range(1, MAX_COM_PORT_CHECK + 1):
        p_name = f"COM{i}"
        # На Linux/Mac логика другая, там только system_ports, но для Windows это важно
        if p_name not in candidates:
            candidates.append(p_name)

    # Сортируем: сначала те, что нашла система, потом по порядку COM1, COM2...
    # (Хитрая сортировка, чтобы проверить системные первыми)
    def sort_key(name):
        is_system = 0 if name in system_ports else 1
        try:
            num = int(name.replace('COM', ''))
        except:
            num = 999
        return (is_system, num)

    candidates.sort(key=sort_key)

    # Удаляем дубликаты, сохраняя порядок
    final_list = []
    [final_list.append(x) for x in candidates if x not in final_list]

    print(f"Будет проверено портов: {len(final_list)}")
    print("-" * 40)

    # 3. Перебираем всех кандидатов
    for port in final_list:
        found_serial = check_port_for_data(port)
        if found_serial:
            print("-" * 40)
            print(f"!!! ДАТЧИК ОБНАРУЖЕН НА {port} !!!")
            return found_serial

    return None


# --- СТАРТ ПРОГРАММЫ ---

# 1. Ищем порт
serial_connection = find_correct_port()

if serial_connection is None:
    print("\n" + "!" * 40)
    print("КРИТИЧЕСКАЯ ОШИБКА: Датчик не найден.")
    print("Советы:")
    print("1. Запущен ли скрипт Sender?")
    print("2. Созданы ли виртуальные порты?")
    print("3. Не занят ли порт другой программой?")
    print("!" * 40)
    input("Нажмите Enter для выхода...")
    exit()

# 2. Если нашли - рисуем график
x_data = []
y_data = []

fig, ax = plt.subplots()
line, = ax.plot([], [], 'r-', linewidth=2, label='Температура')
ax.set_title(f'Данные с порта {serial_connection.port}')
ax.set_xlabel('Время')
ax.set_ylabel('T (°C)')
ax.legend()
ax.grid(True)
text_temp = ax.text(0.02, 0.95, '', transform=ax.transAxes, fontsize=12, verticalalignment='top')


def update(frame):
    if serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            now = datetime.now().strftime('%H:%M:%S')
            y_data.append(val)
            x_data.append(now)

            if len(y_data) > MAX_POINTS:
                y_data.pop(0)
                x_data.pop(0)

            text_temp.set_text(f"{val}°C")
        except:
            pass

    line.set_data(range(len(y_data)), y_data)
    ax.set_xlim(0, MAX_POINTS)
    if y_data:
        ax.set_ylim(min(y_data) - 2, max(y_data) + 2)
    else:
        ax.set_ylim(0, 50)

    ax.set_xticks(range(len(x_data)))
    ax.set_xticklabels(x_data, rotation=45, ha='right')

    # Прячем лишние подписи оси X
    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % 5 != 0 and i != len(x_data) - 1:
            label.set_visible(False)

    return line, text_temp

#1
try:
    print("Запуск графика...")
    ani = animation.FuncAnimation(fig, update, interval=100)
    plt.tight_layout()
    plt.show()
finally:
    serial_connection.close()
    print("Порт закрыт.")