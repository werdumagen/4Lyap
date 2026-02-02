import serial
import time
import random
import math

# --- НАСТРОЙКИ ---
SERIAL_PORT = 'COM22'  # Порт отправки
BAUD_RATE = 9600


def generate_temperatures(step):
    """Генерирует две разные температуры"""
    # Датчик 1 (Синус, теплее)
    t1 = 25.0 + 10 * math.sin(step * 0.1) + random.uniform(-0.2, 0.2)

    # Датчик 2 (Косинус, холоднее)
    t2 = 15.0 + 5 * math.cos(step * 0.15) + random.uniform(-0.2, 0.2)
    return t1, t2


def main():
    try:
        # write_timeout=2 важен! Если порт забит, через 2 сек вылетит ошибка, которую мы поймаем
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, write_timeout=2)
        print(f"Эмулятор (2 датчика) запущен на порту {SERIAL_PORT}.")
    except serial.SerialException as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось открыть порт {SERIAL_PORT}.\n{e}")
        return

    time.sleep(1)
    ser.reset_output_buffer()

    step = 0
    try:
        while True:
            t1, t2 = generate_temperatures(step)

            # Формируем строку: "ЧИСЛО!ЧИСЛО\n"
            msg = f"{t1:.2f}!{t2:.2f}\n"

            try:
                # Пытаемся записать данные
                ser.write(msg.encode('utf-8'))
                ser.flush()
                print(f"[{step}] Отправлено: {msg.strip()}")

            except serial.SerialTimeoutException:
                # ЕСЛИ НИКТО НЕ СЛУШАЕТ — МЫ ПОПАДАЕМ СЮДА (и не падаем)
                print(f"[{step}] (!) Предупреждение: Буфер порта полон. Receiver не запущен?")

                # Сбрасываем буфер, чтобы не копить старье
                ser.reset_output_buffer()

            except Exception as e:
                print(f"[{step}] Ошибка записи: {e}")

            step += 1
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nОстановка.")
    finally:
        if ser.is_open:
            ser.close()


if __name__ == "__main__":
    main()