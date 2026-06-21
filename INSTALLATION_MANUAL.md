# 📋 Comprehensive Installation Manual — EPIC – Email-based Public Interaction & Case Management

Welcome to the definitive setup and installation manual for the **EPIC – Email-based Public Interaction & Case Management**. This document outlines how to install, configure, secure, and run the application natively on **any operating system** (Windows, Linux, macOS) or inside **Docker containers**.

> [!IMPORTANT]
> **Branch Notice:** Please ensure you are cloning and operating from the `main` branch, as it contains the most up-to-date and verified codebase.

---

## 🚦 Table of Contents
1. [System Requirements](#1-system-requirements)
2. [Cloud Platform Setup (API Keys & OAuth)](#2-cloud-platform-setup-api-keys--oauth)
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

### 1.1 Software Prerequisites
Before beginning, ensure you have the following installed on your machine:
*   **Git**: To clone the repository.
*   **Python 3.10 or higher**: Required to run the FastAPI backend.
*   **Node.js 18 or higher**: Required to build and run the React frontend.
*   **(Optional) Docker Desktop**: If you plan to run the system using containers instead of a native installation.
*   **(Optional) Ollama**: If you plan to run open-source AI models locally.

> [!IMPORTANT]
> This application requires an active internet connection to communicate securely with Google Gmail, Microsoft Graph, and Google Gemini AI servers. It cannot run in an entirely air-gapped network environment.

---

## 2. Cloud Platform Setup (API Keys & OAuth)

To unlock automated email synchronization and LLM classification, you must configure credentials in either Google Cloud Console (for Gmail) or Microsoft Azure AD (for Outlook/Office 365), along with Gemini AI keys.

> [!NOTE]
> **Understanding Google Credentials in this System**
> You will generate two completely different types of credentials from your Google Cloud Project:
> 1. **Enterprise Agent Platform Service Account (JSON):** Server-to-Server authentication for the backend to run Enterprise Gemini models.
> 2. **OAuth 2.0 Client (ID & Secret):** User-to-Server authentication to power the "Sign in with Google" popup for Gmail sync.

### 2.1 Enable Google APIs
1. Navigate to the [Google Cloud Library Console](https://console.cloud.google.com/apis/library).
2. Create or select a Google Cloud project.
3. Search for and enable the following APIs:
   * **Gmail API** (if syncing Gmail)
   * **Gemini Enterprise Agent Platform API** (formerly Vertex AI API - required if using enterprise routing)
   * **Generative Language API** (only if using Fallback/Developer Standard API Keys - Paid or Free tier)

### 2.2 Configure Enterprise Gemini Agent Platform Authentication (Google Cloud)
To ensure strict data privacy and compliance with government regulations, the system is engineered to route AI traffic through the **Gemini Enterprise Agent Platform** (formerly Google Cloud Vertex AI). This guarantees that citizen grievance data is **never** used to train Google's public models.

> [!NOTE]
> **Enterprise Security Model:** The Enterprise Agent Platform uses cryptographic Service Account Identity and Access Management (IAM) keys instead of standard developer API strings.

1. **Create a Project:** Go to the [Google Cloud Console](https://console.cloud.google.com/). If you are new to GCP, you will need to set up a billing account. Click the **Project Dropdown** at the top left to create a "New Project".
2. **Set the Project ID:** On your Project Dashboard, locate the **Project ID** (e.g., `my-education-project-123`). Open your `backend/.env` file and set `VERTEX_AI_PROJECT=your-project-id`.
3. **Enable the API:** Use the top search bar in the console to search for the **"Gemini Enterprise Agent Platform API"** (this replaces the legacy Vertex AI API). Click on it and hit the blue **Enable** button.
4. **Set Data Residency:** To comply with Indian data sovereignty laws, open your `backend/.env` file and set `VERTEX_AI_LOCATION=asia-south1`. This forces the system to strictly route all AI processing to the Mumbai data centers.
5. **Create a Service Account:** 
   * In the left-hand navigation menu, go to **IAM & Admin > Service Accounts**.
   * Click **+ CREATE SERVICE ACCOUNT** at the top. Give it a name (e.g., "vertex-ai-bot") and click **Create and Continue**.
   * Under "Select a role", search for and select **Vertex AI User** (`roles/aiplatform.user`). Click **Continue**, then **Done**.
6. **Generate the JSON Key:**
   * Click on the email address of the newly created Service Account in the list.
   * Go to the **Keys** tab at the top.
   * Click **Add Key > Create new key**. Select **JSON** and click **Create**. The key file will automatically download to your computer.
   * *Note: While Google encourages Keyless ADC, using a Service Account JSON key ensures your production server achieves 100% uptime without being tied to a human user session that might unexpectedly expire.*
7. **Secure the Key:** Move that downloaded JSON file into your server at `backend/storage/keys/` and rename it to exactly `vertex-key.json`. *(Create the `keys` folder if it doesn't exist).*
8. **Link the Key:** Finally, in your `backend/.env` file, set `GOOGLE_APPLICATION_CREDENTIALS=storage/keys/vertex-key.json`. (This relative path works seamlessly for both Native Windows and Docker environments).

> *(Fallback/Development Mode)*: If you do not have an Enterprise Google Cloud project ready, you can still test the system using standard API keys. Go to **[Google AI Studio](https://aistudio.google.com/)** and click **Get API Key**. Ensure you set up a billing account for the **Paid Tier** to guarantee data privacy; otherwise, Free Tier data may be used by Google for model training. Copy the key and configure it as `GOOGLE_API_KEY` and `GEMINI_API_KEY` in your `.env` file. The system will automatically fall back to Developer API routing if `VERTEX_AI_PROJECT` is left blank.

### 2.3 Configure the Google Auth Platform (OAuth Consent Screen)
*Google requires configuring the consent screen before generating OAuth client keys.*
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. In the left-hand navigation menu, click **APIs & Services**, then select **OAuth consent screen**.
3. You will be redirected to the new **Google Auth Platform**. Click **Get started** in the center of the screen.
4. You will be placed in a 4-step "Project configuration" wizard:
   * **Step 1 (App Information):** Enter an App name and your User support email, then click **Next**.
   * **Step 2 (Audience):** Select **External** User Type. Under Test Users, add your target Gmail accounts (mandatory while testing), then click **Next**.
   * **Step 3 (Contact Information):** Enter a developer contact email, then click **Next**.
   * **Step 4 (Finish):** Review and click the **Create** button at the bottom.
5. Once the wizard finishes, select **Data Access** from the left sidebar.
6. Click **Add or Remove Scopes** and add:
   * `https://www.googleapis.com/auth/gmail.readonly`
   * `https://www.googleapis.com/auth/gmail.send`
   * `https://www.googleapis.com/auth/gmail.modify`
   * `https://www.googleapis.com/auth/userinfo.email`
   * `https://www.googleapis.com/auth/userinfo.profile`
7. Save your data access scopes.

### 2.4 Create OAuth Client Credentials for Gmail Sync (Google)
1. Still under the **Google Auth Platform** menu in the left sidebar, click **Clients**.
2. Click **Create Client** near the top of the page and select **Web application** as the Application Type.
3. Set the redirect and origin configurations:
   * **Authorized JavaScript origins:** `http://localhost:3000` and `http://localhost:8000`
   * **Authorized redirect URIs:** `http://localhost:8000/auth/google/callback`
4. Click **Create** and safely record your **Client ID** and **Client Secret**. You will assign these to `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in your backend `.env` file.

### 2.5 Create OAuth Client Credentials for Microsoft Graph Sync (Azure AD)
1. Go to the [Microsoft Entra Admin Center](https://entra.microsoft.com/).
2. In the left sidebar, under **Entra ID**, click **App registrations**, then click **New registration**.
3. Name your application and select **Any Entra ID Tenant + Personal Microsoft accounts** for supported account types.
4. Set the Redirect URI type to **Web** and the URL to: `http://localhost:8000/auth/microsoft/callback`.
5. Click the blue **Register** button at the bottom of the page to create the application.
6. Once registered, you will be on the app's Overview page. Under **API permissions** in the left menu, click **Add a permission** → **Microsoft Graph** → **Delegated permissions** and add:
   * `Mail.Read`
   * `Mail.ReadWrite`
   * `Mail.Send`
   * `User.Read`
   * `offline_access` (Required for background sync / refresh tokens)
7. *(Optional but recommended)* Click **Grant admin consent for <Your Directory>** and click **Yes** to confirm if you are an administrator.
8. Under **Certificates & secrets** in the left menu, click **New client secret** and copy the **Value** (not the Secret ID). You will assign this to `MICROSOFT_OAUTH_CLIENT_SECRET` in your backend `.env` file.
9. Go to the **Overview** page and copy the **Application (client) ID**. You will assign this to `MICROSOFT_OAUTH_CLIENT_ID` in your backend `.env` file.

### 2.6 Generate Cryptographic Security Keys
For secure multi-user credential storage and session signing, the system requires two secure cryptographic keys.

1. **OAuth Encryption Key (`OAUTH_ENCRYPTION_KEY`)**:
   * **What it does**: A symmetric Fernet key used to securely encrypt and decrypt email API refresh tokens inside the database (protecting user credentials at rest).
   * **How to generate it**: Open a terminal and run the following Python command:
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   * **Usage**: Copy the printed 44-character string and paste it into `.env` as `OAUTH_ENCRYPTION_KEY`.

2. **Session Signature Secret (`APP_SESSION_SECRET`)**:
   * **What it does**: A cryptographically secure secret used to sign cookies and manage secure user sessions (preventing session hijacking).
   * **How to generate it**: Run the same Python generator command again or use a secure random hex generator:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   * **Usage**: Copy the printed string and paste it into `.env` as `APP_SESSION_SECRET`.

### 2.7 Optional Dedicated LLM Keys (Quota Isolation)
> [!NOTE]
> **Vertex AI Users:** If you are using Enterprise Vertex AI (by setting `VERTEX_AI_PROJECT`), you do **not** need these API keys. Quota is managed automatically through your Google Cloud Service Account.

Under high traffic when using Developer APIs, multiple background AI Triaging tasks can clash with the AI Reply Generator, causing Gemini API rate-limiting errors.
To isolate these quotas, you can optionally configure up to three separate Gemini API keys:
1. **`GOOGLE_API_KEY` / `GEMINI_API_KEY`**: The main key used for generating email responses in the reply modal.
2. **`PRIORITY_GOOGLE_API_KEY` / `PRIORITY_GEMINI_API_KEY`**: A secondary key used for high-volume background ticket classifications and priority triage.
3. **`CHATBOT_GEMINI_API_KEY`**: A third key reserved exclusively for the AI assistant chatbot.

*Note: If secondary keys are left blank in `.env`, the system will gracefully fall back to using your main `GOOGLE_API_KEY` for all operations.*

---

## 3. Method A: Native Installation (Recommended for Local Development & Host GPU)

> [!TIP]
> **Ideal for Internal or Local Use**  
> Native execution is streamlined and highly efficient for local analysis, development, and internal intranet environments. If you intend to deploy this system for public internet access at scale, we recommend using the Containerized method (Method B) or placing this native instance behind a standard reverse proxy (like NGINX or an enterprise load-balancer) to handle public traffic routing.

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
2. Copy `.env.example` to `.env`.
3. Open `.env` and fill in your cloud credentials from [Section 2](#2-cloud-platform-setup-api-keys--oauth):
   ```ini
   # Enterprise Vertex AI Routing (Leaves API Keys blank)
   VERTEX_AI_PROJECT=your_google_cloud_project_id
   GOOGLE_APPLICATION_CREDENTIALS=storage/keys/vertex-key.json
   
   # Or Developer API Fallbacks (If not using Vertex)
   GOOGLE_API_KEY=AIzaSy...your_gemini_key
   GEMINI_API_KEY=AIzaSy...your_gemini_key
   
   # Google OAuth Client
   GOOGLE_OAUTH_CLIENT_ID=your_id.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your_secret

   # Microsoft OAuth Client (If syncing Outlook)
   MICROSOFT_OAUTH_CLIENT_ID=your_microsoft_client_id
   MICROSOFT_OAUTH_CLIENT_SECRET=your_microsoft_secret

   # Security & Sessions (Generated in Section 2.6)
   OAUTH_ENCRYPTION_KEY=your_generated_fernet_key
   APP_SESSION_SECRET=your_generated_hex_secret
   ```

### 3.4 Launch Services Natively

> [!NOTE]
> **Important:** Always launch the backend using `python main.py`. This script is deliberately engineered to run a single safe worker. Do not attempt to run custom multi-worker commands (e.g., `uvicorn app:app --workers 4`) natively, as concurrent initialization will cause database deadlocks. Multi-worker scaling is handled exclusively by the Docker architecture.

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

> [!TIP]
> **Recommended for Public & Scaled Deployments**  
> The Docker container stack automatically includes an NGINX Gateway, which provides built-in rate limiting, optimized routing, and secure handling of public internet traffic. This is the recommended path if you are deploying the application to be accessed by a large number of external users.

Using Docker packages the entire ecosystem into a production-grade, distributed architecture:
*   **PostgreSQL**: Handles persistent, concurrent transactional data with connection pooling.
*   **Redis**: Serves as the high-throughput message broker and result backend for Celery.
*   **FastAPI Backend**: Serves API queries and interacts with the DB pool.
*   **Celery Worker**: Offloads heavy, asynchronous jobs (Gmail synchronisation, PDF parsing, vector indexing, and AI triage).
*   **React Frontend**: Provides the administration and dashboard UI.

### 4.1 Create Environment Files
1. Create `backend/.env` (configured as shown in [Section 3.3](#33-configure-environment-variables)). Ensure `DATABASE_TYPE=postgres` and `TASK_QUEUE_TYPE=celery`.
2. Copy `frontend/.env.example` to `frontend/.env` and configure the backend API endpoints for the unified domain architecture:
   ```ini
   VITE_API_URL=/api
   VITE_REPLY_API_URL=/api
   ```

### 4.2 Start Containers
1. Launch **Docker Desktop** on your host machine.
2. Open a terminal in the project root and start the multi-stage services:
   ```bash
   docker compose up --build -d
   ```
3. Verify all services are running successfully:
   ```bash
   docker compose ps
   ```
   *   `grievance-postgres` (Port 5432 is internal only)
   *   `grievance-pgbouncer` (Port 6432)
   *   `grievance-redis` (Internal only)
   *   `grievance-migrator` (Runs migrations)
   *   `backend` (3 replicas, Internal)
   *   `celery_worker` (2 replicas, Background)
   *   `grievance-nginx` (Port 8000, Master Gateway)
   *   `grievance-frontend` (Internal)
   
   Access the dashboard at `http://localhost:8000`.

### 4.3 Updating the Docker Deployment

> [!WARNING]
> **Important NGINX Routing Quirk:** If you pull new code or need to rebuild the containers in the future, **do not** just run `docker compose up --build -d` by itself. You must tear down the network first:

```bash
docker compose down
docker compose up --build -d
```

> **Why?** The NGINX reverse proxy infinitely caches the internal IP addresses of the `backend` and `frontend` containers on startup. If you rebuild containers without running `down` first, the new containers are assigned new IPs, but NGINX will stubbornly route your traffic to the old, dead IPs (causing a 502 Bad Gateway error).

---

## 5. Build the Semantic FAISS Policy Index

To enable policy-grounded AI responses, the application requires building a semantic FAISS vector index of your institutional guidelines. This is handled completely dynamically via the running application:

1. Start both the backend and frontend servers natively (described in [Section 3](#3-method-a-native-installation-highly-recommended-for-host-gpuollama)) or containerized (described in [Section 4](#4-method-b-containerized-installation-docker-desktop)).
2. Open the React dashboard at `http://localhost:8000` (if using Docker) or `http://localhost:3000` (if using Native) and sign in via your authorized OAuth account.
3. Open the **"Administrative Policy Console"** from the top navigation bar or sidebar.
4. Use the **Upload Policy** interface to upload your department's official PDF or Word document guidelines.
5. Upon upload, the backend will automatically parse the document, extract semantic chunks, and build your department's isolated `index.faiss` vector database in real-time.


---

## 6. Maintenance, Backups & Data Folders

### 6.1 Data Locations
Active application data is preserved centrally in the `backend/storage` directory to ensure update safety and easy backups:
*   **Database (PostgreSQL):** Stored inside the Docker volume `postgres_data` (if containerized) or your native Postgres installation.
*   **OAuth Credentials Cache:** `backend/storage/data/oauth_tokens/`
*   **FAISS Vector Index:** `backend/storage/policies/<user_email>/index/index.faiss` (Isolated per department user)
*   **Extracted Attachments:** `backend/storage/attachments/`
*   **Policy Documents:** `backend/storage/policies/<user_email>/` (User-uploaded)

### 6.2 Manual Data Backup (Windows Command)
To safely backup the system, you must backup both the physical files and the PostgreSQL database. Run the following commands:

1. **Backup the physical files (Attachments, OAuth, FAISS):**
```powershell
Copy-Item -Path ".\backend\storage" -Destination ".\backup_storage_$(Get-Date -Format 'yyyyMMdd')" -Recurse
```

2. **Backup the PostgreSQL Database (if running via Docker):**
```powershell
docker exec -t grievance-postgres pg_dumpall -c -U postgres > ".\backup_db_$(Get-Date -Format 'yyyyMMdd').sql"
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
*   **Fix:** Open the **"Administrative Policy Console"** on the React dashboard and upload official policy documents to trigger the generation of the `index.faiss` vector database and policy chunks.

---

## 8. Appendix: Environment Variables Reference

The system utilizes separate environment files for the FastAPI backend and React frontend.

### 8.1 Backend Environment Variables (`backend/.env`)

The backend engine uses centralized `.env` configurations to dial in background sync behavior, local AI support, and RAG retrieval settings. Below is a comprehensive reference table of every parameter exposed in `backend/.env.example`.

> [!NOTE]
> **Docker Automates Infrastructure:** If you deploy using Docker (Method B), you do not need to worry about manually configuring Redis or PostgreSQL databases. Docker Compose will automatically spin up the required infrastructure and forcefully override the `DATABASE_TYPE` (to `postgres`) and `TASK_QUEUE_TYPE` (to `celery`) variables for you.

| Category | Variable Name | Default Value | Purpose & Comprehensive Impact |
| :--- | :--- | :--- | :--- |
| **Safeguards** | `SYNC_ENABLED` | `true` | **Global Sync Switch**: Instantly toggles the background Gmail synchronization worker on or off. |
| | `GMAIL_CALLS_PER_MINUTE_LIMIT` | `50` | **Rate Limiting**: The maximum number of Gmail API calls the sync engine is allowed to perform per minute, preventing rate-limiting blocks. |
| | `GLOBAL_SYNC_INTERVAL_SECONDS` | `600` | **Polled Refresh Rate**: How frequently (in seconds) the background task checks for new incoming grievance emails. |
| | `MANUAL_SYNC_COOLDOWN_SECONDS` | `60` | **Cooldown Guard**: Prevents users from overloading Google's servers by limiting manual inbox refreshes on the UI. |
| | `FULL_SYNC_DAYS` | `365` | **Sync Depth**: How far back in history (in days) the system crawls to build the initial inbox cache on first user login. |
| | `SYNC_JITTER_SECONDS` | `60` | **Anti-Bot Jitter**: Adds a random ± variance (in seconds) to background intervals so requests do not trigger bot detection systems. |
| | `SYNC_MAX_BACKOFF_SECONDS` | `3600` | **Network Resiliency**: The upper cap (1 hour) for the exponential backoff delay during network disconnects. |
| | `PRIORITY_LLM_MAX_CALLS` | `1` | **Rate Limiting**: Max LLM calls allowed per window for priority background tasks. |
| | `PRIORITY_LLM_WINDOW_SECONDS` | `60` | **Rate Limiting**: Time window for priority LLM calls. |
| | `AI_BATCH_SIZE` | `15` | **Processing Density**: How many emails for the AI to triage in a single background request. |
| **AI / LLM Keys** | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | *(None)* | **Primary LLM Access**: The central Google AI Studio API key used to generate replies and interact with Gemini models. |
| | `VERTEX_AI_PROJECT` | *(None)* | **Enterprise Routing**: Google Cloud Project ID to mandate Vertex AI (zero-data-training) models instead of standard developer APIs. |
| | `VERTEX_AI_LOCATION` | `asia-south1` | **Data Residency**: The geographical region for Vertex AI to strictly enforce Indian data residency laws. |
| | `GOOGLE_APPLICATION_CREDENTIALS` | `storage/keys/vertex-key.json` | **Vertex JSON Key**: Absolute or relative path to the Service Account JSON key for Vertex authentication. |
| | `PRIORITY_GOOGLE_API_KEY` | *(None)* | **Classification Key**: Dedicated key to process high-volume background priority ratings, preventing quota clashes. |
| | `CHATBOT_GEMINI_API_KEY` | *(None)* | **Assistant Key**: Dedicated key reserved for the real-time student grievance assistant chatbot in the UI. |
| **AI Models** | `AI_PREFER_LOCAL` | `false` | **Local Mode Switch**: Set to `true` to strictly route tasks to a local Ollama model (completely skipping and disabling any cloud API fallbacks). |
| | `PRIMARY_LOCAL_MODEL` | `llama3.2:3b` | **Ollama Model**: The target local LLM to load and execute via your local Ollama node. |
| | `OLLAMA_CONTEXT_LENGTH` | `16384` | **Local Token Cap**: The maximum context window loaded into local VRAM (recommended 8k-16k for complex grievances). |
| **Server / CORS**| `PORT` | `8000` | **Listening Port**: The port on which the FastAPI backend will run. |
| | `APP_ENV` | `development` | **Environment**: Sets the execution environment (`development`, `production`). Setting this to `production` **automatically disables and wipes the interactive API documentation (/docs)** to eliminate that attack surface. |
| | `CORS_ORIGINS` | *(Localhost defaults)* | **Cross-Origin**: Comma-separated list of allowed frontend origins to interact with the API. |
| | `AI_FALLBACK_MODELS` | *(List)* | **Resiliency Fallbacks**: Comma-separated list of models the system steps through. **Must use prefixes (`ollama/` for local, `models/` for Google).** |
| | `VISION_FALLBACK_MODELS` | *(List)* | **OCR Fallbacks**: Vision-enabled models used to read scanned attachments. **Must use prefixes (`ollama/` or `models/`).** |
| **RAG & Search** | `RAG_TOP_K` | `15` | **RAG Extraction**: Number of candidate chunks retrieved from the FAISS database for contextual re-ranking. |
| | `RAG_MIN_SCORE` | `0.35` | **Similarity Cutoff**: The strict cosine similarity threshold (0.0 to 1.0) required for a policy clause to be deemed relevant. |
| | `RAG_FINAL_LIMIT` | `12` | **Context Limit**: Maximum chunks included in the final context. |
| | `REPLY_SENDER_NAME` | `Grievance Support Desk` | **Reply Signature**: Configurable sender name used to sign off automated AI email replies. |
| | `RAG_MAX_UNIQUE_SECTIONS` | `0` | **Consistency Filter**: Max unique document sections to keep in context (0 to disable). |
| | `RAG_UNREPLIED_MAX` | `3` | **The "3" in 3+2 RAG**: The maximum number of recent, consecutive unreplied incoming citizen follow-up emails to crawl backwards. |
| | `RAG_ANCHOR_DEPTH` | `2` | **The "2" in 3+2 RAG**: The depth of the "Anchor Turn" representing the **last official Department Reply + its incoming Citizen Trigger** (the "handshake"). |
| | `RAG_SIMILARITY_THRESHOLD` | `0.35` | **Secondary Threshold**: Secondary semantic threshold for broader matches. |
| **Database & Queue** | `DATABASE_TYPE` | `sqlite` | **DB Engine**: Database backend selection (`sqlite` or `postgres`). *Warning: Setting this to `postgres` natively requires a running PostgreSQL server and a valid `DATABASE_URL`.* |
| | `DATABASE_URL` | *(Local URL)* | **DB Connection**: Connection string to the database (PostgreSQL/SQLite). |
| | `TASK_QUEUE_TYPE` | `threadpool` | **Queue Engine**: Task queue backend selection (`threadpool` or `celery`). *Warning: Setting this to `celery` natively without a running Redis server and a separate Celery worker terminal will break background processing.* |
| | `CELERY_BROKER_URL` / `_RESULT_BACKEND` | `redis://...` | **Distributed Queue**: URLs pointing to the Redis broker and result backend. |
| **OAuth & Security**| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | *(None)* | **Google OAuth Client**: Client keys from GCP Credentials for secure department-level user sign-in. |
| | `MICROSOFT_OAUTH_CLIENT_ID` / `_SECRET`| *(None)* | **Microsoft OAuth Client**: Client keys from Azure AD for secure Microsoft user sign-in. |
| | `OAUTH_ENCRYPTION_KEY` | *(None)* | **Credential Guard**: A symmetric Fernet key used to securely encrypt and decrypt OAuth tokens inside the database at rest. |
| | `APP_SESSION_SECRET` | *(None)* | **Session Guard**: Cryptographic signature secret used to sign session cookies and prevent session hijacking. |
| | `OAUTH_SUCCESS_REDIRECT_URL` | `http://localhost:3000` | **Auth Redirect**: Where to send users after successful authentication. |
| | `OAUTH_COOKIE_SECURE` | `false` | **HTTPS Requirement**: Set to 'true' in production to enforce secure cookies. |

### 8.2 Frontend Environment Variables (`frontend/.env`)

The frontend application uses client-side Vite environment variables (prefixed with `VITE_`) to configure API gateway routing and UI behaviors:

| Variable Name | Default Value | Purpose & Comprehensive Impact |
| :--- | :--- | :--- |
| `VITE_API_URL` | `/api` | **Backend API Base**: The central routing address pointing to your FastAPI backend gateway for general transactions (grievances, policy lists, etc.). |
| `VITE_REPLY_API_URL` | `/api` | **Response Engine Gateway**: Pointing to the backend API router responsible for triggering RAG-contextual email generation. |
| `VITE_DEV_PROXY_TARGET` | *(None)* | **Dev Proxy**: Used when running frontend natively via `npm run dev` to proxy requests to your local backend server (e.g. `http://localhost:8000`). Ignored in production. |
| `VITE_AUTH_STATUS_POLLING_SECONDS` | `60` | **Session Poller**: Frequency (in seconds) the UI queries the backend database to check if Google OAuth sync remains fully authenticated. |


