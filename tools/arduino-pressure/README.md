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
  pressure_cli.py           --port / --list-ports
  firmware/pressure_monitor/pressure_monitor.ino
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

## Firmware

Flash `firmware/pressure_monitor/pressure_monitor.ino` with Arduino IDE 2.x
(board: Arduino UNO R4 WiFi). Line format: `seq,micros,raw_adc` at 460800
baud, 14-bit ADC, MPX5700 on A0.

## Run

```bash
python pressure_monitor.py --list-ports
python pressure_monitor.py                  # default /dev/ttyACM0 or COM3
python pressure_monitor.py --port COM5
python pressure_analysis.py
python pressure_analysis.py --no-gui
```

Helpers: `./run_monitor.sh` / `run_monitor.bat` and the analysis equivalents.

Recordings land in `pressure_runs/run_<timestamp>/`. Those folders are not
committed.
