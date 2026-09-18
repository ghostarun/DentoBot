# Arduino pressure monitor

Host sensing bench for the DENTOBOT pneumatic pressure setup: live serial
plot, stage cues, CSV recording, and post-run inspection.

Tracked path: `tools/arduino-pressure/` inside the DentoBot git checkout.
The Ubuntu overlay exposes it as `~/dentobot/tools/arduino-pressure` via
the same symlink pattern as `docs/` and `scripts/`.

Sensing only. It does not command a robot, authorize drilling, or implement
a safety stop. Do not install these packages into Slicer, Conda `dentobot`,
or the SlicerROS2 container.

## Layout

```text
tools/arduino-pressure/
  pressure_monitor.py       live GUI
  pressure_analysis.py      post-processing GUI / --no-gui
  pressure_config.py        filter / sample-rate panel
  pressure_filter.py
  pressure_signal.py
  pressure_plot.py
  pressure_annotate.py
  pressure_cli.py           --port / --wifi / --list-ports
  pressure_transport.py     serial vs WiFi TCP link
  pressure_bridge.py        USB→TCP when campus WiFi is LDAP/enterprise
  firmware/pressure_monitor/pressure_monitor.ino   Arduino sketch (firmware)
  firmware/pressure_monitor/arduino_secrets.h.example
  requirements.txt
  pressure_runs/            local CSVs (gitignored except .gitkeep)
```

## Setup (Ubuntu)

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libxcb-cursor0 libxcb-xinerama0
cd tools/arduino-pressure
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
sudo usermod -aG dialout "$USER"   # then log out and back in
```

On this workstation the existing interpreter is
`/home/light-tarun/pressure-env/bin/python`.

## Setup (Windows)

1. Install Python 3.10+ with **Add python.exe to PATH**.
2. In this folder:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Firmware (Arduino sketch)

In Arduino IDE 2.x this file is a **sketch** (not a “script”):
`firmware/pressure_monitor/pressure_monitor.ino`. Target board: **Arduino UNO
R4 WiFi** (plain UNO has no WiFi).

1. Copy `firmware/pressure_monitor/arduino_secrets.h.example` to
   `arduino_secrets.h` in the same folder.
2. **IITM `iitmwifi` (802.1X PEAP / LDAP):** the board **cannot** join the same
   network your laptop uses for campus login. Set `PRESSURE_WIFI_MODE` to **`2`**
   so the Arduino **hosts** a small WPA2 access point (`AP_SSID` / `AP_PASS`).
   On the PC, connect WiFi to that AP (you can keep **Ethernet** on `iitmwifi`
   for internet). Then:
   `python pressure_monitor.py --wifi --wifi-host 192.168.4.1` (confirm IP on
   Serial Monitor once after flash).
3. **Other WPA2-PSK WiFi (phone hotspot, lab router):** `PRESSURE_WIFI_MODE`
   **`1`**, set `SECRET_SSID` / `SECRET_PASS`, flash, read `# WIFI IP …` on
   Serial Monitor at 460800 baud.
4. **WiFi off:** `PRESSURE_WIFI_MODE` **`0`** — USB only, or USB +
   `pressure_bridge.py` if the PC is on campus WiFi and you want TCP.
5. USB line format: `seq,micros,raw_adc`. Host command: `RATE <hz>` (200–1500).
   The same lines work over **TCP** (board WiFi or host bridge).

### Campus network: USB + bridge (recommended)

Your laptop joins campus WiFi with LDAP as usual. The Arduino stays on USB.

```bash
# Terminal 1 — on the laptop that owns the USB cable
python pressure_bridge.py --port /dev/ttyACM0 --listen 0.0.0.0:8765

# Terminal 2 — same laptop or another PC on the same campus LAN
python pressure_monitor.py --wifi --wifi-host <laptop-ip>
```

Use the laptop’s campus IP (`ip a` / `hostname -I`). Firewall rules on the
laptop must allow inbound TCP 8765 from your bench PC if you split terminals
across machines. Same-machine use: `--wifi-host 127.0.0.1`.

Ask campus IT for a **device PSK SSID** only if you need the board on WiFi
without a bridge; LDAP credentials still cannot be stored in the sketch.

## Run

`pressure_monitor.py` sets **`USE_WIFI_BY_DEFAULT = True`** and
**`DEFAULT_WIFI_HOST = 192.168.4.1`** at the top of the file (same on Linux and
Windows). With the PC WiFi joined to the board AP, run with **no arguments**:

```bash
python pressure_monitor.py
```

Set `USE_WIFI_BY_DEFAULT = False` there to fall back to USB serial.

**Linux**

```bash
python pressure_monitor.py --list-ports
python pressure_monitor.py --port /dev/ttyACM0   # USB if WiFi default off
python pressure_monitor.py --wifi --wifi-host 192.168.4.1
./run_monitor.sh
./run_monitor_wifi.sh
```

**Windows** (venv activated or `run_monitor.bat`)

```bat
python pressure_monitor.py
python pressure_monitor.py --list-ports
python pressure_monitor.py --port COM5
python pressure_monitor.py --wifi --wifi-host 192.168.4.1
run_monitor.bat
run_monitor_wifi.bat
set PRESSURE_WIFI_HOST=192.168.4.1
```

Allow **Python** through Windows Firewall if the GUI connects but gets no data.
`pressure_analysis.py` / `pressure_analysis.py --no-gui` work the same on both OSes.

Helpers: `run_monitor.sh` / `run_monitor.bat`, `run_monitor_wifi.sh` /
`run_monitor_wifi.bat`, and the analysis equivalents.

Recordings land in `pressure_runs/run_<timestamp>/`. Those folders are not
committed.
