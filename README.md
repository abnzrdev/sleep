# Sleep Dashboard

Two-page Flask app for sleep analytics:

- `"/"`: ML sleep efficiency predictor (XGBoost model)
- `"/monitor"`: Live IMU monitor (MPU6050 via I2C + Socket.IO + 3D view)

If MPU6050 is not available, the monitor automatically falls back to simulation mode.

## Project Structure

- `app.py` - backend (Flask + Socket.IO + ML + sensor loop)
- `templates/index.html` - ML page
- `templates/monitor.html` - live monitor page
- `xgboost_sleep_model.pkl` - trained model
- `run.sh` - hardened startup script (auto free-port detection)
- `run.bat` - Windows startup script (auto free-port detection)

## Requirements

- Linux/macOS (or WSL on Windows)
- Python 3.10+ (tested with 3.12)
- `git`

For real MPU6050 data on Raspberry Pi:

- I2C enabled (`sudo raspi-config`)
- Sensor connected correctly (SDA/SCL/3V3/GND)

## Quick Start (Any Machine)

```bash
git clone https://github.com/abnzrdev/sleep.git
cd sleep
chmod +x run.sh
./run.sh
```

Open:

- `http://127.0.0.1:<port>/`
- `http://127.0.0.1:<port>/monitor`

The script chooses a free port automatically when `5000` is busy.

## What Is A Port?

- Think of IP as your house address (example: `192.168.8.151`).
- Port is the door number on that house (example: `5000`, `5001`, `5005`).
- A full app link is always: `http://IP:PORT/`

So if your Pi IP is `192.168.8.151` and app starts on port `5005`, open:

- `http://192.168.8.151:5005/`
- `http://192.168.8.151:5005/monitor`

You can also run directly without scripts; `app.py` now has built-in auto-port fallback:

```bash
python app.py --host 0.0.0.0 --port 5000 --max-port 5100
```

## Quick Start (Windows)

```bat
git clone https://github.com/abnzrdev/sleep.git
cd sleep
run.bat
```

Optional (without auto-opening browser):

```bat
run.bat --no-open
```

## Run with Custom Host/Port

```bash
HOST=0.0.0.0 PORT=5000 MAX_PORT=5100 ./run.sh
```

Then open from another PC on the same network:

- `http://<server-ip>:<chosen-port>/`
- `http://<server-ip>:<chosen-port>/monitor`

Find server IP on Linux:

```bash
hostname -I
```

## Raspberry Pi One-Click Start

Use one command:

```bash
cd ~/sleep
./start.sh
```

`start.sh` automatically:

- binds server to `0.0.0.0` (network-accessible)
- starts from preferred port `5000`
- falls back to next free port up to `5100`
- prints exact links (Local URL, Network URL, Monitor URL)

Open the exact `Network URL` printed in terminal.

Windows CMD example:

```bat
set HOST=0.0.0.0
set PORT=5000
set MAX_PORT=5100
run.bat
```

Windows PowerShell example:

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "5000"
$env:MAX_PORT = "5100"
.\run.bat
```

## Environment Variables

- `HOST` - bind host (default: `127.0.0.1`)
- `PORT` - preferred start port (default: `5000`)
- `MAX_PORT` - last port to scan (default: `5100`)
- `DEBUG` - app debug (`0`/`1`, default: `0`)
- `TEST_MODE` - sleep logic mode (`1` for short test timing, `0` for real timing)
- `MOVEMENT_THRESHOLD` - movement threshold for sleep/wake logic (default: `0.05`)

## API (ML Predictor)

`POST /predict` accepts form-data or JSON with exact feature names:

- `Age`
- `Gender`
- `Sleep duration`
- `REM sleep percentage`
- `Deep sleep percentage`
- `Light sleep percentage`
- `Awakenings`
- `Caffeine consumption`
- `Alcohol consumption`
- `Smoking status`
- `Exercise frequency`

Reference test payload result:

- `prediction_percent`: `87.33`
- `raw_score`: `0.8732507228851318`

## Notes for Real Sensor Deployment

- MPU6050 has no IP address; only the host device (for example Raspberry Pi) has an IP.
- Run this server on the device connected to MPU6050.
- Other PCs connect through the host device IP and port.

## Raspberry Pi: Port Busy Fix

If you see `Address already in use`, another process is listening on that port.

1. Check who is using port `5000`:

```bash
sudo ss -ltnp | grep :5000
```

2. Stop that process (replace `PID`):

```bash
sudo kill PID
```

3. Or just let this app move to the next free port automatically:

```bash
HOST=0.0.0.0 PORT=5000 MAX_PORT=5100 ./run.sh
```

4. Read your Pi IP:

```bash
hostname -I
```

## Raspberry Pi: Sensor Warning Fix

If you see `Sensor warning: [Errno 6] No such device or address`, this is usually hardware/I2C setup, not a Flask code bug.

Run these checks on Raspberry Pi:

1. Enable I2C:

```bash
sudo raspi-config
```

Then: Interface Options -> I2C -> Enable, and reboot.

2. Confirm I2C device file exists:

```bash
ls /dev/i2c-*
```

3. Install I2C tools and scan bus:

```bash
sudo apt update
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```

Expected MPU6050 address is usually `68` (sometimes `69`).

4. If sensor is found at `69`, start app with address override (no code edit needed):

```bash
MPU6050_ADDR=0x69 ./start.sh
```

5. If your board uses another I2C bus, set it when starting:

```bash
I2C_BUS=1 ./start.sh
```

The monitor page now shows selected bus/address in Sensor Source when hardware is connected.

## Conventional Commit Examples

- `feat: add monitor page navigation`
- `fix: handle missing smbus with simulation fallback`
- `docs: update setup instructions`
