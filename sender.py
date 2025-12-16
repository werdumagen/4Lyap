import serial
import time
import random
import math

# --- НАСТРОЙКИ ---
SERIAL_PORT = 'COM22'  # Порт отправки (проверьте, что это правильная пара!)
BAUD_RATE = 9600
#2

def generate_temperature(step):
    """Генерирует плавную температуру"""
    base_temp = 25.0
    fluctuation = 10 * math.sin(step * 0.1)
    noise = random.uniform(-0.5, 0.5)
    return base_temp + fluctuation + noise


def main():
    # write_timeout=0 гарантирует, что программа не зависнет, если никто не слушает
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, write_timeout=2)
        print(f"Эмулятор запущен на порту {SERIAL_PORT}.")
    except serial.SerialException as e:
        print(f"ОШИБКА открытия порта: {e}")
        return

    # Иногда виртуальным портам нужно время на инициализацию
    time.sleep(1)
    ser.reset_output_buffer()

    step = 0
    try:
        while True:
            temp = generate_temperature(step)
            data_to_send = f"{temp:.2f}\n"

            try:
                # 1. Записываем байты
                bytes_sent = ser.write(data_to_send.encode('utf-8'))

                # 2. ПРИНУДИТЕЛЬНО отправляем данные (не ждем заполнения буфера)
                ser.flush()

                print(f"[{step}] Отправлено: {data_to_send.strip()} (байт: {bytes_sent})")
            except serial.SerialTimeoutException:
                print(f"[{step}] ВНИМАНИЕ: Порт забит, данные не ушли (никто не слушает?)")
            except Exception as e:
                print(f"[{step}] Ошибка записи: {e}")

            step += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nОстановка.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()