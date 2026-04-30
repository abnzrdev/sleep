# 🛌 Sleep Command

Flask app for sleep efficiency prediction, live sleep sensor monitoring, and an AI sleep advisor.

## ✨ What It Does

- 🧠 Predicts sleep efficiency from 11 sleep and lifestyle inputs.
- 📟 Shows live MPU6050-style sensor telemetry on `/monitor`.
- 💬 Adds an AI sleep advisor on `/chat` using NVIDIA NIM.
- 🔐 Includes login/register auth with SQLite storage.

## ⚡ Quick Start

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the generated value into `.env` as `SECRET_KEY=...`.

```bash
./run.sh
```

The script creates `.venv`, installs dependencies, finds a free port, starts the app, and prints the URLs.

## 🧭 Commands

```bash
./run.sh              # 🚀 Start app and open browser
./run.sh --no-open    # 🖥️ Start app without opening browser
./run.sh --help       # ❔ Show command help
./start.sh            # 📡 Start with LAN/Pi-friendly defaults
./help                # 📘 Project-local help launcher
```

Windows:

```bat
run.bat
run.bat --no-open
```

## 🌐 Show Friends On Same Wi-Fi

Set this in `.env`:

```env
HOST=0.0.0.0
PORT=5000
DEBUG=0
```

Run:

```bash
./run.sh --no-open
```

Share the printed `Network URL`, for example `http://10.17.17.30:5000`.

## 🔑 Environment

- `SECRET_KEY` signs sessions and CSRF tokens. Use a private random value.
- `NIM_API_KEY` enables the AI chat. Use your NVIDIA key: `NIM_API_KEY=nvapi-...`
- `HOST=127.0.0.1` means only your computer can open it.
- `HOST=0.0.0.0` means other devices on the same network can open it.
- `DEBUG=1` is for local development only.
- `DEBUG=0` is for demos or sharing on Wi-Fi.

## 📍 Pages

- `/` - 🧠 predictor
- `/chat` - 💬 AI sleep advisor
- `/monitor` - 📟 live sensor monitor
- `/login` - 🔐 sign in
- `/register` - 📝 create account

## 🍓 Raspberry Pi Sensor

Configure these in `.env` if you use remote sensor control:

```env
RPI_AUTOCONTROL=1
RPI_SSH_HOST=192.168.8.151
RPI_SSH_PORT=22
RPI_SSH_USER=admin
RPI_SSH_PASSWORD=12345678
RPI_SEND_WORKDIR=/home/admin
RPI_SEND_SCRIPT=scripts/send_data.py
RPI_SEND_PYTHON=python
```

Use `./start.sh` when running in a Pi/LAN-style setup.

## 🧪 Stack

- Python 3.12
- Flask, Jinja2, HTMX, Tailwind CSS
- Flask-Login, Flask-SQLAlchemy, SQLite
- Flask-SocketIO, Three.js
- XGBoost, pandas, joblib
- OpenAI Python SDK with NVIDIA NIM
