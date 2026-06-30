@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ASSUME_YES="
if /I "%~1"=="--yes" set "ASSUME_YES=1"

if not defined ASSUME_YES (
  echo Listener dependency installer
  echo.
  echo This will create a local virtual environment in:
  echo   %CD%\.venv
  echo.
  echo It will download and install Python packages from requirements.txt:
  echo   faster-whisper
  echo   huggingface-hub
  echo   httpx
  echo   sounddevice
  echo   numpy
  echo.
  echo It will NOT download speech recognition models.
  echo Models are downloaded later only when you click "Download model" in the app.
  echo.
  echo GPU note:
  echo   This installer does not install NVIDIA CUDA/cuDNN runtime DLLs.
  echo   If you want GPU mode on Windows, install the NVIDIA runtime required by faster-whisper
  echo   and make sure the DLLs are available on PATH before launching the app.
  echo.
  set /p INSTALL_OK=Continue? [y/N] 
  if /I not "!INSTALL_OK!"=="Y" (
    echo Installation cancelled.
    pause
    exit /b 1
  )
)

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" was not found.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

set "PYLAUNCH=py"
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYLAUNCH=py -3.12"
if "%PYLAUNCH%"=="py" (
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYLAUNCH=py -3.11"
)
if "%PYLAUNCH%"=="py" (
  py -3.10 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYLAUNCH=py -3.10"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  echo Using %PYLAUNCH%
  %PYLAUNCH% -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

echo.
echo Installation complete. You can now run run.cmd.
if not defined ASSUME_YES pause
