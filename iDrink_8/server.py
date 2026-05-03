# iDrink Automatic Bartender - Flask Web Server
# Reza Raji (updated)
#
# Replaces guizero touchscreen UI with a web server accessible from any device (iPad, phone, etc.)
# All pump/GPIO logic preserved from original iDrink-RPi.py
#
# Dependencies: pip install flask
# Run: python3 server.py
# Then open http://<raspberry-pi-ip>:5000 on your iPad

import threading
import time
import json
import os
import io
import zipfile
import datetime
from flask import Flask, jsonify, request, send_from_directory, send_file
from time import sleep

# ---------------------------------------------------------------------------
# GPIO Setup — falls back to mock mode when not running on a Raspberry Pi
# ---------------------------------------------------------------------------
try:
    from gpiozero import LEDBoard
    # 8 pumps, each with Forward and Reverse relay (H-bridge) = 16 GPIO pins
    relay = LEDBoard(2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
    relay.on()  # Active-low relays: .on() = relay OFF at startup
    GPIO_AVAILABLE = True
    print("[GPIO] Hardware relay board initialized.")
except Exception as e:
    GPIO_AVAILABLE = False
    relay = None
    print(f"[GPIO] Not available ({e}). Running in mock mode.")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MENU_FILE         = os.path.join(os.path.dirname(__file__), 'Menu.json')
HISTORY_FILE      = os.path.join(os.path.dirname(__file__), 'history.json')
LIBRARY_FILE      = os.path.join(os.path.dirname(__file__), 'external-drinks-library.json')
PUMP_POUR_RATE    = 286   # milliseconds per 1/10 oz
DRINK_SIZE_FACTOR = 1.0   # scale drink size (1.0 = normal)
NUM_PUMPS         = 8

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
is_pouring    = False
pour_status   = {"active": False, "drink": "", "progress": 0, "menu": ""}
pumps_ON      = [0] * NUM_PUMPS
pour_lock     = threading.Lock()

# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------
def load_menu():
    with open(MENU_FILE, 'r') as f:
        return json.load(f)

def save_menu(data):
    # Write to a temp file then atomically replace — prevents corruption if
    # the process is interrupted mid-write
    tmp = MENU_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, MENU_FILE)

# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history):
    tmp = HISTORY_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(history, f, indent=2)
    os.replace(tmp, HISTORY_FILE)

# ---------------------------------------------------------------------------
# Pump control — identical logic to original iDrink-RPi.py
# ---------------------------------------------------------------------------
def drive_pump(pump_num: int, pump_action: str):
    """Control a single pump. pump_num is 1-8. Actions: FORWARD | REVERSE | OFF"""
    if not GPIO_AVAILABLE:
        print(f"  [MOCK] Pump {pump_num} -> {pump_action}")
        return
    idx_f = (pump_num * 2) - 2   # Forward relay index
    idx_r = (pump_num * 2) - 1   # Reverse relay index
    if pump_action == 'FORWARD':
        relay[idx_f].off()   # relay ON  (active low)
        relay[idx_r].on()    # relay OFF
    elif pump_action == 'REVERSE':
        relay[idx_f].on()    # relay OFF
        relay[idx_r].off()   # relay ON
    else:  # OFF (or any unknown value)
        relay[idx_f].on()
        relay[idx_r].on()

def all_pumps_off():
    for i in range(1, NUM_PUMPS + 1):
        drive_pump(i, 'OFF')

def all_pumps_action(action: str):
    all_pumps_off()
    sleep(0.05)
    for i in range(1, NUM_PUMPS + 1):
        drive_pump(i, action)

# ---------------------------------------------------------------------------
# Pour logic (runs in a background thread so the server stays responsive)
# ---------------------------------------------------------------------------
def pour_drink_thread(menu_idx: int, drink_name: str, recipe_override: list = None):
    global is_pouring, pour_status, pumps_ON

    # Look up recipe
    menu_data = load_menu()
    recipe    = recipe_override  # use caller-supplied scaled recipe if provided
    menu_name = menu_data['Menu'][menu_idx]['MenuName']
    if recipe is None:
        for drink in menu_data['Menu'][menu_idx]['Drink']:
            if drink['Name'] == drink_name:
                recipe = list(drink['Recipe'])  # copy so original is never mutated
                break

    if recipe is None:
        pour_status = {"active": False, "drink": drink_name, "progress": 0, "menu": menu_name}
        is_pouring  = False
        return

    # Calculate total pour duration for progress tracking
    active_times = [recipe[x] * PUMP_POUR_RATE * DRINK_SIZE_FACTOR
                    for x in range(NUM_PUMPS) if recipe[x] != 0]
    total_ms = max(active_times) if active_times else 1

    pour_status = {"active": True, "drink": drink_name, "progress": 0, "menu": menu_name}

    # Start pumps
    pumps_ON = [0] * NUM_PUMPS   # 1 = running forward

    for x in range(NUM_PUMPS):
        if recipe[x] != 0:
            drive_pump(x + 1, 'FORWARD')
            pumps_ON[x] = 1

    time_epoch = time.time() * 1000  # milliseconds

    # Wait loop — FORWARD → OFF when quota reached
    while any(pumps_ON):
        elapsed = time.time() * 1000 - time_epoch
        pour_status['progress'] = min(99, int(elapsed / total_ms * 100))

        for x in range(NUM_PUMPS):
            if pumps_ON[x] == 1:
                quota = recipe[x] * PUMP_POUR_RATE * DRINK_SIZE_FACTOR
                if elapsed >= quota:
                    drive_pump(x + 1, 'OFF')
                    pumps_ON[x] = 0

        sleep(0.05)

    pour_status = {"active": False, "drink": drink_name, "progress": 100, "menu": menu_name}
    is_pouring  = False

    # Log completed pour to history.json
    entry = {
        "drink":     drink_name,
        "menu":      menu_name,
        "timestamp": datetime.datetime.now().isoformat(timespec='seconds')
    }
    history = load_history()
    history.insert(0, entry)           # newest first
    save_history(history[:10000])      # cap at 10,000

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder='templates', static_folder='static')

# Serve the single-page web UI
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

# ── Read ────────────────────────────────────────────────────────────────────

@app.route('/api/menus', methods=['GET'])
def get_menus():
    """Return the entire menu collection."""
    return jsonify(load_menu())

@app.route('/api/status', methods=['GET'])
def get_status():
    """Return current pour status (polled by the UI for progress updates)."""
    return jsonify(pour_status)

# ── Pour ────────────────────────────────────────────────────────────────────

@app.route('/api/pour', methods=['POST'])
def pour():
    """Start pouring a drink. Body: { menu_idx, drink_name, recipe_override? }"""
    global is_pouring
    with pour_lock:
        if is_pouring:
            return jsonify({"error": "Already pouring — please wait."}), 409
        body            = request.get_json()
        menu_idx        = int(body.get('menu_idx', 0))
        drink_name      = body.get('drink_name', '')
        recipe_override = body.get('recipe_override', None)  # scaled recipe from strength slider
        is_pouring      = True

    t = threading.Thread(
        target=pour_drink_thread,
        args=(menu_idx, drink_name, recipe_override),
        daemon=True)
    t.start()
    return jsonify({"ok": True, "drink": drink_name})

# ── Pump Control ─────────────────────────────────────────────────────────────

@app.route('/api/pump', methods=['POST'])
def pump_control():
    """Control a single pump. Body: { pump_num (1-8), action (FORWARD|REVERSE|OFF) }"""
    body     = request.get_json()
    pump_num = int(body.get('pump_num', 1))
    action   = body.get('action', 'OFF').upper()
    drive_pump(pump_num, action)
    return jsonify({"ok": True})

@app.route('/api/pump/all', methods=['POST'])
def pump_all_control():
    """Control all pumps at once. Body: { action (FORWARD|REVERSE|OFF) }"""
    body   = request.get_json()
    action = body.get('action', 'OFF').upper()
    if action == 'OFF':
        all_pumps_off()
    else:
        all_pumps_action(action)
    return jsonify({"ok": True})

# ── Menu CRUD ────────────────────────────────────────────────────────────────

@app.route('/api/menu', methods=['POST'])
def add_menu():
    """Add a new menu. Body: { MenuName, MenuDescription, Bottles[8], Drink[] }"""
    data     = load_menu()
    body     = request.get_json()
    new_menu = {
        "MenuName":        body.get('MenuName', 'New Menu'),
        "MenuDescription": body.get('MenuDescription', ''),
        "Bottles":         body.get('Bottles', [''] * NUM_PUMPS),
        "Drink":           body.get('Drink', [])
    }
    data['Menu'].append(new_menu)
    save_menu(data)
    return jsonify({"ok": True, "idx": len(data['Menu']) - 1})

@app.route('/api/menu/<int:idx>', methods=['PUT'])
def update_menu(idx):
    """Replace an entire menu entry. Body: full menu object."""
    data = load_menu()
    body = request.get_json()
    data['Menu'][idx] = body
    # Enforce at most one active menu — if this menu is being set active,
    # clear all others; prevents two-active-menu corruption
    if body.get('Active'):
        for i, m in enumerate(data['Menu']):
            if i != idx:
                m['Active'] = False
    save_menu(data)
    return jsonify({"ok": True})

@app.route('/api/menu/<int:idx>', methods=['DELETE'])
def delete_menu(idx):
    """Delete a menu by index."""
    data = load_menu()
    if 0 <= idx < len(data['Menu']):
        data['Menu'].pop(idx)
        save_menu(data)
        return jsonify({"ok": True})
    return jsonify({"error": "Index out of range"}), 404

@app.route('/api/active-menu', methods=['PUT'])
def set_active_menu():
    """Set exactly one menu as active. Body: { idx: int, active: bool }"""
    data  = load_menu()
    body  = request.get_json()
    idx   = int(body.get('idx', 0))
    active = bool(body.get('active', True))
    # Single atomic operation — no race condition possible
    for i, m in enumerate(data['Menu']):
        m['Active'] = active and (i == idx)
    save_menu(data)
    return jsonify({"ok": True})

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update top-level settings (e.g. DarkMode). Body: { key: value, ... }"""
    data = load_menu()
    body = request.get_json()
    for key, value in body.items():
        if key != 'Menu':   # never allow overwriting the menus array this way
            data[key] = value
    save_menu(data)
    return jsonify({"ok": True})

@app.route('/api/history', methods=['GET'])
def get_history():
    """Return pour history list."""
    return jsonify(load_history())

@app.route('/api/history', methods=['DELETE'])
def clear_history():
    """Clear all pour history."""
    save_history([])
    return jsonify({"ok": True})

@app.route('/api/library', methods=['GET'])
def get_library():
    """Return the external drinks library."""
    if not os.path.exists(LIBRARY_FILE):
        return jsonify({"drinks": []})
    with open(LIBRARY_FILE, 'r') as f:
        return jsonify(json.load(f))

@app.route('/api/backup', methods=['GET'])
def backup():
    """Download a zip containing Menu.json and history.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(MENU_FILE,    'Menu.json')
        if os.path.exists(HISTORY_FILE):
            zf.write(HISTORY_FILE, 'history.json')
    buf.seek(0)
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    filename  = f'idrink-backup-{timestamp}.zip'
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name=filename)

@app.route('/api/restore', methods=['POST'])
def restore():
    """Upload a backup zip and restore Menu.json and/or history.json."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files['file']
    try:
        buf = io.BytesIO(f.read())
        with zipfile.ZipFile(buf, 'r') as zf:
            names = zf.namelist()
            restored = []
            if 'Menu.json' in names:
                data = json.loads(zf.read('Menu.json'))
                save_menu(data)
                restored.append('Menu.json')
            if 'history.json' in names:
                history = json.loads(zf.read('history.json'))
                save_history(history)
                restored.append('history.json')
        if not restored:
            return jsonify({"error": "No valid files found in zip"}), 400
        return jsonify({"ok": True, "restored": restored})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_pour():
    """Stop the active pour immediately."""
    global is_pouring, pumps_ON

    pumps_ON = [0] * NUM_PUMPS
    all_pumps_off()
    is_pouring = False
    pour_status['active']   = False
    pour_status['progress'] = 0
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 50)
    print("  iDrink Web Server")
    print("  Open http://<this-pi-ip>:5000 on your iPad")
    print("=" * 50)
    # host='0.0.0.0' makes it reachable from other devices on the same WiFi
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
