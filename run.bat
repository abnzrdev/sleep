@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

call :load_env_file ".env"
call :load_env_file ".env.local"

set "OPEN_BROWSER=1"
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--no-open" (
  set "OPEN_BROWSER=0"
  shift
  goto parse_args
)
echo Unknown option: %~1
echo Usage: run.bat [--no-open]
exit /b 1

:args_done
set "PYTHON_CMD="
where py >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>&1 && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo Python 3 is required but was not found on PATH.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  call %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    exit /b 1
  )
)

set "PYEXE=.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo Virtual environment python executable not found: %PYEXE%
  exit /b 1
)

if not exist "requirements.txt" (
  echo requirements.txt not found.
  exit /b 1
)

set "REQ_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -Path 'requirements.txt').Hash"`) do (
  set "REQ_HASH=%%H"
)

set "REQ_HASH_FILE=.venv\requirements.sha256"
set "NEED_INSTALL=1"

if defined REQ_HASH if exist "%REQ_HASH_FILE%" (
  set /p SAVED_HASH=<"%REQ_HASH_FILE%"
  if /I "!SAVED_HASH!"=="!REQ_HASH!" set "NEED_INSTALL=0"
)

if "%NEED_INSTALL%"=="1" (
  echo Installing dependencies from requirements.txt...
  call "%PYEXE%" -m pip install --disable-pip-version-check --no-input -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
  )
  if defined REQ_HASH (
    > "%REQ_HASH_FILE%" echo(!REQ_HASH!
  )
) else (
  echo Dependencies are already up to date.
)

if defined PORT (
  set "START_PORT=%PORT%"
) else (
  set "START_PORT=5000"
)

if defined MAX_PORT (
  set "MAX_PORT_VALUE=%MAX_PORT%"
) else (
  set "MAX_PORT_VALUE=5100"
)

if defined HOST (
  set "HOST_VALUE=%HOST%"
) else (
  set "HOST_VALUE=127.0.0.1"
)

call :validate_port "%START_PORT%"
if errorlevel 1 (
  echo Invalid PORT value: %START_PORT%
  exit /b 1
)

call :validate_port "%MAX_PORT_VALUE%"
if errorlevel 1 (
  echo Invalid MAX_PORT value: %MAX_PORT_VALUE%
  exit /b 1
)

if %START_PORT% GTR %MAX_PORT_VALUE% (
  echo PORT (%START_PORT%) must be less than or equal to MAX_PORT (%MAX_PORT_VALUE%).
  exit /b 1
)

set "AVAILABLE_PORT="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$start=[int]$env:START_PORT; $end=[int]$env:MAX_PORT_VALUE; $hostValue=$env:HOST_VALUE; $ip=[System.Net.IPAddress]::Loopback; if($hostValue -eq '0.0.0.0'){ $ip=[System.Net.IPAddress]::Any } else { $parsed=$null; if([System.Net.IPAddress]::TryParse($hostValue, [ref]$parsed)){ $ip=$parsed } }; for($p=$start; $p -le $end; $p++){ try { $listener=[System.Net.Sockets.TcpListener]::new($ip,$p); $listener.Start(); $listener.Stop(); Write-Output $p; exit 0 } catch {} }; exit 1"`) do (
  set "AVAILABLE_PORT=%%P"
)

if not defined AVAILABLE_PORT (
  echo No free port found in range %START_PORT%-%MAX_PORT_VALUE%.
  exit /b 1
)

set "OPEN_HOST=%HOST_VALUE%"
if "%OPEN_HOST%"=="0.0.0.0" set "OPEN_HOST=127.0.0.1"
set "APP_URL=http://%OPEN_HOST%:%AVAILABLE_PORT%"

echo Starting Sleep Efficiency Predictor on %APP_URL%

if "%OPEN_BROWSER%"=="1" (
  start "" "%APP_URL%" >nul 2>&1
)

set "HOST=%HOST_VALUE%"
set "PORT=%AVAILABLE_PORT%"
if not defined DEBUG set "DEBUG=0"

call "%PYEXE%" app.py
exit /b %ERRORLEVEL%

:load_env_file
set "ENV_FILE=%~1"
if not exist "%ENV_FILE%" exit /b 0

for /f "usebackq tokens=* delims=" %%L in ("%ENV_FILE%") do (
  call :process_env_line "%%L"
)
echo Loaded config: %ENV_FILE%
exit /b 0

:process_env_line
set "RAW_LINE=%~1"
if not defined RAW_LINE exit /b 0

for /f "tokens=* delims= " %%A in ("%RAW_LINE%") do set "RAW_LINE=%%A"
if not defined RAW_LINE exit /b 0
if "!RAW_LINE:~0,1!"=="#" exit /b 0

if /I "!RAW_LINE:~0,7!"=="export " set "RAW_LINE=!RAW_LINE:~7!"

for /f "tokens=1,* delims==" %%K in ("!RAW_LINE!") do (
  set "ENV_KEY=%%K"
  set "ENV_VAL=%%L"
)

if not defined ENV_KEY exit /b 0
if not defined ENV_VAL exit /b 0

call :trim_var ENV_KEY
call :trim_var ENV_VAL

if not defined ENV_KEY exit /b 0

if "!ENV_VAL:~0,1!"=="\"" if "!ENV_VAL:~-1!"=="\"" set "ENV_VAL=!ENV_VAL:~1,-1!"
if "!ENV_VAL:~0,1!"=="'" if "!ENV_VAL:~-1!"=="'" set "ENV_VAL=!ENV_VAL:~1,-1!"

set "%ENV_KEY%=%ENV_VAL%"
exit /b 0

:trim_var
set "TRIM_TARGET=%~1"
if not defined %TRIM_TARGET% exit /b 0

for /f "tokens=* delims= " %%A in ("!%TRIM_TARGET%!") do set "%TRIM_TARGET%=%%A"
:trim_var_right
if not defined %TRIM_TARGET% exit /b 0
if "!%TRIM_TARGET%:~-1!"==" " (
  set "%TRIM_TARGET%=!%TRIM_TARGET%:~0,-1!"
  goto trim_var_right
)
exit /b 0

:validate_port
set "PORT_CANDIDATE=%~1"
if "%PORT_CANDIDATE%"=="" exit /b 1
for /f "delims=0123456789" %%A in ("%PORT_CANDIDATE%") do exit /b 1
if %PORT_CANDIDATE% LSS 1 exit /b 1
if %PORT_CANDIDATE% GTR 65535 exit /b 1
exit /b 0
