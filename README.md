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

- `http://<server-ip>:5000/`
- `http://<server-ip>:5000/monitor`

Find server IP on Linux:

```bash
hostname -I
```

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

## Conventional Commit Examples

- `feat: add monitor page navigation`
- `fix: handle missing smbus with simulation fallback`
- `docs: update setup instructions`
