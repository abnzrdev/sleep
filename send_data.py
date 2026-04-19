import requests
import time
import math
from datetime import datetime
import argparse

try:
    import smbus
except ImportError:
    print("Error: smbus library not found. Please install it with 'pip install smbus-cffi'")
    exit(1)

# --- MPU6050 SETTINGS ---
Device_Address = 0x68   # MPU6050 Address
try:
    bus = smbus.SMBus(1)    # Initialize I2C bus
except FileNotFoundError:
    print("Error: I2C bus not found. Make sure I2C is enabled (raspi-config).")
    exit(1)

# Registers
PWR_MGMT_1   = 0x6B
SMPLRT_DIV   = 0x19
CONFIG       = 0x1A
GYRO_CONFIG  = 0x1B
INT_ENABLE   = 0x38
ACCEL_XOUT_H = 0x3B

def MPU_Init():
    """Initializes the MPU6050 sensor."""
    bus.write_byte_data(Device_Address, SMPLRT_DIV, 7)
    bus.write_byte_data(Device_Address, PWR_MGMT_1, 1)
    bus.write_byte_data(Device_Address, CONFIG, 0)
    bus.write_byte_data(Device_Address, GYRO_CONFIG, 24)
    bus.write_byte_data(Device_Address, INT_ENABLE, 1)

def read_raw_data(addr):
    """Reads raw data from the MPU6050 sensor."""
    high = bus.read_byte_data(Device_Address, addr)
    low = bus.read_byte_data(Device_Address, addr+1)
    value = ((high << 8) | low)
    if(value > 32768):
        value = value - 65536
    return value

# --- SLEEP ALGORITHM SETTINGS ---
TEST_MODE = True 
MOVEMENT_THRESHOLD = 0.05 # Threshold for movement detection (in g)

if TEST_MODE:
    TIME_TO_FALL_ASLEEP = 10  # 10 seconds of inactivity = asleep
    TIME_TO_WAKE_UP = 3       # 3 seconds of activity = awake
else:
    TIME_TO_FALL_ASLEEP = 10 * 60  # 10 minutes of inactivity = asleep
    TIME_TO_WAKE_UP = 30           # 30 seconds of activity = awake (tossing and turning)

# --- SLEEP STATE VARIABLES ---
start_bed_time = time.time()
is_sleeping = False

time_of_sleep_onset = None
total_sleep_seconds = 0
awakenings_count = 0

quiet_seconds = 0
active_seconds = 0
prev_acc_mag = 0

def send_data_to_server(server_url, data):
    """Sends data to the server."""
    try:
        response = requests.post(server_url, json=data, timeout=5)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Data sent successfully.")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error sending data: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error sending data: {e}")

def main(server_url):
    """Main function to run the sleep monitoring."""
    global is_sleeping, time_of_sleep_onset, total_sleep_seconds, awakenings_count, quiet_seconds, active_seconds, prev_acc_mag

    try:
        MPU_Init()
    except OSError:
        print("Error: MPU6050 sensor not found at address 0x68. Check connection.")
        exit(1)

    print("="*50)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] SLEEP MONITORING STARTED")
    print(f"Test Mode: {'ON (seconds)' if TEST_MODE else 'OFF (minutes)'}")
    print("Place the sensor still to simulate falling asleep. Shake to wake up.")
    print("Press Ctrl+C to stop monitoring and see results.")
    print("="*50)

    try:
        while True:
            acc_x = read_raw_data(ACCEL_XOUT_H) / 16384.0
            acc_y = read_raw_data(ACCEL_XOUT_H + 2) / 16384.0
            acc_z = read_raw_data(ACCEL_XOUT_H + 4) / 16384.0
            
            acc_mag = math.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
            movement = abs(acc_mag - prev_acc_mag)
            prev_acc_mag = acc_mag

            if movement > MOVEMENT_THRESHOLD:
                active_seconds += 1
                quiet_seconds = 0
            else:
                quiet_seconds += 1
                active_seconds = 0

            if not is_sleeping:
                if quiet_seconds >= TIME_TO_FALL_ASLEEP:
                    is_sleeping = True
                    if time_of_sleep_onset is None:
                        time_of_sleep_onset = datetime.now()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ---> SLEEP DETECTED (Quiet: {quiet_seconds}s)")
                    active_seconds = 0
            
            else: # If currently sleeping
                total_sleep_seconds += 1
                if active_seconds >= TIME_TO_WAKE_UP:
                    is_sleeping = False
                    awakenings_count += 1
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ---> AWAKENING DETECTED (Active: {active_seconds}s)")
                    quiet_seconds = 0

            roll = math.atan2(acc_y, acc_z)
            pitch = math.atan2(-acc_x, math.sqrt(acc_y * acc_y + acc_z * acc_z))

            status_text = "SLEEPING zZz" if is_sleeping else "AWAKE"
            print(f"Movement: {movement:.3f}g | Status: {status_text}")

            total_time_in_bed = time.time() - start_bed_time
            efficiency = (total_sleep_seconds / total_time_in_bed) * 100 if total_time_in_bed > 0 else 0

            data = {
                "status": "Sleeping zZz" if is_sleeping else "Awake",
                "movement": round(movement, 3),
                "first_sleep": time_of_sleep_onset.strftime("%H:%M:%S") if time_of_sleep_onset else "--:--:--",
                "awakenings": awakenings_count,
                "efficiency": round(efficiency, 1),
                "timestamp": datetime.now().isoformat(),
                "pitch": pitch,
                "roll": roll,
                "x": f"{acc_x:.2f}",
                "y": f"{acc_y:.2f}",
                "z": f"{acc_z:.2f}",
                "sensor_source": f"Pi @ {args.host}",
            }
            send_data_to_server(server_url, data)
            
            time.sleep(1)

    except KeyboardInterrupt:
        end_bed_time = time.time()
        total_time_in_bed_sec = end_bed_time - start_bed_time
        
        sleep_efficiency = (total_sleep_seconds / total_time_in_bed_sec) * 100 if total_time_in_bed_sec > 0 else 0

        print("\n" + "="*50)
        print("🌅 MONITORING FINISHED (SLEEP SUMMARY)")
        print("="*50)
        
        if time_of_sleep_onset:
            print(f"🕒 First time asleep: {time_of_sleep_onset.strftime('%H:%M:%S')}")
        else:
            print("🕒 First time asleep: Not recorded (user did not fall asleep)")
            
        print(f"🛏  Total time in bed:   {total_time_in_bed_sec:.1f}s")
        print(f"💤 Net sleep time:        {total_sleep_seconds:.1f}s")
        print(f"🔔 Number of awakenings:  {awakenings_count}")
        print(f"📈 Sleep efficiency:       {sleep_efficiency:.1f}%")
        print("="*50)

    except OSError:
        print("\nError: Sensor lost. Check I2C wires (SDA/SCL).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send MPU6050 data to a server.")
    parser.add_argument("--host", default="127.0.0.1", help="The hostname or IP address of the server.")
    parser.add_argument("--port", type=int, default=5000, help="The port of the server.")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/sensor_data"
    main(url)
