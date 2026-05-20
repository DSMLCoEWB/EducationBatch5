# 📋 Comprehensive Installation Manual — AI Grievance Intelligence System

Welcome to the definitive setup and installation manual for the **AI Grievance Intelligence System**. This document outlines how to install, configure, secure, and run the application natively on **any operating system** (Windows, Linux, macOS) or inside **Docker containers**.

---

## 🚦 Table of Contents
1. [System Requirements](#1-system-requirements)
2. [Google Cloud Platform Setup (API Keys & OAuth)](#2-google-cloud-platform-setup-api-keys--oauth)
3. [Method A: Native Installation (Highly Recommended for Host GPU/Ollama)](#3-method-a-native-installation-highly-recommended-for-host-gpuollama)
4. [Method B: Containerized Installation (Docker Desktop)](#4-method-b-containerized-installation-docker-desktop)
5. [Local Playground: Seeding & Initializing FAISS Index](#5-local-playground-seeding--initializing-faiss-index)
6. [Maintenance, Backups & Data Folders](#6-maintenance-backups--data-folders)
7. [Troubleshooting & Common Fixes](#7-troubleshooting--common-fixes)
8. [Appendix: Environment Variables Reference](#8-appendix-environment-variables-reference)
   * [8.1 Backend Environment Variables](#81-backend-environment-variables-backendenv)
   * [8.2 Frontend Environment Variables](#82-frontend-environment-variables-frontendenv)

---

## 1. System Requirements

The system processes large policy documents and scans visual email attachments. Minimum and recommended criteria vary based on whether local GPU acceleration is used.

| Requirement | Minimum (CPU Only) | Recommended (NVIDIA GPU Acceleration) |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11, Ubuntu 22.04+, macOS | Windows 11 / Ubuntu 22.04+ |
| **Processor** | Intel Core i5 / AMD Ryzen 5 | Intel Core i7 / AMD Ryzen 7 |
| **RAM** | 8 GB | 16 GB+ |
| **Graphics Card** | Standard Integrated Graphics | NVIDIA GPU with 4GB+ VRAM (CUDA 12.4 compatible) |
| **Disk Space** | 5 GB free space | 15 GB free space (for AI model caching) |
| **Internet** | Required for external API calls | High-speed Broadband |

> [!IMPORTANT]
> This application requires an active internet connection to communicate securely with Google Gmail and Google Gemini AI servers. It cannot run in an air-gapped network environment.

---

## 2. Google Cloud Platform Setup (API Keys & OAuth)

To unlock automated Gmail synchronization and LLM classification, you must configure two types of credentials in your Google Cloud Console.

### 2.1 Enable Google APIs
1. Navigate to the [Google Cloud Library Console](https://console.cloud.google.com/apis/library).
2. Create or select a Google Cloud project.
3. Search for and enable the following APIs:
   * **Gmail API**
   * **Generative Language API** (required for Gemini)

### 2.2 Get a Gemini API Key
1. Go to the [Google AI Studio API Key Manager](https://aistudio.google.com/apikey).
2. Click **Create API Key**.
3. Copy the generated key. You will configure this as `GOOGLE_API_KEY` and `GEMINI_API_KEY`.

### 2.3 Create OAuth Client Credentials for Gmail Sync
1. Go to the [Google Credentials Console](https://console.cloud.google.com/apis/credentials).
2. Click **Create Credentials** → **OAuth client ID**.
3. If prompted to configure the OAuth Consent Screen:
   * Select **External** User Type.
   * Add the following authorization scopes:
     * `https://www.googleapis.com/auth/gmail.readonly`
     * `https://www.googleapis.com/auth/gmail.send`
     * `https://www.googleapis.com/auth/gmail.modify`
     * `https://www.googleapis.com/auth/userinfo.email`
     * `https://www.googleapis.com/auth/userinfo.profile`
   * Add your target Gmail accounts as **Test Users** (mandatory while in testing mode).
4. Select **Web Application** as the Application Type.
5. Set the redirect and origin configurations:
   * **Authorized JavaScript Origins:** `http://localhost:3000`
   * **Authorized Redirect URIs:** `http://localhost:8000/auth/google/callback`
6. Click **Create** and safely record your **Client ID** and **Client Secret**.

### 2.4 Generate Cryptographic Security Keys
For secure multi-user credential storage and session signing, the system requires two secure cryptographic keys.

1. **OAuth Encryption Key (`GOOGLE_OAUTH_ENCRYPTION_KEY`)**:
   * **What it does**: A symmetric Fernet key used to securely encrypt and decrypt Gmail API refresh tokens inside the database (protecting user credentials at rest).
   * **How to generate it**: Open a terminal and run the following Python command:
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   * **Usage**: Copy the printed 44-character string and paste it into `.env` as `GOOGLE_OAUTH_ENCRYPTION_KEY`.

2. **Session Signature Secret (`APP_SESSION_SECRET`)**:
   * **What it does**: A cryptographically secure secret used to sign cookies and manage secure user sessions (preventing session hijacking).
   * **How to generate it**: Run the same Python generator command again or use a secure random hex generator:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   * **Usage**: Copy the printed string and paste it into `.env` as `APP_SESSION_SECRET`.

### 2.5 Optional Dedicated LLM Keys (Quota Isolation)
Under high traffic, multiple background AI Triaging tasks can clash with the AI Reply Generator, causing Gemini API rate-limiting errors.
To isolate these quotas, you can optionally configure up to three separate Gemini API keys:
1. **`GOOGLE_API_KEY` / `GEMINI_API_KEY`**: The main key used for generating email responses in the reply modal.
2. **`PRIORITY_GOOGLE_API_KEY` / `PRIORITY_GEMINI_API_KEY`**: A secondary key used for high-volume background ticket classifications and priority triage.
3. **`CHATBOT_GEMINI_API_KEY`**: A third key reserved exclusively for the AI assistant chatbot.

*Note: If secondary keys are left blank in `.env`, the system will gracefully fall back to using your main `GOOGLE_API_KEY` for all operations.*

---

## 3. Method A: Native Installation (Highly Recommended for Host GPU/Ollama)

Running the system natively lets the backend leverage host GPU architectures and connect to local Ollama nodes directly without virtualization overhead.

### 3.1 Setup on Windows (Automated Smart Script)
1. **Ensure Ollama is running** on your host.
2. Double-click the **`setup_coe.bat`** script in the project root.
3. The script will automatically:
   * Detect NVIDIA GPU video controllers.
   * Configure a local Python Virtual Environment (`backend/venv`).
   * Download the correct version of PyTorch (CUDA 12.4 wheels for GPU, standard wheels for CPU) to prevent system DLL conflicts.
   * Install all required backend packages from `backend/requirements.txt`.

### 3.2 Setup on Linux / macOS
1. Open a terminal and navigate to the `backend/` directory:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### 3.3 Configure Environment Variables
1. Navigate to the `backend/` folder.
2. Rename `.env.example` to `.env`.
3. Open `.env` and fill in your Google credentials from [Section 2](#2-google-cloud-platform-setup-api-keys--oauth):
   ```ini
   GOOGLE_API_KEY=AIzaSy...your_gemini_key
   GEMINI_API_KEY=AIzaSy...your_gemini_key
   GOOGLE_OAUTH_CLIENT_ID=your_id.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your_secret
   ```

### 3.4 Launch Services Natively

*   **Terminal 1 - Backend Server:**
    ```bash
    cd backend
    # Windows:
    venv\Scripts\activate.bat
    python main.py
    # Linux / macOS:
    source venv/bin/activate
    python main.py
    ```
*   **Terminal 2 - Frontend Client:**
    ```bash
    cd frontend
    npm install
    npm run dev
    ```
    Access the React UI at `http://localhost:3000`.

---

## 4. Method B: Containerized Installation (Docker Desktop)

Using Docker simplifies cross-platform dependencies by packaging the backend and frontend into isolated, self-healing containers.

### 4.1 Create Environment Files
1. Create `backend/.env` (configured as shown in [Section 3.3](#33-configure-environment-variables)).
2. Create `frontend/.env` and verify the backend API endpoints:
   ```ini
   VITE_API_URL=http://localhost:8000
   VITE_REPLY_API_URL=http://localhost:8000
   ```

### 4.2 Start Containers
1. Launch **Docker Desktop** on your host machine.
2. Open a terminal in the project root and start the multi-stage services:
   ```bash
   docker compose up --build -d
   ```
3. Verify both containers are running successfully:
   ```bash
   docker compose ps
   ```
   Access the dashboard at `http://localhost:3000`.

---

## 5. Build the Semantic FAISS Policy Index

To enable policy-grounded AI responses, the application requires building a semantic FAISS vector index of your institutional guidelines. This is handled completely dynamically via the running application:

1. Start both the backend and frontend servers natively (described in [Section 3](#3-method-a-native-installation-highly-recommended-for-host-gpuollama)) or containerized (described in [Section 4](#4-method-b-containerized-installation-docker-desktop)).
2. Open the React dashboard at `http://localhost:3000` and sign in using Google OAuth.
3. Open the **"Administrative Policy Console"** from the top navigation bar or sidebar, and click the **"Load Demo PDFs"** button in the modal's footer. This dynamically parses all official policy documents stored in `backend/demo_policies/`, extracts their semantic chunks, and builds the local `rag_index.faiss` database.
4. Alternatively, you can compile this index via a single HTTP API call:
   ```bash
   curl -X POST http://localhost:8000/policies/load-demo
   ```

---

## 6. Maintenance, Backups & Data Folders

### 6.1 Data Locations
Active application data is preserved outside of code directories to ensure update safety:
*   **SQLite Database:** `backend/data/grievances.db`
*   **OAuth Credentials Cache:** `backend/data/oauth_tokens/`
*   **FAISS Vector Index:** `backend/rag/data/`
*   **Extracted Attachments:** `backend/attachments/`

### 6.2 Manual Data Backup (Windows Command)
To safely backup all user credentials, emails, and attachments, run:
```powershell
# Stop services
docker compose down
# Copy data safely
Copy-Item -Path ".\backend\data" -Destination ".\backup_data_$(Get-Date -Format 'yyyyMMdd')" -Recurse
```

---

## 7. Troubleshooting & Common Fixes

### ❌ Python `WinError 1114` (DLL Initialization Failed)
*   **Cause:** Occurs on Windows host GPUs when PyTorch tries to load mismatched CUDA/CPU drivers.
*   **Fix:** Run `setup_coe.bat` to automatically detect your driver capabilities and install matched PyTorch libraries.

### ❌ OAuth consent screen `Error 403: access_denied`
*   **Cause:** The Gmail login address has not been registered as an authorized developer account test user.
*   **Fix:** Go to Google Cloud Console → **OAuth consent screen** → **Test Users** and add your sync email address.

### ❌ Gmail callback fails with `redirect_uri_mismatch`
*   **Cause:** The URI configured in Google Credentials differs from the server environment.
*   **Fix:** Ensure your GCP OAuth Authorized Redirect URI matches exactly: `http://localhost:8000/auth/google/callback`

### ❌ FAISS Index / Retrieval Fails
*   **Cause:** The FAISS index directory is empty or raw PDFs failed chunk ingestion.
*   **Fix:** Open the **"Administrative Policy Console"** on the React dashboard and click **"Load Demo PDFs"** in the footer, or trigger it manually by running `curl -X POST http://localhost:8000/policies/load-demo` to build the `rag_index.faiss` vector database and policy chunks.

---

## 8. Appendix: Environment Variables Reference

The system utilizes separate environment files for the FastAPI backend and React frontend.

### 8.1 Backend Environment Variables (`backend/.env`)

The backend engine uses centralized `.env` configurations to dial in background sync behavior, local AI support, and RAG retrieval settings. Below is a comprehensive reference table of every parameter exposed in `backend/.env.example`:

| Category | Variable Name | Default Value | Purpose & Comprehensive Impact |
| :--- | :--- | :--- | :--- |
| **Safeguards** | `SYNC_ENABLED` | `true` | **Global Sync Switch**: Instantly toggles the background Gmail synchronization worker on or off. |
| | `GMAIL_CALLS_PER_MINUTE_LIMIT` | `50` | **Rate Limiting**: The maximum number of Gmail API calls the sync engine is allowed to perform per minute, preventing rate-limiting blocks. |
| | `GMAIL_SYNC_INTERVAL_SECONDS` | `600` | **Polled Refresh Rate**: How frequently (in seconds) the background task checks for new incoming grievance emails. |
| | `MANUAL_SYNC_COOLDOWN_SECONDS` | `60` | **Cooldown Guard**: Prevents users from overloading Google's servers by limiting manual inbox refreshes on the UI. |
| | `GMAIL_FULL_SYNC_DAYS` | `365` | **Sync Depth**: How far back in history (in days) the system crawls to build the initial inbox cache on first user login. |
| | `SYNC_JITTER_SECONDS` | `60` | **Anti-Bot Jitter**: Adds a random ± variance (in seconds) to background intervals so requests do not trigger bot detection systems. |
| | `SYNC_MAX_BACKOFF_SECONDS` | `3600` | **Network Resiliency**: The upper cap (1 hour) for the exponential backoff delay during network disconnects. |
| **AI / LLM Keys** | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | *(None)* | **Primary LLM Access**: The central Google AI Studio API key used to generate replies and interact with Gemini models. |
| | `PRIORITY_GOOGLE_API_KEY` | *(None)* | **Classification Key**: Dedicated key to process high-volume background priority ratings, preventing quota clashes. |
| | `CHATBOT_GEMINI_API_KEY` | *(None)* | **Assistant Key**: Dedicated key reserved for the real-time student grievance assistant chatbot in the UI. |
| **AI Models** | `AI_PREFER_LOCAL` | `false` | **Local Mode Switch**: Set to `true` to route classification and parsing tasks to a local Ollama model instead of Gemini. |
| | `PRIMARY_LOCAL_MODEL` | `gemma3:4b` | **Ollama Model**: The target local LLM to load and execute via your local Ollama node. |
| | `OLLAMA_CONTEXT_LENGTH` | `16384` | **Local Token Cap**: The maximum context window loaded into local VRAM (recommended 8k-16k for complex grievances). |
| | `OLLAMA_VULKAN` / `OLLAMA_FLASH_ATTENTION` | `1` / `1` | **Acceleration**: Activates AMD/Intel Vulkan and Flash Attention optimizations inside Ollama for rapid inference. |
| | `AI_FALLBACK_MODELS` | *(List)* | **Resiliency Fallbacks**: Comma-separated list of models the system steps through if primary local or API requests fail. |
| | `VISION_FALLBACK_MODELS` | *(List)* | **OCR Fallbacks**: Vision-enabled models used to read scanned graphic PDF attachments and visual tickets. |
| **RAG & Search** | `RAG_TOP_K` | `5` | **RAG Extraction**: Number of candidate chunks retrieved from the FAISS database for contextual re-ranking. |
| | `RAG_MIN_SCORE` | `0.40` | **Similarity Cutoff**: The strict cosine similarity threshold (0.0 to 1.0) required for a policy clause to be deemed relevant. |
| | `RAG_UNREPLIED_MAX` | `3` | **The "3" in 3+2 RAG**: The maximum number of recent, consecutive unreplied incoming citizen follow-up emails to crawl backwards. This captures the complete list of fresh unaddressed queries sent by the student since the last official department reply. |
| | `RAG_ANCHOR_DEPTH` | `2` | **The "2" in 3+2 RAG**: The depth of the "Anchor Turn" representing the **last official Department Reply + its incoming Citizen Trigger** (the "handshake"). This establishes a perfect historical context of what was already officially answered and what prompted it. |
| **OAuth & Security**| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | *(None)* | **Google OAuth Client**: Client keys from GCP Credentials for secure department-level user sign-in. |
| | `GOOGLE_OAUTH_ENCRYPTION_KEY` | *(None)* | **Credential Guard**: A symmetric Fernet key used to securely encrypt and decrypt Gmail OAuth tokens inside the database at rest. |
| | `APP_SESSION_SECRET` | *(None)* | **Session Guard**: Cryptographic signature secret used to sign session cookies and prevent session hijacking. |

### 8.2 Frontend Environment Variables (`frontend/.env`)

The frontend application uses client-side Vite environment variables (prefixed with `VITE_`) to configure API gateway routing and UI behaviors:

| Variable Name | Default Value | Purpose & Comprehensive Impact |
| :--- | :--- | :--- |
| `VITE_API_URL` | `http://localhost:8000` | **Backend API Base**: The central routing address pointing to your FastAPI backend gateway for general transactions (grievances, policy lists, etc.). |
| `VITE_REPLY_API_URL` | `http://localhost:8000` | **Response Engine Gateway**: Pointing to the backend API router responsible for triggering RAG-contextual email generation. |
| `VITE_AUTH_STATUS_POLLING_SECONDS` | `60` | **Session Poller**: Frequency (in seconds) the UI queries the backend database to check if Google OAuth sync remains fully authenticated. |
| `VITE_SHOW_DEMO_BUTTON` | `false` | **Demo Console Bypass**: Developer/QA override. Set to `true` to force-render the "Load Demo PDFs" option in a production/deployed environment. Otherwise, it is automatically protected and only displayed on localhost/dev nodes. |

