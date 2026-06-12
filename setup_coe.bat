@echo off
setlocal

:: ==============================================================================
:: AICOE EDUCATION - UNIVERSAL INITIALIZATION SCRIPT
:: ==============================================================================
:: This script prepares the local environment for the AI Grievance System.
:: ARCHITECTURE:
:: - Local Inference: Powered by Ollama (GPU-accelerated on host).
:: - Embeddings/RAG: GPU-accelerated (via CUDA) if detected, otherwise CPU fallback.
:: - Resource Management: Interactive Chatbot tasks take priority over OCR/Triage.
:: ==============================================================================

echo 🔍 Initializing System...

:: 1. Detect Python (Supports standard paths and common Windows installations)
set PYTHON_CMD=python
:: Try to use the Python Launcher for Windows to grab the latest Python 3.x
py -3 --version >nul 2>&1 && set PYTHON_CMD=py -3
:: Explicitly prefer 3.12, 3.11, 3.10, 3.9 if installed in standard locations
if exist "C:\Program Files\Python312\python.exe" set PYTHON_CMD="C:\Program Files\Python312\python.exe"
if exist "C:\Program Files\Python311\python.exe" set PYTHON_CMD="C:\Program Files\Python311\python.exe"
if exist "C:\Program Files\Python310\python.exe" set PYTHON_CMD="C:\Program Files\Python310\python.exe"

echo 🔍 Using Python Command: %PYTHON_CMD%
%PYTHON_CMD% --version

:: Validate Python Version >= 3.9
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)"
if errorlevel 1 (
    echo.
    echo ❌ ERROR: Python 3.9 or higher is STRICTLY REQUIRED!
    echo    Google GenAI SDK dropped support for Python 3.8.
    echo    Please upgrade your Python installation or explicitly point to Python 3.9+.
    echo.
    pause
    exit /b 1
)

:: 2. Create venv if not exists
if not exist "backend\venv" (
    echo 🛠️ Creating Virtual Environment...
    %PYTHON_CMD% -m venv backend\venv
)

:: 3. Activate venv (for interactive shell users, optional for this script's execution)
echo 🔌 Activating Virtual Environment...
call backend\venv\Scripts\activate.bat

:: Define explicit path to the venv's python to guarantee packages are installed in the right place!
set VENV_PYTHON=backend\venv\Scripts\python.exe

:: 4. Upgrade pip inside the venv
echo 🆙 Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip

:: 5. Install Dependencies
echo 📚 Detecting Hardware for Optimal AI performance...

:: Check for NVIDIA GPU to prevent DLL initialization errors (WinError 1114)
wmic path win32_VideoController get name | findstr /i "NVIDIA" >nul 2>&1
if %errorlevel% == 0 (
    echo 🚀 NVIDIA GPU Detected! Installing High-Performance PyTorch (CUDA 12.4)...
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
) else (
    echo 💻 AMD or Standard Hardware Detected. Installing standard CPU PyTorch...
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
)

echo 📚 Finalizing dependencies from requirements.txt...
"%VENV_PYTHON%" -m pip install -r backend\requirements.txt

:: 5. Finalize
echo ========================================================
echo ✅ Setup Complete!
echo.
echo TO START THE SYSTEM NATIVELY:
echo 1. Ensure Ollama is running on your host.
echo 2. Run: python backend/main.py
echo.
echo TO START VIA DOCKER:
echo 1. Run: docker compose up --build -d
echo ========================================================
pause
