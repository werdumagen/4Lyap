import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import serial
import serial.tools.list_ports
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime
import time
import csv
import os
import logging
import sys
import numpy as np

# ==========================================
# 0. LOGGING SETUP
# ==========================================
log_filename = f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("=== APPLICATION STARTED ===")
logging.info(f"Logging initialized. Writing to: {log_filename}")

# --- GLOBAL SETTINGS (Defaults) ---
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32

# Default Settings
current_y_min = 10.0
current_y_max = 25.0
current_window_width = 50  # Will be requested at startup

# Global Connection Object
serial_connection = None

# Data Buffers (Storing only visible part)
visible_x = []
visible_y = []

# Theme State
is_dark_mode = True

# Colors definition
THEME = {
    'dark': {
        'bg': '#2b2b2b', 'fg': '#ffffff',
        'entry_bg': '#404040', 'entry_fg': '#ffffff',
        'btn_bg': '#505050', 'btn_fg': '#ffffff',
        'plot_bg': '#2b2b2b', 'axis_color': '#ffffff',
        'line_colors': ['#FFFF00', '#00FFFF', '#00FF00', '#FF00FF', '#FFA500', '#FFFFFF'],
        'status_ok': '#00FF00', 'status_err': '#FF5555'
    },
    'light': {
        'bg': '#f0f0f0', 'fg': '#000000',
        'entry_bg': '#ffffff', 'entry_fg': '#000000',
        'btn_bg': '#dddddd', 'btn_fg': '#000000',
        'plot_bg': '#f0f0f0', 'axis_color': '#000000',
        'line_colors': ['#FF0000', '#0000FF', '#008000', '#800080', '#FFA500', '#000000'],
        'status_ok': '#008800', 'status_err': '#FF0000'
    }
}


# ==========================================
# 1. SPLASH SCREEN
# ==========================================
def show_splash():
    if not os.path.exists("logo.png"):
        return
    try:
        splash_root = tk.Tk()
        splash_root.overrideredirect(True)
        img = tk.PhotoImage(file="logo.png")
        w, h = img.width(), img.height()
        ws, hs = splash_root.winfo_screenwidth(), splash_root.winfo_screenheight()
        splash_root.geometry(f"{w}x{h}+{(ws // 2) - (w // 2)}+{(hs // 2) - (h // 2)}")
        tk.Label(splash_root, image=img, borderwidth=0).pack()
        splash_root.after(3000, splash_root.destroy)
        splash_root.mainloop()
    except Exception:
        pass


show_splash()


# ==========================================
# 2. PORT SCANNING LOGIC
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

        for _ in range(4):
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue
                parts = line.split('!')
                valid_numbers = 0
                for part in parts:
                    if not part.strip(): continue
                    try:
                        float(part)
                        valid_numbers += 1
                    except ValueError:
                        pass
                if valid_numbers > 0:
                    print(f"SUCCESS! (Found {valid_numbers} vals)")
                    return ser
            except Exception:
                pass
        print("GARBAGE")
        ser.close()
        return None
    except Exception:
        print("BUSY/ERR")
        if ser: ser.close()
        return None


def auto_find_port():
    logging.info("Starting Auto-Discovery...")
    candidates = [p.device for p in serial.tools.list_ports.comports()]
    for i in range(1, MAX_COM_PORT_CHECK + 1):
        p = f"COM{i}"
        if p not in candidates: candidates.append(p)

    def sort_key(x):
        if x.startswith("COM") and x[3:].isdigit(): return int(x[3:])
        return x

    candidates = sorted(list(set(candidates)), key=sort_key)

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        logging.info(f"Scan attempt {attempt}/{max_attempts}")
        for port in candidates:
            ser = check_port_for_data(port)
            if ser:
                logging.info(f"Found on {port}")
                return ser
        if attempt < max_attempts:
            time.sleep(0.5)

    logging.warning("Auto-discovery failed. Opening GUI anyway.")
    return None


# ==========================================
# 3. SETUP & STARTUP DIALOG
# ==========================================
serial_connection = auto_find_port()

# CSV Logging
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = f"{start_time_str}.csv"
try:
    csv_file = open(csv_filename, mode='w', newline='', encoding='utf-8')
    csv_writer = csv.writer(csv_file, delimiter=',')
    csv_writer.writerow(["System Time", "Values..."])
    csv_file.flush()
    logging.info(f"CSV created: {csv_filename}")
except Exception as e:
    logging.error(f"CSV Error: {e}")

# --- GUI INITIALIZATION ---
root = tk.Tk()
root.withdraw()  # Hide main window while asking settings

# --- STARTUP DIALOG (English) ---
try:
    user_width = simpledialog.askinteger(
        "Display Settings",
        "Enter window width (number of points):",
        initialvalue=current_window_width,
        minvalue=2,
        parent=root
    )
    if user_width is not None:
        current_window_width = user_width
except Exception as e:
    logging.error(f"Dialog Error: {e}")

root.deiconify()  # Show main window

title_port = serial_connection.port if serial_connection else "NO CONNECTION"
root.title(f"TermoReciever - {title_port}")
root.geometry("1000x750")

ui_elements = []


def create_label(parent, text, font=("Arial", 10), bold=False):
    f = ("Arial", 10, "bold") if bold else ("Arial", 10)
    lbl = tk.Label(parent, text=text, font=f)
    lbl.pack(side=tk.LEFT, padx=5)
    ui_elements.append({'type': 'label', 'widget': lbl})
    return lbl


def create_entry(parent, default_val, width=5):
    ent = tk.Entry(parent, width=width)
    ent.insert(0, str(default_val))
    ent.pack(side=tk.LEFT, padx=2)
    ui_elements.append({'type': 'entry', 'widget': ent})
    return ent


# --- 1. TOP CONTROL PANEL ---
control_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
ui_elements.append({'type': 'frame', 'widget': control_frame})

# A. Port Selection
frame_port = tk.Frame(control_frame)
frame_port.pack(side=tk.LEFT, padx=5)
ui_elements.append({'type': 'frame', 'widget': frame_port})

create_label(frame_port, "Port:", bold=True)

sys_ports = [p.device for p in serial.tools.list_ports.comports()]
manual_ports = [f"COM{i}" for i in range(1, 33)]
all_available_ports = list(set(sys_ports + manual_ports))


def port_sort(x):
    if x.startswith("COM") and x[3:].isdigit(): return int(x[3:])
    return x


all_available_ports.sort(key=port_sort)

combo_ports = ttk.Combobox(frame_port, values=all_available_ports, width=8)
combo_ports.pack(side=tk.LEFT, padx=2)

if serial_connection:
    combo_ports.set(serial_connection.port)
elif "COM1" in all_available_ports:
    combo_ports.set("COM1")
elif all_available_ports:
    combo_ports.current(0)


def manual_connect():
    global serial_connection
    selected_port = combo_ports.get()
    logging.info(f"Manual connection requested to {selected_port}")

    if serial_connection and serial_connection.is_open:
        serial_connection.close()

    try:
        serial_connection = serial.Serial(selected_port, BAUD_RATE, timeout=1.5)
        serial_connection.reset_input_buffer()
        logging.info(f"Connected to {selected_port}")
        root.title(f"TermoReciever - {selected_port}")
        lbl_status.config(text=f"Status: Connected to {selected_port}", fg="green")
    except Exception as e:
        logging.error(f"Connection failed: {e}")
        lbl_status.config(text=f"Error: {e}", fg="red")
        serial_connection = None
        root.title("TermoReciever - Disconnected")


btn_connect = tk.Button(frame_port, text="Connect", command=manual_connect)
btn_connect.pack(side=tk.LEFT, padx=5)
ui_elements.append({'type': 'button', 'widget': btn_connect})

# Separator
tk.Frame(control_frame, width=2, bd=1, relief=tk.SUNKEN).pack(side=tk.LEFT, fill=tk.Y, padx=10)

# B. Settings
create_label(control_frame, "Y-Axis:", bold=True)
entry_min_y = create_entry(control_frame, current_y_min)
create_label(control_frame, "-")
entry_max_y = create_entry(control_frame, current_y_max)

tk.Frame(control_frame, width=10).pack(side=tk.LEFT)

create_label(control_frame, "Window:", bold=True)
entry_width_x = create_entry(control_frame, current_window_width, width=6)


def apply_settings():
    global current_y_min, current_y_max, current_window_width
    global visible_x, visible_y
    try:
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())

        if new_min >= new_max: return
        if new_width < 2: return

        current_y_min, current_y_max, current_window_width = new_min, new_max, new_width
        logging.info("Settings applied.")

        # Trim data if window size decreased
        if len(visible_x) > current_window_width:
            visible_x = visible_x[-current_window_width:]
            for i in range(len(visible_y)):
                visible_y[i] = visible_y[i][-current_window_width:]

        canvas.draw()
    except:
        pass


btn_apply = tk.Button(control_frame, text="Apply", command=apply_settings)
btn_apply.pack(side=tk.LEFT, padx=15)
ui_elements.append({'type': 'button', 'widget': btn_apply})


# C. Theme Toggle
def toggle_theme():
    global is_dark_mode
    is_dark_mode = not is_dark_mode
    update_theme_colors()


btn_theme = tk.Button(control_frame, text="Theme", command=toggle_theme)
btn_theme.pack(side=tk.LEFT, padx=5)
ui_elements.append({'type': 'button', 'widget': btn_theme})

# Current Temp (Right)
lbl_current_temp = tk.Label(control_frame, text="T: --.--", font=("Arial", 16, "bold"))
lbl_current_temp.pack(side=tk.RIGHT, padx=20)
ui_elements.append({'type': 'label_temp', 'widget': lbl_current_temp})

# --- 2. PLOT AREA ---
fig = Figure(figsize=(5, 4), dpi=100)
fig.subplots_adjust(bottom=0.25)
ax = fig.add_subplot(111)

lines = []

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

# --- 3. STATUS BAR ---
status_frame = tk.Frame(root, bd=1, relief=tk.SUNKEN)
status_frame.pack(side=tk.BOTTOM, fill=tk.X)
ui_elements.append({'type': 'frame', 'widget': status_frame})
lbl_status = tk.Label(status_frame, text="Status: Waiting...", font=("Consolas", 9), anchor="w")
lbl_status.pack(side=tk.LEFT, fill=tk.X, padx=5)


# ==========================================
# 5. THEME ENGINE
# ==========================================
def update_theme_colors():
    t = THEME['dark'] if is_dark_mode else THEME['light']
    root.configure(bg=t['bg'])

    for item in ui_elements:
        w = item['widget']
        typ = item['type']
        if typ == 'frame':
            w.configure(bg=t['bg'])
        elif typ == 'label':
            w.configure(bg=t['bg'], fg=t['fg'])
        elif typ == 'label_temp':
            w.configure(bg=t['bg'], fg=t['fg'])
        elif typ == 'entry':
            w.configure(bg=t['entry_bg'], fg=t['entry_fg'], insertbackground=t['fg'])
        elif typ == 'button':
            w.configure(bg=t['btn_bg'], fg=t['btn_fg'])

    status_frame.configure(bg=t['entry_bg'])
    lbl_status.configure(bg=t['entry_bg'], fg=t['fg'])

    fig.patch.set_facecolor(t['plot_bg'])
    ax.set_facecolor(t['plot_bg'])
    for sp in ax.spines.values(): sp.set_color(t['axis_color'])
    ax.tick_params(colors=t['axis_color'])
    ax.yaxis.label.set_color(t['axis_color'])
    ax.xaxis.label.set_color(t['axis_color'])

    line_colors = t['line_colors']
    for i, line in enumerate(lines):
        color = line_colors[i % len(line_colors)]
        line.set_color(color)

    ax.grid(True, linestyle='--', alpha=0.5, color='#505050' if is_dark_mode else '#b0b0b0')
    canvas.draw()


# Init Theme
update_theme_colors()


# ==========================================
# 6. MAIN LOOP (RING BUFFER LOGIC)
# ==========================================
def run_app_cycle():
    """
    Main loop with manual update rate.
    Deletes data that goes beyond the window width.
    """
    global visible_x, visible_y

    t = THEME['dark'] if is_dark_mode else THEME['light']
    has_new_data = False

    # 1. READ PORT
    if serial_connection and serial_connection.is_open:
        try:
            while serial_connection.in_waiting > 0:
                raw_bytes = serial_connection.readline()
                try:
                    raw_str = raw_bytes.decode('utf-8').strip()
                except:
                    raw_str = str(raw_bytes)

                if raw_str:
                    parts = raw_str.split('!')
                    current_values = []
                    for part in parts:
                        if not part.strip(): continue
                        try:
                            current_values.append(float(part))
                        except ValueError:
                            pass

                    if current_values:
                        has_new_data = True
                        now = datetime.now()

                        # Add new point
                        visible_x.append(now.strftime('%H:%M:%S'))

                        # If more channels appeared - add lines
                        while len(visible_y) < len(current_values):
                            new_channel_history = [np.nan] * (len(visible_x) - 1)
                            visible_y.append(new_channel_history)
                            color_idx = len(lines)
                            color = t['line_colors'][color_idx % len(t['line_colors'])]
                            new_line, = ax.plot([], [], '-', linewidth=2, color=color)
                            lines.append(new_line)

                        # Write values
                        for i, val in enumerate(current_values):
                            visible_y[i].append(val)

                        # If fewer channels than before - pad with NaN
                        for i in range(len(current_values), len(visible_y)):
                            visible_y[i].append(np.nan)

                        # === MAIN LOGIC: DELETE OLD DATA ===
                        if len(visible_x) > current_window_width:
                            excess = len(visible_x) - current_window_width
                            visible_x = visible_x[excess:]
                            for i in range(len(visible_y)):
                                visible_y[i] = visible_y[i][excess:]

                        # CSV (write everything to file)
                        csv_row = [now.strftime('%Y-%m-%d %H:%M:%S.%f')] + [f"!{v}!" for v in current_values]
                        csv_writer.writerow(csv_row)

                        status_txt = " | ".join([f"{v:.1f}" for v in current_values])
                        lbl_current_temp.config(text=f"T: {status_txt}")
                        lbl_status.config(text=f"Status: Rx ({len(visible_x)} pts)", fg=t['status_ok'])
                    else:
                        if raw_str:
                            lbl_status.config(text=f"RAW: {raw_str}", fg=t['status_err'])

        except Exception as e:
            lbl_status.config(text=f"Read Error: {e}", fg=t['status_err'])

    # 2. DRAW
    if has_new_data and visible_x:
        try:
            x_range = range(len(visible_x))

            for i, line in enumerate(lines):
                line.set_data(x_range, visible_y[i])

            ax.set_xlim(0, max(1, len(visible_x) - 1))
            # Use global Y settings (adjustable at runtime)
            ax.set_ylim(current_y_min, current_y_max)

            n = len(visible_x)
            if n > 0:
                step = 1 if n < 60 else n // 60 + 1
                idxs = list(range(0, n, step))
                if (n - 1) not in idxs: idxs.append(n - 1)
                ax.set_xticks(idxs)
                ax.set_xticklabels([visible_x[i] for i in idxs], rotation=90, fontsize=8)

            canvas.draw()
            csv_file.flush()
        except Exception as e:
            print(f"Draw Error: {e}")

    root.after(50, run_app_cycle)


def on_closing():
    try:
        if serial_connection: serial_connection.close()
        csv_file.close()
    except:
        pass
    root.quit()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_closing)

print("GUI Started.")
run_app_cycle()
tk.mainloop()