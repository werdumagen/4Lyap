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
import logging
import sys

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

# --- GLOBAL SETTINGS ---
BAUD_RATE = 9600
MAX_COM_PORT_CHECK = 32

# Default Settings
current_y_min = 15.0
current_y_max = 35.0
current_window_width = 50

# Global Connection Object
serial_connection = None

# Smoothing State
is_smooth_enabled = True

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
        'line_color': '#FFFF00',
        'status_ok': '#00FF00', 'status_err': '#FF5555'
    },
    'light': {
        'bg': '#f0f0f0', 'fg': '#000000',
        'entry_bg': '#ffffff', 'entry_fg': '#000000',
        'btn_bg': '#dddddd', 'btn_fg': '#000000',
        'plot_bg': '#f0f0f0', 'axis_color': '#000000',
        'line_color': '#FF0000',
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
                float(line)  # Try to convert
                # If success
                print(f"SUCCESS!")
                return ser
            except ValueError:
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

    # 1. Get List
    candidates = [p.device for p in serial.tools.list_ports.comports()]
    # Add manual range just in case
    for i in range(1, MAX_COM_PORT_CHECK + 1):
        p = f"COM{i}"
        if p not in candidates: candidates.append(p)

    # Deduplicate
    candidates = sorted(list(set(candidates)), key=lambda x: (len(x), x))

    # 2. Try twice
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
# 3. SETUP
# ==========================================
# Try to find port, but DON'T EXIT if failed
serial_connection = auto_find_port()

# Create CSV (Session Log)
start_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = f"{start_time_str}.csv"
try:
    csv_file = open(csv_filename, mode='w', newline='', encoding='utf-8')
    csv_writer = csv.writer(csv_file, delimiter=',')
    csv_writer.writerow(["System Time", "Temperature"])
    csv_file.flush()
    logging.info(f"CSV created: {csv_filename}")
except Exception as e:
    logging.error(f"CSV Error: {e}")
    # We continue even if CSV fails, just logging won't work

# ==========================================
# 4. GUI IMPLEMENTATION
# ==========================================
root = tk.Tk()
title_port = serial_connection.port if serial_connection else "NO CONNECTION"
root.title(f"TermoReciever - {title_port}")
root.geometry("1000x750")

# --- UI Collections ---
ui_elements = []  # For theme updates


# Helper functions
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

# A. Port Selection Section
frame_port = tk.Frame(control_frame)
frame_port.pack(side=tk.LEFT, padx=5)
ui_elements.append({'type': 'frame', 'widget': frame_port})

create_label(frame_port, "Port:", bold=True)
available_ports = [p.device for p in serial.tools.list_ports.comports()]
if not available_ports: available_ports = ["COM1"]

combo_ports = ttk.Combobox(frame_port, values=available_ports, width=8)
combo_ports.pack(side=tk.LEFT, padx=2)
if serial_connection:
    combo_ports.set(serial_connection.port)
elif available_ports:
    combo_ports.current(0)


def manual_connect():
    global serial_connection
    selected_port = combo_ports.get()
    logging.info(f"Manual connection requested to {selected_port}")

    # Close old
    if serial_connection and serial_connection.is_open:
        serial_connection.close()

    try:
        serial_connection = serial.Serial(selected_port, BAUD_RATE, timeout=1.5)
        # Reset buffers to clear old garbage
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

# B. Settings Section
create_label(control_frame, "Y-Axis:", bold=True)
entry_min_y = create_entry(control_frame, current_y_min)
create_label(control_frame, "-")
entry_max_y = create_entry(control_frame, current_y_max)

tk.Frame(control_frame, width=10).pack(side=tk.LEFT)  # spacer

create_label(control_frame, "Window:", bold=True)
entry_width_x = create_entry(control_frame, current_window_width, width=6)


def apply_settings():
    global current_y_min, current_y_max, current_window_width
    try:
        new_min = float(entry_min_y.get())
        new_max = float(entry_max_y.get())
        new_width = int(entry_width_x.get())
        if new_min >= new_max: return
        if new_width < 2: return
        current_y_min, current_y_max, current_window_width = new_min, new_max, new_width
        logging.info("Settings applied.")
    except:
        pass


btn_apply = tk.Button(control_frame, text="Apply", command=apply_settings)
btn_apply.pack(side=tk.LEFT, padx=15)
ui_elements.append({'type': 'button', 'widget': btn_apply})


# C. Toggles
def toggle_smooth():
    global is_smooth_enabled
    is_smooth_enabled = not is_smooth_enabled
    btn_smooth.config(relief=tk.SUNKEN if is_smooth_enabled else tk.RAISED)


btn_smooth = tk.Button(control_frame, text="Smooth", command=toggle_smooth, relief=tk.SUNKEN)
btn_smooth.pack(side=tk.LEFT, padx=10)
ui_elements.append({'type': 'button', 'widget': btn_smooth})


def toggle_theme():
    global is_dark_mode
    is_dark_mode = not is_dark_mode
    update_theme_colors()


btn_theme = tk.Button(control_frame, text="Theme", command=toggle_theme)
btn_theme.pack(side=tk.LEFT, padx=5)
ui_elements.append({'type': 'button', 'widget': btn_theme})

# Current Temp (Right)
lbl_current_temp = tk.Label(control_frame, text="--.-- °C", font=("Arial", 16, "bold"))
lbl_current_temp.pack(side=tk.RIGHT, padx=20)
ui_elements.append({'type': 'label_temp', 'widget': lbl_current_temp})

# --- 2. PLOT AREA ---
fig = Figure(figsize=(5, 4), dpi=100)
fig.subplots_adjust(bottom=0.25)
ax = fig.add_subplot(111)
line, = ax.plot([], [], '-', linewidth=2)
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

# --- 3. STATUS BAR (RAW DATA) ---
status_frame = tk.Frame(root, bd=1, relief=tk.SUNKEN)
status_frame.pack(side=tk.BOTTOM, fill=tk.X)
ui_elements.append({'type': 'frame', 'widget': status_frame})

lbl_status = tk.Label(status_frame, text="Status: Waiting...", font=("Consolas", 9), anchor="w")
lbl_status.pack(side=tk.LEFT, fill=tk.X, padx=5)


# Don't add to ui_elements standard list because text color changes dynamically

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

    # Status bar special handling
    status_frame.configure(bg=t['entry_bg'])
    lbl_status.configure(bg=t['entry_bg'], fg=t['fg'])

    # Plot
    fig.patch.set_facecolor(t['plot_bg'])
    ax.set_facecolor(t['plot_bg'])
    for sp in ax.spines.values(): sp.set_color(t['axis_color'])
    ax.tick_params(colors=t['axis_color'])
    ax.yaxis.label.set_color(t['axis_color'])
    ax.xaxis.label.set_color(t['axis_color'])
    line.set_color(t['line_color'])
    ax.grid(True, linestyle='--', alpha=0.5, color='#505050' if is_dark_mode else '#b0b0b0')
    canvas.draw()


update_theme_colors()


# ==========================================
# 6. MAIN LOOP
# ==========================================
def update_graph(frame):
    t = THEME['dark'] if is_dark_mode else THEME['light']

    # Check connection
    if serial_connection and serial_connection.is_open:
        if serial_connection.in_waiting > 0:
            try:
                # Read line
                raw_bytes = serial_connection.readline()
                try:
                    raw_str = raw_bytes.decode('utf-8').strip()
                except:
                    raw_str = str(raw_bytes)

                if raw_str:
                    # Try to parse
                    try:
                        val = float(raw_str)
                        # SUCCESS
                        now = datetime.now()
                        full_history_y.append(val)
                        full_history_x.append(now.strftime('%H:%M:%S'))
                        csv_writer.writerow([now.strftime('%Y-%m-%d %H:%M:%S.%f'), val])
                        lbl_current_temp.config(text=f"{val:.2f} °C")

                        # Status OK
                        lbl_status.config(text=f"Status: Receiving Data ({len(full_history_y)} pts)", fg=t['status_ok'])
                    except ValueError:
                        # FAIL (Not a number) -> Show RAW
                        lbl_status.config(text=f"RAW DATA (Not Number): {raw_str}", fg=t['status_err'])
                        # Log to file too to be safe
                        logging.debug(f"Raw garbage received: {raw_str}")

            except Exception as e:
                lbl_status.config(text=f"Read Error: {e}", fg=t['status_err'])
    else:
        lbl_status.config(text="Status: Disconnected (Select Port and Click Connect)", fg=t['fg'])

    # Flush CSV
    try:
        csv_file.flush()
    except:
        pass

    # DRAW
    if not full_history_x: return line,

    # Windowing
    start = max(0, len(full_history_x) - current_window_width)
    view_x = full_history_x[start:]
    view_y = np.array(full_history_y[start:])
    x_idxs = np.arange(len(view_y))

    # Smoothing
    if is_smooth_enabled and len(view_y) > 3:
        try:
            x_smooth = np.linspace(x_idxs.min(), x_idxs.max(), 300)
            spl = make_interp_spline(x_idxs, view_y, k=3)
            y_smooth = spl(x_smooth)
            line.set_data(x_smooth, y_smooth)
        except:
            line.set_data(x_idxs, view_y)
    else:
        line.set_data(x_idxs, view_y)

    # Axis Limits
    ax.set_xlim(0, max(1, len(view_y) - 1))
    ax.set_ylim(current_y_min, current_y_max)

    # Smart Ticks
    n = len(view_y)
    if n > 0:
        step = 1 if n < 60 else n // 60 + 1
        idxs = list(range(0, n, step))
        if (n - 1) not in idxs: idxs.append(n - 1)
        ax.set_xticks(idxs)
        ax.set_xticklabels([view_x[i] for i in idxs], rotation=90, fontsize=8)

    return line,


ani = animation.FuncAnimation(fig, update_graph, interval=200)


def on_closing():
    try:
        if serial_connection: serial_connection.close()
        csv_file.close()
    except:
        pass
    root.quit()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_closing)
tk.mainloop()