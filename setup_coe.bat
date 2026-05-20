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
py --version >nul 2>&1 && set PYTHON_CMD=py
if exist "C:\Program Files\Python312\python.exe" set "PYTHON_CMD=C:\Program Files\Python312\python.exe"

echo 🔍 Using: 
"%PYTHON_CMD%" --version

:: 2. Create venv if not exists
if not exist "backend\venv" (
    echo 🛠️ Creating Virtual Environment...
    "%PYTHON_CMD%" -m venv backend\venv
)

:: 2. Activate venv
echo 🔌 Activating Virtual Environment...
call backend\venv\Scripts\activate.bat

:: 4. Upgrade pip
echo 🆙 Upgrading pip...
"%PYTHON_CMD%" -m pip install --upgrade pip

:: 4. Install Dependencies
echo 📚 Detecting Hardware for Optimal AI performance...

:: Check for NVIDIA GPU to prevent DLL initialization errors (WinError 1114)
wmic path win32_VideoController get name | findstr /i "NVIDIA" >nul 2>&1
if %errorlevel% == 0 (
    echo 🚀 NVIDIA GPU Detected! Installing High-Performance PyTorch (CUDA 12.4)...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
) else (
    echo 💻 Standard Hardware Detected. Installing Stable AI dependencies...
)

echo 📚 Finalizing dependencies from requirements.txt...
pip install -r backend\requirements.txt

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
