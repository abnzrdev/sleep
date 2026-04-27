# Sleep Dashboard

## Project Overview

This project is a Flask web app with two main features:

- A sleep efficiency predictor that uses an XGBoost model to estimate sleep efficiency from user input.
- A live sensor monitor that displays motion and sleep state data from an MPU6050 sensor in real time.

The predictor is available on `/`, and the live monitor is available on `/monitor`.

## Tech Stack

- Flask
- Flask-SocketIO
- XGBoost
- MPU6050
- Paramiko

## Requirements

- Python 3.10+
- `pip`

## Setup

1. Clone the repository:

```bash
git clone https://github.com/abnzrdev/sleep.git
cd sleep
```

2. Create a virtual environment:

```bash
python -m venv venv
```

3. Activate the virtual environment:

Linux/macOS:

```bash
source venv/bin/activate
```

Windows:

```bat
venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Copy the environment template and fill in your values:

```bash
cp .env.example .env
```

## Running the App

Start the app with:

```bash
python app.py
```

By default, the app serves:

- `/` for the predictor
- `/monitor` for the live sensor monitor

## Environment Variables

The following variables are defined in `.env.example`:

- `HOST`: Host address for the Flask app.
- `PORT`: Preferred port for the app.
- `MAX_PORT`: Highest port to try if the preferred port is busy.
- `DEBUG`: Enables Flask debug mode when set to `1`.
- `RPI_AUTOCONTROL`: Enables remote start and stop control for the Raspberry Pi sender.
- `RPI_SSH_HOST`: Raspberry Pi SSH host or IP address.
- `RPI_SSH_PORT`: Raspberry Pi SSH port.
- `RPI_SSH_USER`: Raspberry Pi SSH username.
- `RPI_SSH_PASSWORD`: Raspberry Pi SSH password.
- `RPI_SEND_WORKDIR`: Remote working directory where the sender script is located.
- `RPI_SEND_SCRIPT`: Remote sender script name or path.
- `RPI_SEND_PYTHON`: Python executable to use on the Raspberry Pi.
- `RPI_TARGET_HOST`: Optional override for the host that receives sensor data.
- `RPI_TARGET_PORT`: Optional override for the port that receives sensor data.

## Pages

### `/`

The home page is the sleep efficiency predictor. It collects sleep and lifestyle inputs and returns a predicted sleep efficiency score from the trained model.

### `/monitor`

The monitor page shows live motion, orientation, sleep state, awakenings, and efficiency updates from the sensor feed using Socket.IO.

## Raspberry Pi Setup

The Raspberry Pi can run `scripts/send_data.py` to read data from the MPU6050 sensor and post it to this app. If you want the dashboard to start and stop the sender remotely over SSH, configure the SSH-related variables in `.env`.

If your Raspberry Pi uses `scripts/send_data.py`, set:

```env
RPI_SEND_SCRIPT=scripts/send_data.py
```

Make sure SSH access is enabled on the Raspberry Pi and the values for `RPI_SSH_HOST`, `RPI_SSH_PORT`, `RPI_SSH_USER`, and `RPI_SSH_PASSWORD` are correct.
