@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Listener needs a local Python virtual environment before it can run.
  echo.
  echo The installer will create:
  echo   .venv\
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
  echo   GPU mode is enabled only when CTranslate2 can see a CUDA device at app startup.
  echo.
  set /p INSTALL_NOW=Create the environment and install dependencies now? [y/N] 
  if /I not "!INSTALL_NOW!"=="Y" (
    echo Installation cancelled.
    pause
    exit /b 1
  )
  call install.cmd --yes
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" faster_whisper_gui.py
