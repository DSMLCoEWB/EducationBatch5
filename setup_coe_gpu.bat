@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo 🚀 AI Grievance System - COE GPU Smart Setup
echo ======================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Python is not installed or not in PATH.
    pause
    exit /b
)

:: 2. Create Virtual Environment
if not exist "backend\venv" (
    echo 📦 Creating Virtual Environment in backend\venv...
    python -m venv backend\venv
) else (
    echo ✅ Virtual Environment already exists in backend\venv.
)

:: 3. Activate venv
echo 🔌 Activating Virtual Environment...
call backend\venv\Scripts\activate.bat

:: 4. Upgrade pip
echo 🆙 Upgrading pip...
python -m pip install --upgrade pip

:: 5. GPU Detection and PyTorch Installation
echo 🔍 Checking for NVIDIA GPU...
nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    :: Install the absolute latest 2026 suite for NVIDIA/CUDA 12.6
    pip install torch==2.11.0 torchvision==0.26.0 transformers sentence-transformers accelerate --index-url https://download.pytorch.org/whl/cu126
) else (
    echo ℹ️ No NVIDIA GPU found or drivers not installed. Installing CPU version.
    pip install torch transformers sentence-transformers accelerate
)

:: 6. Install remaining requirements
echo 📚 Installing dependencies from requirements.txt...
pip install -r backend\requirements.txt

:: 7. Success
echo.
echo ======================================================
echo ✅ SETUP COMPLETE!
echo.
echo To start the backend, run:
echo    cd backend
echo    venv\Scripts\python main.py
echo ======================================================
pause
