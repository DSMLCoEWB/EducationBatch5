@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo 🚀 AI Grievance System - COE AMD/Intel GPU Setup
echo ======================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Python is not installed.
    pause
    exit /b
)

:: 2. Create Virtual Environment
if not exist "backend\venv" (
    echo 📦 Creating Virtual Environment in backend\venv...
    python -m venv backend\venv
)

:: 3. Activate venv
echo 🔌 Activating Virtual Environment...
call backend\venv\Scripts\activate.bat

:: 4. Upgrade pip
echo 🆙 Upgrading pip...
python -m pip install --upgrade pip

:: 5. AMD/Intel GPU Support Installation
echo 🏎️ Installing DirectML Acceleration (Torch 2.3.1 Suite)...
pip install torch==2.3.1 torchvision==0.18.1 transformers==4.41.2 sentence-transformers==2.7.0 accelerate
pip install torch-directml

:: 6. Install remaining requirements
echo 📚 Installing dependencies...
pip install -r backend\requirements.txt

:: 7. Success
echo.
echo ======================================================
echo ✅ AMD/INTEL SETUP COMPLETE!
echo.
echo To start the backend, run:
echo    cd backend
echo    venv\Scripts\python main.py
echo ======================================================
pause
