import logging
import math
import os
import shlex
import threading
import time
from datetime import datetime

from .config import external_sensor_only_enabled, remote_sender_autocontrol_enabled, valid_port

LOGGER = logging.getLogger("sleep-dashboard")

try:
    import paramiko
except ImportError:
    paramiko = None

try:
    import smbus  # type: ignore
except ImportError:
    try:
        import smbus2 as smbus  # type: ignore
    except ImportError:
        smbus = None


class SensorState:
    DEVICE_ADDRESS = 0x68
    PWR_MGMT_1 = 0x6B
    SMPLRT_DIV = 0x19
    CONFIG = 0x1A
    GYRO_CONFIG = 0x1B
    INT_ENABLE = 0x38
    ACCEL_XOUT_H = 0x3B

    def __init__(self, socketio) -> None:
        self.socketio = socketio
        self.bus = None
        self.sensor_source = "Simulation"
        self.sensor_error = ""
        self.sensor_task_started = False
        self.sensor_lock = threading.Lock()
        self.external_feed_paused = False
        self.external_last_data: dict = {}
        self.external_control_lock = threading.Lock()
        self.external_metrics = {
            "started_at": None,
            "last_ts": None,
            "total_sleep_seconds": 0.0,
            "latest_efficiency": 0.0,
        }
        self.runtime_host = os.getenv("HOST", "127.0.0.1")
        port_value = os.getenv("PORT", "5000")
        self.runtime_port = int(port_value) if port_value.isdigit() else 5000
        self.remote_control_lock = threading.Lock()
        self.device_address = self.DEVICE_ADDRESS

    def set_runtime_address(self, host: str, port: int) -> None:
        self.runtime_host = host
        self.runtime_port = port

    def _event_time_from_payload(self, data: dict) -> float:
        raw = data.get("timestamp")
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return time.time()
        return time.time()

    def _enrich_external_sensor_data(self, data: dict) -> dict:
        now_ts = self._event_time_from_payload(data)

        started_at = self.external_metrics.get("started_at")
        last_ts = self.external_metrics.get("last_ts")

        if started_at is None:
            self.external_metrics["started_at"] = now_ts
            started_at = now_ts

        if last_ts is None:
            dt = 1.0
        else:
            dt = now_ts - float(last_ts)
            if dt <= 0 or dt > 5:
                dt = 1.0

        status_text = str(data.get("status", "")).lower()
        if status_text.startswith("sleeping"):
            self.external_metrics["total_sleep_seconds"] = float(self.external_metrics["total_sleep_seconds"]) + dt

        elapsed = max(now_ts - float(started_at), 1.0)
        efficiency = (float(self.external_metrics["total_sleep_seconds"]) / elapsed) * 100.0

        self.external_metrics["last_ts"] = now_ts
        self.external_metrics["latest_efficiency"] = efficiency

        # Ensure UI always receives an efficiency value, even if sender omits it.
        data["efficiency"] = round(efficiency, 1)
        return data

    def _reset_external_metrics(self) -> None:
        self.external_metrics["started_at"] = None
        self.external_metrics["last_ts"] = None
        self.external_metrics["total_sleep_seconds"] = 0.0
        self.external_metrics["latest_efficiency"] = 0.0

    def _resolve_sender_target(self, request) -> tuple[str, int]:
        target_host = os.getenv("RPI_TARGET_HOST", "").strip()
        target_port_raw = os.getenv("RPI_TARGET_PORT", "").strip()

        if not target_host:
            target_host = request.host.split(":", 1)[0] if request.host else self.runtime_host
            if target_host in {"127.0.0.1", "localhost", "0.0.0.0"}:
                target_host = os.getenv("PUBLIC_HOST", target_host).strip() or target_host

        if target_port_raw:
            try:
                target_port = int(target_port_raw)
            except ValueError as exc:
                raise RuntimeError(f"Invalid RPI_TARGET_PORT: {target_port_raw}") from exc
        else:
            server_port = request.environ.get("SERVER_PORT")
            try:
                target_port = int(server_port) if server_port else self.runtime_port
            except (TypeError, ValueError):
                target_port = self.runtime_port

        if not valid_port(target_port):
            raise RuntimeError(f"Invalid target port: {target_port}")

        return target_host, target_port

    def _run_remote_command(self, command: str, timeout: int = 20) -> tuple[int, str, str]:
        if paramiko is None:
            raise RuntimeError("paramiko is not installed. Run pip install -r requirements.txt")

        host = os.getenv("RPI_SSH_HOST", "192.168.8.151").strip()
        username = os.getenv("RPI_SSH_USER", "admin").strip()
        password = os.getenv("RPI_SSH_PASSWORD", "").strip()
        port_raw = os.getenv("RPI_SSH_PORT", "22").strip()

        if not host:
            raise RuntimeError("RPI_SSH_HOST is required")
        if not username:
            raise RuntimeError("RPI_SSH_USER is required")
        if not password:
            raise RuntimeError("RPI_SSH_PASSWORD is required")

        try:
            port = int(port_raw)
        except ValueError as exc:
            raise RuntimeError(f"Invalid RPI_SSH_PORT: {port_raw}") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                look_for_keys=False,
                allow_agent=False,
                timeout=10,
            )
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return exit_code, out, err
        except Exception as exc:
            raise RuntimeError(f"SSH command failed: {exc}") from exc
        finally:
            client.close()

    def _remote_sender_start(self, target_host: str, target_port: int) -> dict:
        sender_python = os.getenv("RPI_SEND_PYTHON", "python")
        sender_script = os.getenv("RPI_SEND_SCRIPT", "send.py")
        sender_workdir = os.getenv("RPI_SEND_WORKDIR", "~")
        sender_pid_file = os.getenv("RPI_SENDER_PID_FILE", "/tmp/sleep_sender.pid")
        sender_log_file = os.getenv("RPI_SENDER_LOG_FILE", "/tmp/sleep_sender.log")
        extra_args = os.getenv("RPI_SEND_EXTRA_ARGS", "").strip()

        sender_cmd = (
            f"{shlex.quote(sender_python)} {shlex.quote(sender_script)} "
            f"--host {shlex.quote(target_host)} --port {target_port}"
        )
        if extra_args:
            sender_cmd = f"{sender_cmd} {extra_args}"

        remote_cmd = (
            "set -e; "
            f"PID_FILE={shlex.quote(sender_pid_file)}; "
            f"LOG_FILE={shlex.quote(sender_log_file)}; "
            f"cd {shlex.quote(sender_workdir)}; "
            "if [ -f \"$PID_FILE\" ] && kill -0 \"$(cat \"$PID_FILE\")\" 2>/dev/null; then "
            "echo already_running; "
            "else "
            f"nohup {sender_cmd} >> \"$LOG_FILE\" 2>&1 & echo $! > \"$PID_FILE\"; "
            "echo started; "
            "fi"
        )

        exit_code, out, err = self._run_remote_command(remote_cmd)
        if exit_code != 0:
            raise RuntimeError(f"Remote start failed: {err or out or 'unknown error'}")

        state = "started" if "started" in out else "already_running"
        return {
            "state": state,
            "target_host": target_host,
            "target_port": target_port,
            "log_file": sender_log_file,
            "pid_file": sender_pid_file,
        }

    def _remote_sender_stop(self) -> dict:
        sender_pid_file = os.getenv("RPI_SENDER_PID_FILE", "/tmp/sleep_sender.pid")

        remote_cmd = (
            "set -e; "
            f"PID_FILE={shlex.quote(sender_pid_file)}; "
            "if [ -f \"$PID_FILE\" ]; then "
            "PID=\"$(cat \"$PID_FILE\")\"; "
            "kill \"$PID\" 2>/dev/null || true; "
            "rm -f \"$PID_FILE\"; "
            "echo stopped; "
            "else "
            "echo not_running; "
            "fi"
        )

        exit_code, out, err = self._run_remote_command(remote_cmd)
        if exit_code != 0:
            raise RuntimeError(f"Remote stop failed: {err or out or 'unknown error'}")

        return {"state": "stopped" if "stopped" in out else "not_running"}

    def mpu_init(self) -> None:
        if self.bus is None:
            raise RuntimeError("I2C bus not initialized.")

        self.bus.write_byte_data(self.device_address, self.SMPLRT_DIV, 7)
        self.bus.write_byte_data(self.device_address, self.PWR_MGMT_1, 1)
        self.bus.write_byte_data(self.device_address, self.CONFIG, 0)
        self.bus.write_byte_data(self.device_address, self.GYRO_CONFIG, 24)
        self.bus.write_byte_data(self.device_address, self.INT_ENABLE, 1)

    def read_raw_data(self, addr: int) -> int:
        if self.bus is None:
            raise RuntimeError("I2C bus not initialized.")

        high = self.bus.read_byte_data(self.device_address, addr)
        low = self.bus.read_byte_data(self.device_address, addr + 1)
        value = (high << 8) | low
        if value > 32768:
            value -= 65536
        return value

    def init_sensor_source(self) -> None:
        if external_sensor_only_enabled():
            self.bus = None
            self.sensor_source = "External sensor feed (waiting for data)"
            self.sensor_error = ""
            LOGGER.info("EXTERNAL_SENSOR_ONLY enabled - waiting for external sensor data")
            return

        if smbus is None:
            self.sensor_source = "Simulation (smbus unavailable)"
            self.sensor_error = "smbus module not installed."
            LOGGER.warning("smbus module not available - running in simulation mode")
            return

        try:
            bus_number = int(os.getenv("I2C_BUS", "1"))
        except ValueError:
            self.sensor_source = "Simulation (invalid I2C config)"
            self.sensor_error = "I2C_BUS must be an integer. Example: I2C_BUS=1"
            LOGGER.error("Invalid I2C_BUS configuration - running in simulation mode: %s", self.sensor_error)
            return

        raw_addr = os.getenv("MPU6050_ADDR", "0x68")
        try:
            device_address = int(raw_addr, 0)
        except ValueError:
            self.sensor_source = "Simulation (invalid I2C config)"
            self.sensor_error = "MPU6050_ADDR must be numeric (for example 0x68)."
            LOGGER.error("Invalid MPU6050_ADDR configuration - running in simulation mode: %s", self.sensor_error)
            return

        if not (0 <= device_address <= 0x7F):
            self.sensor_source = "Simulation (invalid I2C config)"
            self.sensor_error = "MPU6050_ADDR must be in 0x00..0x7F range."
            LOGGER.error("Invalid MPU6050_ADDR range - running in simulation mode: %s", self.sensor_error)
            return

        try:
            self.device_address = device_address
            self.bus = smbus.SMBus(bus_number)
            self.mpu_init()
            self.sensor_source = f"MPU6050 (I2C bus {bus_number}, addr 0x{self.device_address:02X})"
            self.sensor_error = ""
            LOGGER.info(
                "Successfully initialized MPU6050 sensor on I2C bus %s at address 0x%02X",
                bus_number,
                self.device_address,
            )
        except Exception as exc:
            self.bus = None
            self.sensor_source = f"Simulation (MPU6050 offline on bus {bus_number})"
            self.sensor_error = str(exc)
            LOGGER.error("Failed to initialize MPU6050 sensor - running in simulation mode. Error: %s", exc)

    def read_accelerometer(self) -> tuple[float, float, float]:
        if self.bus is not None:
            acc_x = self.read_raw_data(self.ACCEL_XOUT_H) / 16384.0
            acc_y = self.read_raw_data(self.ACCEL_XOUT_H + 2) / 16384.0
            acc_z = self.read_raw_data(self.ACCEL_XOUT_H + 4) / 16384.0
            return acc_x, acc_y, acc_z

        # Fallback simulation keeps the UI alive even without hardware.
        t = time.time()
        acc_x = 0.05 * math.sin(t / 2.0)
        acc_y = 0.04 * math.cos(t / 2.6)
        acc_z = 1.00 + 0.02 * math.sin(t / 3.3)
        return acc_x, acc_y, acc_z

    def sensor_loop(self) -> None:
        test_mode = os.getenv("TEST_MODE", "1").lower() in {"1", "true", "yes", "on"}
        movement_threshold = float(os.getenv("MOVEMENT_THRESHOLD", "0.05"))

        if test_mode:
            time_to_fall_asleep = 10
            time_to_wake_up = 3
        else:
            time_to_fall_asleep = 10 * 60
            time_to_wake_up = 30

        start_bed_time = time.time()
        is_sleeping = False
        total_sleep_seconds = 0
        awakenings_count = 0
        quiet_seconds = 0
        active_seconds = 0
        prev_acc_mag = 0.0
        first_sleep_time = "--:--:--"

        while True:
            try:
                acc_x, acc_y, acc_z = self.read_accelerometer()

                try:
                    roll = math.atan2(acc_y, acc_z)
                    pitch = math.atan2(-acc_x, math.sqrt(acc_y * acc_y + acc_z * acc_z))
                except Exception:
                    roll, pitch = 0.0, 0.0

                acc_mag = math.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
                movement = abs(acc_mag - prev_acc_mag)
                prev_acc_mag = acc_mag

                if movement > movement_threshold:
                    active_seconds += 1
                    quiet_seconds = 0
                else:
                    quiet_seconds += 1
                    active_seconds = 0

                if not is_sleeping:
                    if quiet_seconds >= time_to_fall_asleep:
                        is_sleeping = True
                        if first_sleep_time == "--:--:--":
                            first_sleep_time = datetime.now().strftime("%H:%M:%S")
                        active_seconds = 0
                else:
                    total_sleep_seconds += 1
                    if active_seconds >= time_to_wake_up:
                        is_sleeping = False
                        awakenings_count += 1
                        quiet_seconds = 0

                total_time_in_bed = time.time() - start_bed_time
                efficiency = (total_sleep_seconds / total_time_in_bed) * 100 if total_time_in_bed > 0 else 0

                sensor_data = {
                    "status": "Sleeping zZz" if is_sleeping else "Awake",
                    "movement": round(movement, 3),
                    "first_sleep": first_sleep_time,
                    "awakenings": awakenings_count,
                    "efficiency": round(efficiency, 1),
                    "pitch": pitch,
                    "roll": roll,
                    "x": f"{acc_x:.2f}",
                    "y": f"{acc_y:.2f}",
                    "z": f"{acc_z:.2f}",
                    "sensor_source": self.sensor_source,
                }
                self.socketio.emit("sensor_update", sensor_data)
                self.socketio.sleep(1)
            except OSError:
                # Hardware read error; keep server alive and retry.
                self.socketio.sleep(1)

    def ensure_sensor_task_started(self) -> None:
        with self.sensor_lock:
            if self.sensor_task_started:
                return
            self.socketio.start_background_task(self.sensor_loop)
            self.sensor_task_started = True

    def receive_sensor_data(self, data: dict) -> tuple[dict, int]:
        if not data:
            return {"success": False, "error": "JSON body is required."}, 400

        with self.external_control_lock:
            paused = self.external_feed_paused
            if not paused:
                enriched = self._enrich_external_sensor_data(dict(data))
                self.external_last_data = dict(enriched)
            else:
                enriched = dict(data)

        if paused:
            return {"success": True, "paused": True, "message": "Feed is paused."}, 202

        self.socketio.emit("sensor_update", enriched)
        return {"success": True, "paused": False}, 200

    def stop_sensor_feed(self) -> dict:
        with self.external_control_lock:
            self.external_feed_paused = True
            snapshot = dict(self.external_last_data)

        remote = None
        remote_error = ""
        if external_sensor_only_enabled() and remote_sender_autocontrol_enabled():
            with self.remote_control_lock:
                try:
                    remote = self._remote_sender_stop()
                except Exception as exc:
                    remote_error = str(exc)
                    LOGGER.exception("Failed to stop remote sender")

        if snapshot:
            snapshot["status"] = "Stopped"
            snapshot["sensor_source"] = snapshot.get("sensor_source", "External sensor feed (stopped)")
        else:
            snapshot = {
                "status": "Stopped",
                "movement": 0.0,
                "first_sleep": "--:--:--",
                "awakenings": 0,
                "efficiency": 0,
                "pitch": 0.0,
                "roll": 0.0,
                "x": "0.00",
                "y": "0.00",
                "z": "0.00",
                "sensor_source": "External sensor feed (stopped)",
            }

        self.socketio.emit("sensor_update", snapshot)
        return {
            "success": True,
            "paused": True,
            "snapshot": snapshot,
            "remote": remote,
            "remote_error": remote_error,
        }

    def start_sensor_feed(self, request) -> tuple[dict, int]:
        remote = None
        if external_sensor_only_enabled() and remote_sender_autocontrol_enabled():
            target_host, target_port = self._resolve_sender_target(request)
            with self.remote_control_lock:
                try:
                    remote = self._remote_sender_start(target_host, target_port)
                except Exception as exc:
                    LOGGER.exception("Failed to start remote sender")
                    return {"success": False, "paused": True, "error": str(exc)}, 502

        with self.external_control_lock:
            self.external_feed_paused = False
            self.external_last_data = {}
            self._reset_external_metrics()

        return {"success": True, "paused": False, "remote": remote}, 200
