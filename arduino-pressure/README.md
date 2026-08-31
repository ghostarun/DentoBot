# Arduino pressure monitor

Standalone host software for the DENTOBOT pneumatic pressure bench: live
serial plot, stage cues, CSV recording, and post-run inspection.

This folder is a **copy**. The live experiment scripts stay at
`ros2_ws/src/Arduino/` and are not used by this package. Copy or zip this
`arduino-pressure` directory onto another PC. It does not need the rest of
the DENTOBOT repository, ROS 2, or 3D Slicer.

Sensing only. It does not command a robot, authorize drilling, or implement
a safety stop.

## What you need

- Python 3.10 or newer (3.11–3.14 are fine)
- Arduino UNO WiFi R4 with an MPX5700 (or compatible) on analog pin **A0**
- USB cable
- A graphical desktop for the live plot (analysis `--no-gui` works without one)

Verified on Ubuntu with Python 3.14.6, `numpy 2.5.2`, `pyserial 3.5`,
`PyQt6 6.11.0`, `pyqtgraph 0.14.0`. Windows uses the same pip packages.

## Copy this folder to another PC

Take the whole `arduino-pressure` directory (or a zip of it). You do **not**
need `pressure_runs/` recordings from the lab PC unless you want to review
those CSVs.

```text
arduino-pressure/
  README.md                 this file
  requirements.txt
  pressure_monitor.py       live GUI
  pressure_analysis.py      post-processing GUI / --no-gui
  pressure_signal.py
  pressure_plot.py
  pressure_annotate.py
  pressure_cli.py           --port / --list-ports helper
  firmware/pressure_monitor/pressure_monitor.ino
  run_monitor.sh / .bat
  run_analysis.sh / .bat
  pressure_runs/            created when you record
```

## 1. Python environment

Do not install these packages into Slicer, Conda `dentobot`, or a ROS image.

### Ubuntu

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
# Qt on a minimal desktop may also need:
sudo apt install libxcb-cursor0 libxcb-xinerama0

cd arduino-pressure
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Add your user to `dialout` so `/dev/ttyACM0` is usable without sudo. Then
**log out and back in** (or reboot):

```bash
sudo usermod -aG dialout "$USER"
```

### Windows

1. Install Python 3.10+ from https://www.python.org/downloads/
2. Enable **Add python.exe to PATH**
3. Open Command Prompt or PowerShell in this folder:

```bat
cd arduino-pressure
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python` is not found, try `py -3`.

## 2. Firmware (once per board)

The live host expects **460800 baud** lines:

```text
seq,micros,raw_adc
```

with **14-bit** ADC counts. Flash
`firmware/pressure_monitor/pressure_monitor.ino` with Arduino IDE 2.x:

1. Board: **Arduino UNO R4 WiFi**
2. Select the serial port (see below)
3. Open the `.ino` and click Upload

Do not flash this onto a board that is mid-recording on another PC.

The older sketch under `ros2_ws/src/Arduino/pressure_monitor/` that prints
kPa at 115200 does **not** match this Python host. Use the firmware in this
folder.

## 3. Find the serial port

```bash
python pressure_monitor.py --list-ports
```

Windows: Device Manager → Ports (COM & LPT). UNO R4 often shows two COM
ports (CMSIS-DAP debug plus CDC data). Use the CDC/data port, commonly the
higher COM number. Example:

```bat
python pressure_monitor.py --port COM5
```

Ubuntu: typically `/dev/ttyACM0`. If it is `/dev/ttyACM1`:

```bash
python pressure_monitor.py --port /dev/ttyACM1
```

You can also set `PRESSURE_PORT` and `PRESSURE_BAUD`.

## 4. Live monitor

From this folder, with the venv active:

**Ubuntu**

```bash
python pressure_monitor.py
# or
./run_monitor.sh --port /dev/ttyACM0
```

On a remote/SSH session you need the physical display, for example
`DISPLAY=:0`.

**Windows**

```bat
python pressure_monitor.py --port COM5
run_monitor.bat --port COM5
```

### Recording and cues

- **Start Recording + Cues** creates `pressure_runs/run_<timestamp>/` and
  starts the stage metronome.
- Set **Cue every** (1–600 s, default 10 s). Order loops
  AIR OFF → DRILL IN AIR → DRILL IN DENTIN → DRILL IN PULP until
  **Stop Recording**.
- Space / **CUE NEXT STAGE** skips ahead and resets the countdown.
- F1–F4 mark the tissue/air stage. Those times minus **Operator latency**
  (default 400 ms) are stored in `annotations.csv`. `samples.csv` is every
  sample and is not rewritten by annotations.
- **Air** / **Trace** / **View** only change the plot. New recordings
  store raw plus filtered/ΔP columns; older CSVs still open in analysis.

The live screen is four linked plots: filtered pressure, ΔP, filtered
dP/dt, and p90−p10 spread. Tissue-boundary detection is armed only after
**DRILL IN DENTIN** while air is already on.

## 5. Post-processing

No Arduino required. Points at `pressure_runs/` next to these scripts, or
pass a run folder / `samples.csv`.

```bash
python pressure_analysis.py
python pressure_analysis.py --no-gui
python pressure_analysis.py --no-gui path\to\run_20260831_181522
python pressure_analysis.py --no-gui --auto-air-thresholds
```

`--no-gui` prints dips, peaks, air-off fraction, load boundaries, and
annotation matches. Default confirmed-event floor is 20 ms.

To review CSVs copied from the lab PC, put the `run_*` folder under
`pressure_runs/` in this directory, or pass its path on the command line.

## Output files

Each recording writes:

| File | Role |
|---|---|
| `samples.csv` | every sample (do not edit) |
| `events.csv` | live dip/peak detector |
| `annotations.csv` | cues and latency-corrected stage marks |

## Troubleshooting

| Symptom | What to try |
|---|---|
| `Could not open COMx` / `/dev/ttyACM0` | `--list-ports`; close Arduino IDE Serial Monitor and other Python GUIs; on Ubuntu confirm `dialout` and replug USB |
| GUI starts, plot stays empty | Baud 460800 and firmware line format `seq,micros,raw`; unplug other serial programs |
| `Qt platform plugin` / blank window | Ubuntu: install `libxcb-cursor0`; run from a graphical session, not a raw SSH tty |
| Cue beeps missing | Optional Qt multimedia; Mute is off; Windows/Ubuntu still flash the banner |
| `pip` / `venv` not found | Ubuntu: `python3-venv`; Windows: reinstall Python with PATH enabled |
| Two COM ports on Windows | Use the non-debug CDC port |

## Relation to the DENTOBOT repo

On the lab Ubuntu machine, experiments may still be running from
`ros2_ws/src/Arduino/pressure_monitor.py`. Leave that copy alone. This
folder is the portable snapshot for another PC. Run files written here stay
under this folder’s `pressure_runs/`.
