# 📋 Installation Manual — AI Grievance Intelligence System

> **Version:** 1.0
> **Target Platform:** Windows 10/11 (COE Machine)
> **Deployment Method:** Docker Desktop
> **Estimated Setup Time:** 30–45 minutes

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Install Docker Desktop](#2-install-docker-desktop)
3. [Download the Project](#3-download-the-project)
4. [Google Cloud Setup (API Keys &amp; OAuth)](#4-google-cloud-setup-api-keys--oauth)
5. [Configure the Application](#5-configure-the-application)
6. [Launch the Application](#6-launch-the-application)
7. [First Login &amp; Onboarding](#7-first-login--onboarding)
8. [Stopping &amp; Restarting](#8-stopping--restarting)
9. [Updating to a New Version](#9-updating-to-a-new-version)
10. [Backup &amp; Data](#10-backup--data)
11. [Troubleshooting](#11-troubleshooting)
12. [Installation without Docker (Traditional Method)](#12-installation-without-docker-traditional-method)
13. [Architecture Overview](#13-architecture-overview)

---

## 1. System Requirements

| Requirement                | Minimum                                       | Recommended   |
| :------------------------- | :-------------------------------------------- | :------------ |
| **Operating System** | Windows 10 (64-bit) Build 19041+              | Windows 11    |
| **RAM**              | 4 GB                                          | 8 GB          |
| **Disk Space**       | 5 GB free                                     | 10 GB free    |
| **Internet**         | Required (for Gmail & AI APIs)                | Broadband     |
| **Browser**          | Chrome 90+ / Edge 90+                         | Latest Chrome |
| **Ports**            | 3000 (Frontend) & 8000 (Backend) must be free | —            |

> ⚠️ **Important:** This application requires an active internet connection to communicate with Google's Gmail API and Gemini AI API. It will NOT work on an air-gapped network.

---

## 2. Install Docker Desktop

Docker Desktop packages the entire application into isolated containers, eliminating the need to install Python, Node.js, or any other dependencies manually.

### Steps:

1. **Download Docker Desktop** from: https://www.docker.com/products/docker-desktop/
2. **Run the installer** (`Docker Desktop Installer.exe`).
3. During installation, ensure **"Use WSL 2 instead of Hyper-V"** is checked (recommended).
4. **Restart your computer** when prompted.
5. **Launch Docker Desktop** from the Start Menu.
6. Wait for the Docker Engine to start (the whale icon in the system tray will stop animating).
7. **Verify installation** by opening **PowerShell** and running:

```powershell
docker --version
docker compose version
```

You should see version numbers like `Docker version 27.x.x` and `Docker Compose version v2.x.x`.

> 💡 **Tip:** If you see an error about WSL 2, run `wsl --install` in an elevated PowerShell and restart.

---

## 2.1. GPU Acceleration (Recommended for COE)

The AI Grievance System includes local AI models for searching policy documents. While these can run on the CPU, using an NVIDIA GPU is significantly faster.

### Prerequisites:

- **NVIDIA GPU** with 4GB+ VRAM.
- **NVIDIA Driver** (Version 535+ recommended).

### One-Time Setup for Docker GPU Support:

To allow Docker containers to use your physical GPU, you must install the **NVIDIA Container Toolkit**:

1. **Open PowerShell as Administrator**.
2. Run the following command to install the toolkit via `winget`:
   ```powershell
   winget install NVIDIA.ContainerToolkit
   ```
3. **Restart Docker Desktop** after the installation completes.

### Launching in GPU Mode:

If you have an **NVIDIA GPU** and have installed the toolkit above, run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

If you have an **AMD or Intel GPU** (like a Radeon or Iris Xe), run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.amd.yml up --build -d
```

This will build the specialized GPU image and give the backend access to your hardware via DirectML.

---

## 3. Download the Project

### Option A: Using Git (Recommended)

```powershell
# Open PowerShell and navigate to a folder of your choice
cd C:\Projects

# Clone the repository
git clone https://github.com/Debajitgithub/AICOE_EDUCATION_with_priority.git

# Enter the project folder
cd AICOE_EDUCATION_with_priority
```

### Option B: Manual Download

1. Go to the GitHub repository page.
2. Click the green **"Code"** button → **"Download ZIP"**.
3. Extract the ZIP to a folder like `C:\Projects\AICOE_EDUCATION_with_priority`.

---

## 4. Google Cloud Setup (API Keys & OAuth)

The application needs **two types of Google credentials**:

- **Gemini API Key** — for the AI chatbot and email classification.
- **OAuth Client ID & Secret** — for secure Gmail login and email sync.

### 4A. Get a Gemini API Key

1. Go to: https://aistudio.google.com/apikey
2. Click **"Create API Key"**.
3. Select an existing Google Cloud project or create a new one.
4. **Copy the API key** — you will need it in Step 5.

> 💡 The free tier of Gemini API provides generous rate limits sufficient for departmental use.

### 4B. Create OAuth Credentials

1. Go to: https://console.cloud.google.com/apis/credentials
2. Select or create a project (use the same project as Step 4A).
3. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**.
4. If prompted to configure the **OAuth Consent Screen**:
   - Choose **"External"** user type.
   - Fill in the required fields (App name, Support email).
   - Add the following **Scopes**:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.send`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/userinfo.email`
     - `https://www.googleapis.com/auth/userinfo.profile`
   - Add **Test Users** (the Gmail addresses that will use the system).
   - Save.
5. Back on the Credentials page, click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**.
6. Choose **"Web application"** as the Application Type.
7. Set:
   - **Name:** `Grievance Dashboard`
   - **Authorized JavaScript Origins:** `http://localhost:3000`
   - **Authorized Redirect URIs:** `http://localhost:8000/auth/google/callback`
8. Click **"Create"**.
9. **Copy the Client ID and Client Secret** — you will need them in Step 5.

### 4C. Enable Required APIs

In the same Google Cloud project, enable these APIs:

1. Go to: https://console.cloud.google.com/apis/library
2. Search and enable:
   - **Gmail API**
   - **Generative Language API** (for Gemini)

---

## 5. Configure the Application

### 5A. Create the Backend Configuration

1. Open the project folder in File Explorer.
2. Navigate to the `backend` folder.
3. Find the file named `.env.example`.
4. **Copy** it and **rename** the copy to `.env` (just `.env`, no other extension).
5. Open `.env` in Notepad and fill in these **mandatory** fields:

```ini
# ===== MANDATORY: Replace these with your actual values =====

# Your Gemini API Key from Step 4A
GOOGLE_API_KEY=AIzaSy...your_key_here
GEMINI_API_KEY=AIzaSy...your_key_here

# Your OAuth credentials from Step 4B
GOOGLE_OAUTH_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...your_secret_here

# Security Keys (generate random strings or use these defaults for testing)
GOOGLE_OAUTH_ENCRYPTION_KEY=my-super-secret-encryption-key-change-me
APP_SESSION_SECRET=my-session-secret-change-me-in-production
```

6. **Save and close** the file.

> ⚠️ **Security:** Never share your `.env` file or commit it to Git. It contains sensitive credentials.

### 5B. Create the Frontend Configuration

1. Navigate to the `frontend` folder.
2. Find `.env.example` and **copy** it to `.env`.
3. For local deployment, set:

```ini
VITE_API_URL=http://localhost:8000
VITE_REPLY_API_URL=http://localhost:8000
```

4. **Save and close.**

---

## 6. Launch the Application

### First-Time Build & Launch

1. **Open PowerShell** (or Windows Terminal).
2. Navigate to the project root folder:

```powershell
cd C:\Projects\AICOE_EDUCATION_with_priority
```

3. **Build and start** the application:

```powershell
docker compose up --build -d
```

This command will:

- Download the required base images (~1 GB, first time only).
- Build the backend container (installs Python + AI libraries).
- Build the frontend container (compiles the React app).
- Start both containers in the background.

> ⏱️ **First build takes 5–10 minutes** depending on internet speed. Subsequent starts take ~30 seconds.

4. **Verify both containers are running:**

```powershell
docker compose ps
```

You should see:

```
NAME                 STATUS              PORTS
grievance-backend    Up (healthy)        0.0.0.0:8000->8000/tcp
grievance-frontend   Up (healthy)        0.0.0.0:3000->80/tcp
```

5. **Open your browser** and go to:

```
http://localhost:3000
```

🎉 **The application is now running!**

---

## 7. First Login & Onboarding

1. On the login page, click **"Sign in with Google"**.
2. Select the Gmail account you added as a Test User in Step 4B.
3. Grant the requested permissions (Read, Send, Modify emails).
4. You will be redirected to the Dashboard.
5. The system will begin **syncing your emails** in the background.
   - A progress indicator will show on the dashboard.
   - Initial sync fetches the last 14 days of email history.
   - The AI will automatically classify and prioritize each grievance.
6. Once sync completes, you can:
   - View grievance statistics on the **Dashboard**.
   - Ask the **AI Assistant** questions like: *"How many SVMCM complaints are unresolved?"*
   - Reply to grievances with **AI-suggested responses**.

---

## 8. Stopping & Restarting

### Stop the Application

```powershell
cd C:\Projects\AICOE_EDUCATION_with_priority
docker compose down
```

### Restart the Application (without rebuilding)

```powershell
cd C:\Projects\AICOE_EDUCATION_with_priority
docker compose up -d
```

### View Real-Time Logs

```powershell
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Frontend only
docker compose logs -f frontend
```

---

## 9. Updating to a New Version

When you receive an updated version of the code:

```powershell
cd C:\Projects\AICOE_EDUCATION_with_priority

# Stop the current instance
docker compose down

# Pull the latest code (if using Git)
git pull origin main

# Rebuild and restart
docker compose up --build -d
```

> 💡 Your data (emails, chat history, OAuth tokens) is stored in the `backend/data/` folder on your host machine and is preserved across updates.

---

## 10. Backup & Data

### Where is data stored?

| Data             | Location on Host Machine       |
| :--------------- | :----------------------------- |
| Email database   | `backend/data/grievances.db` |
| OAuth tokens     | `backend/data/oauth_tokens/` |
| Policy documents | `backend/policies/`          |
| Attachments      | `backend/attachments/`       |

### Creating a Backup

```powershell
# Stop the app first to ensure data consistency
docker compose down

# Copy the data folder
Copy-Item -Path ".\backend\data" -Destination ".\backup_data_$(Get-Date -Format 'yyyyMMdd')" -Recurse

# Restart
docker compose up -d
```

### Restoring from Backup

```powershell
docker compose down
Copy-Item -Path ".\backup_data_20260507\*" -Destination ".\backend\data\" -Recurse -Force
docker compose up -d
```

---

## 11. Troubleshooting

### ❌ "Docker is not running"

→ Open Docker Desktop from the Start Menu and wait for the engine to start.

### ❌ "Port 8000 already in use"

→ Another program is using port 8000. Find and stop it:

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID_NUMBER> /F
```

### ❌ "Port 3000 already in use"

→ Same as above but for port 3000.

### ❌ Backend shows "unhealthy"

→ Check the backend logs for errors:

```powershell
docker compose logs backend
```

Common causes:

- Missing or invalid API keys in `.env`.
- Missing environment variables.

### ❌ Frontend shows a blank page

→ The frontend build may have failed. Rebuild:

```powershell
docker compose down
docker compose up --build -d
```

### ❌ "OAuth error: redirect_uri_mismatch"

→ The redirect URI in Google Cloud Console doesn't match. Ensure it is exactly:

```
http://localhost:8000/auth/google/callback
```

### ❌ "Error 403: access_denied"

→ The Gmail account is not added as a Test User in the OAuth Consent Screen. Go to Google Cloud Console → OAuth Consent Screen → Test Users → Add the email.

### ❌ AI Chatbot says "I am having trouble processing"

→ Check if the Gemini API key is valid:

```powershell
docker compose logs backend | Select-String "API"
```

### ❌ Emails not syncing

→ Verify Gmail API is enabled in Google Cloud Console and the OAuth token is valid. Try logging out and logging back in.

---

---

## 12. Installation without Docker (Traditional Method)

If the COE machine does **not** have Docker Desktop installed, use this method to run the application directly on Windows.

### Prerequisites:

- **Python 3.10+** installed and added to PATH.
- **Node.js 18+** (Required for frontend).
- **NVIDIA GPU** (Optional but highly recommended for speed).

### Steps:

1. **Download the Project** (See Section 3).
2. **Configure the .env files** (See Section 4 & 5).
3. **Run the GPU Smart Setup**:
   - **For NVIDIA GPUs**: Double-click **`setup_coe_gpu.bat`**.
   - **For AMD/Intel GPUs**: Double-click **`setup_coe_amd.bat`**.
   - This script will automatically create a `venv`, detect your GPU, and install the correct version of PyTorch to avoid "DLL load" errors.
4. **Start the Backend**:
   - Open a new terminal.
   - `cd backend`
   - `venv\Scripts\python main.py`
5. **Start the Frontend**:
   - Open a second terminal.
   - `cd frontend`
   - `npm install`
   - `npm run dev`
6. **Access the system** at `http://localhost:3000` (or the port shown in the terminal).

---

## 13. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    User's Browser                    │
│                 http://localhost:3000                 │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              Docker Desktop (Windows)                 │
│                                                       │
│  ┌─────────────────┐    ┌──────────────────────────┐ │
│  │   Frontend       │    │   Backend                │ │
│  │   (Nginx)        │    │   (FastAPI + Uvicorn)    │ │
│  │   Port: 3000     │───▶│   Port: 8000             │ │
│  │                  │    │                          │ │
│  │   React + Vite   │    │   ┌──────────────────┐  │ │
│  │   TailwindCSS    │    │   │  SQLite Database  │  │ │
│  │                  │    │   │  (grievances.db)  │  │ │
│  └─────────────────┘    │   └──────────────────┘  │ │
│                          │                          │ │
│                          │   ┌──────────────────┐  │ │
│                          │   │  AI Engine        │  │ │
│                          │   │  (LangGraph +     │  │ │
│                          │   │   Gemini API)     │  │ │
│                          │   └──────────────────┘  │ │
│                          │                          │ │
│                          │   ┌──────────────────┐  │ │
│                          │   │  Gmail Sync       │  │ │
│                          │   │  (Background      │  │ │
│                          │   │   Worker)          │  │ │
│                          │   └──────────────────┘  │ │
│                          └──────────────────────────┘ │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────┐
        │   Google Cloud Platform   │
        │                          │
        │  • Gmail API             │
        │  • Gemini AI API         │
        │  • OAuth 2.0             │
        └──────────────────────────┘
```

### Key Components

| Component            | Technology                   | Purpose                                         |
| :------------------- | :--------------------------- | :---------------------------------------------- |
| **Frontend**   | React, Vite, TailwindCSS     | User interface, dashboard, chatbot UI           |
| **Backend**    | Python, FastAPI, Uvicorn     | API server, business logic, AI orchestration    |
| **Database**   | SQLite                       | Email storage, chat history, user settings      |
| **AI Engine**  | LangGraph, Gemini API        | Chatbot, email classification, priority scoring |
| **Email Sync** | Gmail API                    | Background email fetching and parsing           |
| **RAG System** | FAISS, Sentence-Transformers | Policy-aware AI responses                       |
| **Web Server** | Nginx (in Docker)            | Serves the compiled frontend, handles routing   |

---

> **Document Prepared By:** AI Centre of Excellence, Education Department
> **Last Updated:** May 2026
