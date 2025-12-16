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

# --- GLOBAL SETTINGS ---
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32

# Default Axis Settings
current_y_min = 15.0
current_y_max = 35.0
current_window_width = 50

# Data Buffers (Full Session History)
full_history_x = []
full_history_y = []

# Theme State (True = Dark Mode by default)
is_dark_mode = True

# Colors definition
THEME = {
    'dark': {
        'bg': '#2b2b2b', 'fg': '#ffffff',
        'entry_bg': '#404040', 'entry_fg': '#ffffff',
        'btn_bg': '#505050', 'btn_fg': '#ffffff',
        'plot_bg': '#2b2b2b', 'axis_color': '#ffffff',
        'line_color': '#FFFF00'  # Yellow for Dark Mode
    },
    'light': {
        'bg': '#f0f0f0', 'fg': '#000000',
        'entry_bg': '#ffffff', 'entry_fg': '#000000',
        'btn_bg': '#dddddd', 'btn_fg': '#000000',
        'plot_bg': '#f0f0f0', 'axis_color': '#000000',
        'line_color': '#FF0000'  # Red for Light Mode
    }
}


# ==========================================
# 1. PORT SCANNING LOGIC
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
            print(f"SUCCESS! (Numbers found: {valid_floats})")
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
    # Brute-force check for hidden ports
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
# 2. SETUP (Port & CSV)
# ==========================================

serial_connection = find_correct_port()

if serial_connection is None:
    print("\nError: Sensor not found.")
    print("1. Make sure Sender is running.")
    print("2. Check virtual ports pair.")
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
# 3. GUI SETUP
# ==========================================

root = tk.Tk()
root.title(f"Temperature Monitor by Werdiki ({serial_connection.port})")
root.geometry("1000x700")

# --- UI ELEMENTS CREATION ---

# Main Control Frame
control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

# Helper to track widgets for theme updates
ui_elements = []

# Add the main frame itself to the list to update its background
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
lbl_title = create_label(control_frame, "SETTINGS:", font=("Arial", 10, "bold"))

# Y Axis Frame
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

# X Axis Frame
frame_x = tk.Frame(control_frame)
frame_x.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'frame', 'widget': frame_x})

create_label(frame_x, "Window (points):")
entry_width_x = create_entry(frame_x, current_window_width, width=8)


# Functions
def apply_settings():
    global current_y_min, current_y_max, current_window_width
    try:
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())

        if new_min >= new_max:
            print("Error: Min Y must be < Max Y")
            return
        if new_width < 2:
            print("Error: Window must be > 1")
            return

        current_y_min = new_min
        current_y_max = new_max
        current_window_width = new_width
        print(f"Updated: Y[{new_min}:{new_max}], Window={new_width}")

    except ValueError:
        print("Error: Invalid numbers")


btn_apply = tk.Button(control_frame, text="Apply", command=apply_settings, relief=tk.RAISED)
btn_apply.pack(side=tk.LEFT, padx=15)
ui_elements.append({'type': 'button', 'widget': btn_apply})


# Theme Toggle Button
def toggle_theme():
    global is_dark_mode
    is_dark_mode = not is_dark_mode
    update_theme_colors()


btn_theme = tk.Button(control_frame, text="☀/☾", command=toggle_theme, width=5)
btn_theme.pack(side=tk.LEFT, padx=15)
ui_elements.append({'type': 'button', 'widget': btn_theme})

# Current Temp Display
lbl_current_temp = tk.Label(control_frame, text="T: --.-- °C", font=("Arial", 16, "bold"))
lbl_current_temp.pack(side=tk.RIGHT, padx=20)
ui_elements.append({'type': 'label_temp', 'widget': lbl_current_temp})

# --- MATPLOTLIB FIGURE ---
fig = Figure(figsize=(5, 4), dpi=100)
fig.subplots_adjust(bottom=0.25)  # Space for vertical labels
ax = fig.add_subplot(111)

line, = ax.plot([], [], '.-', linewidth=1.5, markersize=4)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas_widget = canvas.get_tk_widget()
canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=1)


# ==========================================
# 4. THEME & UPDATE LOGIC (FIXED)
# ==========================================

def update_theme_colors():
    """Updates colors of all GUI elements based on is_dark_mode"""
    t = THEME['dark'] if is_dark_mode else THEME['light']

    # 1. Main Window
    root.configure(bg=t['bg'])

    # 2. Widgets
    for item in ui_elements:
        w = item['widget']
        w_type = item['type']

        # FIX: 'frame' type only supports 'bg', not 'fg'
        if w_type == 'frame':
            w.configure(bg=t['bg'])

        elif w_type in ['label', 'label_bold']:
            w.configure(bg=t['bg'], fg=t['fg'])

        elif w_type == 'label_temp':
            w.configure(bg=t['bg'], fg=t['fg'])

        elif w_type == 'entry':
            w.configure(bg=t['entry_bg'], fg=t['entry_fg'], insertbackground=t['fg'])

        elif w_type == 'button':
            w.configure(bg=t['btn_bg'], fg=t['btn_fg'])

    # 3. Matplotlib Graph
    fig.patch.set_facecolor(t['plot_bg'])
    ax.set_facecolor(t['plot_bg'])

    # Axis colors
    ax.spines['bottom'].set_color(t['axis_color'])
    ax.spines['top'].set_color(t['axis_color'])
    ax.spines['right'].set_color(t['axis_color'])
    ax.spines['left'].set_color(t['axis_color'])

    ax.tick_params(axis='x', colors=t['axis_color'])
    ax.tick_params(axis='y', colors=t['axis_color'])

    ax.yaxis.label.set_color(t['axis_color'])
    ax.xaxis.label.set_color(t['axis_color'])
    ax.title.set_color(t['axis_color'])

    # Line Color
    line.set_color(t['line_color'])

    # Update grid color
    grid_color = '#505050' if is_dark_mode else '#b0b0b0'
    ax.grid(True, linestyle='--', alpha=0.5, color=grid_color)

    canvas.draw()


# Initialize theme
update_theme_colors()


def update_graph(frame):
    # 1. Read Data
    while serial_connection.in_waiting > 0:
        try:
            raw = serial_connection.readline().decode('utf-8').strip()
            val = float(raw)

            now_str = datetime.now().strftime('%H:%M:%S')
            full_time_csv = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # Buffer
            full_history_y.append(val)
            full_history_x.append(now_str)

            # CSV
            csv_writer.writerow([full_time_csv, val])

            # Update Label Text
            lbl_current_temp.config(text=f"T: {val:.2f} °C")

        except ValueError:
            pass
        except Exception:
            pass

    csv_file.flush()

    # 2. View Window Logic
    if not full_history_x:
        return line,

    start_index = max(0, len(full_history_x) - current_window_width)
    view_x = full_history_x[start_index:]
    view_y = full_history_y[start_index:]

    line.set_data(range(len(view_x)), view_y)

    # 3. Axis Setup
    ax.set_xlim(0, max(1, len(view_x) - 1))
    ax.set_ylim(current_y_min, current_y_max)

    # 4. Smart Labels (X-Axis)
    num_points = len(view_x)

    if num_points > 0:
        # Font size calculation
        font_size = 10
        if num_points > 30: font_size = 9
        if num_points > 60: font_size = 8
        if num_points > 100: font_size = 7
        if num_points > 150: font_size = 6

        # Step calculation (to avoid overlap)
        max_labels = 80  # Approximate max vertical labels
        step = 1
        if num_points > max_labels:
            step = num_points // max_labels + 1

        tick_indices = list(range(0, num_points, step))
        if (num_points - 1) not in tick_indices:
            tick_indices.append(num_points - 1)

        tick_labels = [view_x[i] for i in tick_indices]

        ax.set_xticks(tick_indices)
        ax.set_xticklabels(tick_labels, rotation=90, fontsize=font_size)

    return line,


# ==========================================
# 5. START
# ==========================================
ani = animation.FuncAnimation(fig, update_graph, interval=200)


def on_closing():
    try:
        serial_connection.close()
        csv_file.close()
    except:
        pass
    root.quit()
    root.destroy()
    print("App closed.")


root.protocol("WM_DELETE_WINDOW", on_closing)

print("GUI Started.")
tk.mainloop()