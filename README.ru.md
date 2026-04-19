# Sleep Dashboard

Двухстраничное Flask-приложение для анализа сна:

- `"/"`: ML-предиктор эффективности сна (модель XGBoost)
- `"/monitor"`: live-монитор IMU (MPU6050 по I2C + Socket.IO + 3D)

Если MPU6050 недоступен, монитор автоматически переходит в режим симуляции.

## Структура проекта

- `app.py` - backend (Flask + Socket.IO + ML + цикл сенсора)
- `templates/index.html` - страница ML
- `templates/monitor.html` - страница live-монитора
- `xgboost_sleep_model.pkl` - обученная модель
- `run.sh` - защищенный скрипт запуска (автоподбор свободного порта)
- `run.bat` - скрипт запуска для Windows (автоподбор свободного порта)

## Требования

- Linux/macOS (или WSL на Windows)
- Python 3.10+ (проверено на 3.12)
- `git`

Для реальных данных с MPU6050 на Raspberry Pi:

- Включенный I2C (`sudo raspi-config`)
- Корректное подключение датчика (SDA/SCL/3V3/GND)

## Быстрый старт (на любой машине)

```bash
git clone https://github.com/abnzrdev/sleep.git
cd sleep
chmod +x run.sh
./run.sh
```

Откройте:

- `http://127.0.0.1:<port>/`
- `http://127.0.0.1:<port>/monitor`

Скрипт автоматически выберет свободный порт, если `5000` занят.

## Что Такое Порт?

- IP - это адрес устройства в сети (например: `192.168.8.151`).
- Порт - это «номер двери» приложения (например: `5000`, `5001`, `5005`).
- Полная ссылка всегда имеет вид: `http://IP:PORT/`

Если IP Raspberry Pi `192.168.8.151`, а приложение запустилось на порту `5005`, открывайте:

- `http://192.168.8.151:5005/`
- `http://192.168.8.151:5005/monitor`

Можно запускать и напрямую без скриптов; в `app.py` есть встроенный автопереход на свободный порт:

```bash
python app.py --host 0.0.0.0 --port 5000 --max-port 5100
```

## Быстрый старт (Windows)

```bat
git clone https://github.com/abnzrdev/sleep.git
cd sleep
run.bat
```

Опционально (без авто-открытия браузера):

```bat
run.bat --no-open
```

## Запуск с кастомным host/port

```bash
HOST=0.0.0.0 PORT=5000 MAX_PORT=5100 ./run.sh
```

Тогда с другого ПК в той же сети открывайте:

- `http://<ip-сервера>:<выбранный-порт>/`
- `http://<ip-сервера>:<выбранный-порт>/monitor`

Узнать IP сервера на Linux:

```bash
hostname -I
```

## Запуск На Raspberry Pi В Один Клик

Используйте одну команду:

```bash
cd ~/sleep
./start.sh
```

`start.sh` автоматически:

- запускает сервер на `0.0.0.0` (доступ по сети)
- пытается стартовать с `5000`
- при занятости порта переходит к следующему свободному до `5100`
- печатает точные ссылки (Local URL, Network URL, Monitor URL)

Открывайте точный `Network URL`, который напечатан в терминале.

Пример для Windows CMD:

```bat
set HOST=0.0.0.0
set PORT=5000
set MAX_PORT=5100
run.bat
```

Пример для Windows PowerShell:

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "5000"
$env:MAX_PORT = "5100"
.\run.bat
```

## Переменные окружения

- `HOST` - адрес привязки (по умолчанию: `127.0.0.1`)
- `PORT` - стартовый порт (по умолчанию: `5000`)
- `MAX_PORT` - последний порт для поиска (по умолчанию: `5100`)
- `DEBUG` - debug-режим (`0`/`1`, по умолчанию: `0`)
- `TEST_MODE` - режим логики сна (`1` для короткого теста, `0` для реального времени)
- `MOVEMENT_THRESHOLD` - порог движения для логики сон/пробуждение (по умолчанию: `0.05`)

## API (ML предиктор)

`POST /predict` принимает form-data или JSON с точными именами признаков:

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

Референсный результат для тестового payload:

- `prediction_percent`: `87.33`
- `raw_score`: `0.8732507228851318`

## Для реального деплоя с датчиком

- У MPU6050 нет IP-адреса; IP есть только у хоста (например Raspberry Pi).
- Сервер нужно запускать на устройстве, к которому подключен MPU6050.
- Остальные ПК подключаются по IP хоста и порту.

## Raspberry Pi: если порт занят

Если видите `Address already in use`, этот порт уже используется другим процессом.

1. Проверить, кто занял порт `5000`:

```bash
sudo ss -ltnp | grep :5000
```

2. Остановить процесс (замените `PID`):

```bash
sudo kill PID
```

3. Или просто запустить с автоподбором следующего свободного порта:

```bash
HOST=0.0.0.0 PORT=5000 MAX_PORT=5100 ./run.sh
```

4. Узнать IP Raspberry Pi:

```bash
hostname -I
```

## Raspberry Pi: как исправить Sensor warning

Если видите `Sensor warning: [Errno 6] No such device or address`, обычно проблема в настройке I2C/подключении, а не в Flask-коде.

Проверьте на Raspberry Pi:

1. Включите I2C:

```bash
sudo raspi-config
```

Далее: Interface Options -> I2C -> Enable, затем перезагрузка.

2. Проверьте, что есть I2C-устройство:

```bash
ls /dev/i2c-*
```

3. Установите утилиты и просканируйте шину:

```bash
sudo apt update
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```

Обычно адрес MPU6050: `68` (иногда `69`).

4. Если датчик найден на `69`, запускайте так (без правки кода):

```bash
MPU6050_ADDR=0x69 ./start.sh
```

5. Если нужна другая I2C-шина, задайте при старте:

```bash
I2C_BUS=1 ./start.sh
```

Теперь на странице мониторинга в Sensor Source показываются выбранные bus/address при успешном подключении.

## Примеры Conventional Commits

- `feat: add monitor page navigation`
- `fix: handle missing smbus with simulation fallback`
- `docs: update setup instructions`
