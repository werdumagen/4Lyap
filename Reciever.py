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
import numpy as np
from scipy.interpolate import make_interp_spline

# --- GLOBAL SETTINGS ---
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32

# Default Settings
current_y_min = 15.0
current_y_max = 35.0
current_window_width = 50

# Smoothing State
is_smooth_enabled = True  # Enabled by default

# Data Buffers
full_history_x = []
full_history_y = []

# Theme State
is_dark_mode = True

# Colors definition
THEME = {
    'dark': {
        'bg': '#2b2b2b', 'fg': '#ffffff',
        'entry_bg': '#404040', 'entry_fg': '#ffffff',
        'btn_bg': '#505050', 'btn_fg': '#ffffff',
        'plot_bg': '#2b2b2b', 'axis_color': '#ffffff',
        'line_color': '#FFFF00'
    },
    'light': {
        'bg': '#f0f0f0', 'fg': '#000000',
        'entry_bg': '#ffffff', 'entry_fg': '#000000',
        'btn_bg': '#dddddd', 'btn_fg': '#000000',
        'plot_bg': '#f0f0f0', 'axis_color': '#000000',
        'line_color': '#FF0000'
    }
}


# ==========================================
# 1. PORT SCANNING
# ==========================================
def check_port_for_data(port_name):
    print(f"   [...] Checking {port_name}...", end=" ", flush=True)
    ser = None
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1.5)
        ser.reset_input_buffer()
        time.sleep(1.1)

        if ser.in_waiting == 0:
            print("EMPTY")
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
            print(f"SUCCESS! (Found {valid_floats} numbers)")
            return ser
        else:
            print(f"GARBAGE")
            ser.close()
            return None

    except serial.SerialException:
        print("BUSY/NONE")
        if ser: ser.close()
        return None
    except Exception:
        if ser: ser.close()
        return None


def find_correct_port():
    print("=" * 40)
    print("SEARCHING FOR SENSOR...")
    print("=" * 40)
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
# 2. SETUP
# ==========================================
serial_connection = find_correct_port()

if serial_connection is None:
    print("\nError: Sensor not found.")
    input("Press Enter to exit...")
    exit()

# CSV Setup
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{start_time_str}.csv"
print(f"\nLogging to file: {filename}")

csv_file = open(filename, mode='w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file, delimiter=',')
csv_writer.writerow(["System Time", "Temperature"])
csv_file.flush()

# ==========================================
# 3. GUI
# ==========================================
root = tk.Tk()
root.title(f"Smooth Monitor PRO ({serial_connection.port})")
root.geometry("1000x700")

control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

ui_elements = []
ui_elements.append({'type': 'frame', 'widget': control_frame})


def create_label(parent, text, font=("Arial", 10)):
    lbl = tk.Label(parent, text=text, font=font)
    lbl.pack(side=tk.LEFT, padx=5)
    ui_elements.append({'type': 'label', 'widget': lbl})
    return lbl


def create_entry(parent, default_val, width=5):
    ent = tk.Entry(parent, width=width)
    ent.insert(0, str(default_val))
    ent.pack(side=tk.LEFT, padx=2)
    ui_elements.append({'type': 'entry', 'widget': ent})
    return ent


# Settings UI
create_label(control_frame, "SETTINGS:", font=("Arial", 10, "bold"))

# Y Axis
frame_y = tk.Frame(control_frame)
frame_y.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'frame', 'widget': frame_y})

create_label(frame_y, "Min Y:")
entry_min_y = create_entry(frame_y, current_y_min)
create_label(frame_y, "Max Y:")
entry_max_y = create_entry(frame_y, current_y_max)

# Separator
sep = tk.Frame(control_frame, width=2, bd=1, relief=tk.SUNKEN)
sep.pack(side=tk.LEFT, fill=tk.Y, padx=10)
ui_elements.append({'type': 'frame', 'widget': sep})

# X Axis
frame_x = tk.Frame(control_frame)
frame_x.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'frame', 'widget': frame_x})

create_label(frame_x, "Window:")
entry_width_x = create_entry(frame_x, current_window_width, width=6)


# Functions
def apply_settings():
    global current_y_min, current_y_max, current_window_width
    try:
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())

        if new_min >= new_max: return
        if new_width < 2: return

        current_y_min = new_min
        current_y_max = new_max
        current_window_width = new_width
        print(f"Updated: Y[{new_min}:{new_max}], Window={new_width}")
    except ValueError:
        pass


btn_apply = tk.Button(control_frame, text="Apply", command=apply_settings, relief=tk.RAISED)
btn_apply.pack(side=tk.LEFT, padx=15)
ui_elements.append({'type': 'button', 'widget': btn_apply})


# --- SMOOTH TOGGLE ---
def toggle_smooth():
    global is_smooth_enabled
    is_smooth_enabled = not is_smooth_enabled
    if is_smooth_enabled:
        btn_smooth.config(text="Smooth: ON", relief=tk.SUNKEN)
    else:
        btn_smooth.config(text="Smooth: OFF", relief=tk.RAISED)


btn_smooth = tk.Button(control_frame, text="Smooth: ON", command=toggle_smooth, width=10, relief=tk.SUNKEN)
btn_smooth.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'button', 'widget': btn_smooth})


# Theme Toggle
def toggle_theme():
    global is_dark_mode
    is_dark_mode = not is_dark_mode
    update_theme_colors()


btn_theme = tk.Button(control_frame, text="☀/☾", command=toggle_theme, width=5)
btn_theme.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'button', 'widget': btn_theme})

# Temp Label
lbl_current_temp = tk.Label(control_frame, text="T: --.-- °C", font=("Arial", 16, "bold"))
lbl_current_temp.pack(side=tk.RIGHT, padx=20)
ui_elements.append({'type': 'label_temp', 'widget': lbl_current_temp})

# --- FIGURE ---
fig = Figure(figsize=(5, 4), dpi=100)
fig.subplots_adjust(bottom=0.25)
ax = fig.add_subplot(111)

# Линия графика
line, = ax.plot([], [], '-', linewidth=2)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)


# ==========================================
# 4. THEME LOGIC
# ==========================================
def update_theme_colors():
    t = THEME['dark'] if is_dark_mode else THEME['light']
    root.configure(bg=t['bg'])

    for item in ui_elements:
        w = item['widget']
        w_type = item['type']

        if w_type == 'frame':
            w.configure(bg=t['bg'])
        elif w_type in ['label', 'label_temp']:
            w.configure(bg=t['bg'], fg=t['fg'])
        elif w_type == 'entry':
            w.configure(bg=t['entry_bg'], fg=t['entry_fg'], insertbackground=t['fg'])
        elif w_type == 'button':
            w.configure(bg=t['btn_bg'], fg=t['btn_fg'])

    fig.patch.set_facecolor(t['plot_bg'])
    ax.set_facecolor(t['plot_bg'])

    for spine in ax.spines.values():
        spine.set_color(t['axis_color'])

    ax.tick_params(axis='both', colors=t['axis_color'])
    ax.yaxis.label.set_color(t['axis_color'])
    ax.xaxis.label.set_color(t['axis_color'])
    ax.title.set_color(t['axis_color'])
    line.set_color(t['line_color'])

    grid_color = '#505050' if is_dark_mode else '#b0b0b0'
    ax.grid(True, linestyle='--', alpha=0.5, color=grid_color)
    canvas.draw()


update_theme_colors()


# ==========================================
# 5. UPDATE GRAPH (WITH SMOOTHING)
# ==========================================
def update_graph(frame):
    # Read Data
    while serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)
            now_str = datetime.now().strftime('%H:%M:%S')
            full_time_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            full_history_y.append(val)
            full_history_x.append(now_str)
            csv_writer.writerow([full_time_csv, val])
            lbl_current_temp.config(text=f"T: {val:.2f} °C")
        except:
            pass

    csv_file.flush()

    if not full_history_x: return line,

    # Окно просмотра
    start = max(0, len(full_history_x) - current_window_width)
    view_x = full_history_x[start:]
    view_y = np.array(full_history_y[start:])  # Convert to numpy array
    x_indices = np.arange(len(view_y))

    # --- СГЛАЖИВАНИЕ (SMOOTHING) ---
    if is_smooth_enabled and len(view_y) > 3:
        try:
            # Создаем более плотную сетку X (300 точек вместо 50)
            x_smooth = np.linspace(x_indices.min(), x_indices.max(), 300)

            # Строим сплайн (k=3 - кубический, самый "округлый")
            spl = make_interp_spline(x_indices, view_y, k=3)
            y_smooth = spl(x_smooth)

            # Рисуем гладкую линию
            line.set_data(x_smooth, y_smooth)
        except Exception:
            # Если ошибка в математике, рисуем обычную линию
            line.set_data(x_indices, view_y)
    else:
        # Рисуем обычную ломаную
        line.set_data(x_indices, view_y)

    # Оси
    ax.set_xlim(0, max(1, len(view_y) - 1))
    ax.set_ylim(current_y_min, current_y_max)

    # Умные подписи
    num_points = len(view_y)
    if num_points > 0:
        font_size = 10
        if num_points > 30: font_size = 9
        if num_points > 60: font_size = 8
        if num_points > 100: font_size = 7

        step = 1
        if num_points > 60: step = num_points // 60 + 1

        tick_indices = list(range(0, num_points, step))
        if (num_points - 1) not in tick_indices:
            tick_indices.append(num_points - 1)

        tick_labels = [view_x[i] for i in tick_indices]
        ax.set_xticks(tick_indices)
        ax.set_xticklabels(tick_labels, rotation=90, fontsize=font_size)

    return line,


ani = animation.FuncAnimation(fig, update_graph, interval=200)


def on_closing():
    try:
        serial_connection.close()
        csv_file.close()
    except:
        pass
    root.quit()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_closing)
print("GUI Started with Smoothing.")
tk.mainloop()