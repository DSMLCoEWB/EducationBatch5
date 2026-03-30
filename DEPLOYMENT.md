# 🚀 DEPLOYMENT GUIDE

Complete guide to deploy the AI Grievance Management System to production.

## Table of Contents
1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Local Testing with Docker](#local-testing-with-docker)
3. [Environment Configuration](#environment-configuration)
4. [Backend Deployment](#backend-deployment)
5. [Frontend Deployment](#frontend-deployment)
6. [Database & Data](#database--data)
7. [Production URLs](#production-urls)

---

## Pre-Deployment Checklist

### ✅ Cleanup
- [x] **DELETE `reply-generator-main/` folder** (unused, increases repo size)
  ```bash
  rm -rf reply-generator-main/
  ```
- [x] **.gitignore updated** (prevents committing `.env` and sensitive files)
- [x] **requirements.txt updated** (added `gunicorn` for production server)

### ✅ Environment Files
- [x] `backend/.env.example` created (template for backend config)
- [x] `frontend/.env.example` created (template for frontend config)
- DO NOT commit `.env` files - create them locally from `.example`

### ✅ Dockerfiles
- [x] **backend/Dockerfile** updated for production (gunicorn, healthcheck)
- [x] **frontend/Dockerfile** created (multi-stage build with nginx)

---

## Local Testing with Docker

Before deploying to production, test locally with Docker Compose.

### 1. Create Local `.env` Files

**`backend/.env`:**
```bash
cp backend/.env.example backend/.env
# Edit backend/.env and add your GOOGLE_API_KEY
```

**`frontend/.env`:**
```bash
cp frontend/.env.example frontend/.env
# Default values OK for local testing
```

### 2. Start Services with Docker Compose

```bash
docker-compose up --build
```

**Services will be available at:**
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Health Check: http://localhost:8000/health

### 3. Test the Application

```bash
# Check backend health
curl http://localhost:8000/health

# Check categories endpoint
curl http://localhost:8000/categories

# Generate a reply
curl -X POST http://localhost:8000/generate-reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_content": "Please help with my grievance",
    "email_subject": "Grievance Request",
    "sender": "student@example.edu"
  }'
```

### 4. Stop Services

```bash
docker-compose down
```

---

## Environment Configuration

### Backend (`backend/.env`)

**REQUIRED:**
```env
GOOGLE_API_KEY=your_api_key_from_google_cloud
GEMINI_API_KEY=your_gemini_api_key
```

**CORS Configuration (for frontend domain):**
```env
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**Optional: RAG Tuning (keep defaults for most cases):**
```env
RAG_WARMUP=true              # Preload model on startup
RAG_RETRIEVAL_CONF_THRESHOLD=0.55
RAG_TOP_K=5
RAG_MIN_TRUST_SCORE=0.62
```

### Frontend (`frontend/.env`)

**Development:**
```env
VITE_API_URL=http://localhost:8000
VITE_REPLY_API_URL=http://localhost:8000
```

**Production:**
```env
VITE_API_URL=https://api.yourdomain.com
VITE_REPLY_API_URL=https://api.yourdomain.com
```

**Production Build:**
```bash
cd frontend
npm install
npm run build
# Output: frontend/build/ (ready to deploy)
```

---

## Backend Deployment

### Option 1: Render (Recommended - Free tier)

#### Step 1: Push to GitHub
```bash
git add .
git commit -m "Production ready"
git push origin main
```

#### Step 2: Deploy on Render
1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repo
4. Select branch: `main`
5. Configure:
   - Name: `grievance-backend`
   - Runtime: `Python 3.10`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn -w 4 -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker main:app`
   - Instance Type: `Free` (512 MB RAM)

#### Step 3: Add Environment Variables
Go to Settings → Environment Variables:
```
GOOGLE_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
CORS_ORIGINS=https://<frontend-domain>.onrender.com
RAG_WARMUP=true
```

#### Step 4: Create Data Directory
```bash
# SSH into Render instance and create data folder
mkdir -p /app/data
```

---

### Option 2: Railway (Free tier, $5 credit)

1. Go to https://railway.app
2. Create new project → Deploy from GitHub
3. Select repository
4. Auto-detect `Dockerfile`
5. Add environment variables
6. Deploy

**Pros:** Better free tier limits, easier environment setup

---

### Option 3: Docker on Your Own Server

```bash
# Build image
docker build -t grievance-backend:latest backend/

# Run container
docker run -d \
  -p 8000:8000 \
  -e GOOGLE_API_KEY=your_key \
  -e GEMINI_API_KEY=your_key \
  -e CORS_ORIGINS=https://yourdomain.com \
  -v /app/data:/app/data \
  -v /app/files:/app/files \
  --name grievance-backend \
  grievance-backend:latest

# View logs
docker logs -f grievance-backend
```

---

## Frontend Deployment

### Option 1: Render Static Site (Recommended)

1. Build locally:
   ```bash
   cd frontend
   npm run build
   ```

2. On Render:
   - New Static Site
   - Connect GitHub repo
   - Build Command: `npm install && npm run build`
   - Publish Directory: `build`
   - Auto-deploys on git push

### Option 2: Netlify

1. `npm run build`
2. Drag & drop `frontend/build` folder to Netlify
3. Set environment variable: `REACT_APP_API_URL`

### Option 3: S3 + CloudFront (AWS)

```bash
cd frontend
npm run build
aws s3 sync build/ s3://your-bucket/
```

---

## Database & Data

### Directory Structure
```
backend/
├── data/
│   ├── grievances.xlsx    (auto-generated on first run)
│   ├── policy_chunks.json (RAG policy data)
│   └── faiss.index        (RAG vector index)
└── files/
    └── *.eml              (email files to process)
```

### First Time Setup

**1. Load Initial Policy Data:**
```python
# From backend directory
python -c "
from rag_pipeline.ingest import ingest_policy_document
result = ingest_policy_document('path/to/policy.pdf', policy_id='policy_2024')
print(result)
"
```

**2. Process Email Files:**
```bash
# Place .eml files in backend/files/
# Then run:
python -c "from main import run; run()"
```

### Backup Strategy
```bash
# Daily backup to S3
aws s3 sync backend/data/ s3://your-bucket/backups/data-$(date +%Y%m%d)/
aws s3 sync backend/files/ s3://your-bucket/backups/files-$(date +%Y%m%d)/
```

---

## Production URLs

After deployment, your system will be available at:

| Service | URL |
|---------|-----|
| **Frontend** | `https://yourdomain.com` |
| **Backend API** | `https://yourdomain.com/api` or `https://api.yourdomain.com` |
| **Health Check** | `https://yourdomain.com/api/health` |
| **Categories** | `https://yourdomain.com/api/categories` |
| **Generate Reply** | `https://yourdomain.com/api/generate-reply` |

---

## 🔒 Security Checklist

- [ ] HTTPS enabled on all domains
- [ ] CORS properly configured (no `*` in production)
- [ ] `.env` files NOT in git
- [ ] `reply-generator-main/` folder DELETED
- [ ] API keys stored as environment variables
- [ ] Database backups automated
- [ ] Rate limiting enabled (if on API gateway)
- [ ] DDoS protection enabled

---

## 📊 Monitoring

### Health Checks
```bash
# Backend
curl https://yourdomain.com/api/health

# Response should be:
# {"status":"healthy","service":"AI Grievance Management Backend"}
```

### Logs
- **Render:** Dashboard → Logs
- **Railway:** Dashboard → Logs
- **Docker:** `docker logs <container-id>`

### Performance
- Cold start time: ~30-45s (model loading)
- Response time after warmup: <2s
- Memory: ~1.2GB for full stack

---

## Troubleshooting

### Issue: "CORS error in frontend"
**Solution:** Update `CORS_ORIGINS` environment variable to include frontend domain

### Issue: "Model loading timeout"
**Solution:** Increase Docker timeout, set `RAG_WARMUP=true` for preloading

### Issue: "Out of memory"
**Solution:** Use cheaper instance with CPU-only, reduce cache sizes

---

## Additional Resources

- [Render Docs](https://render.com/docs)
- [Railway Docs](https://docs.railway.app)
- [Docker Docs](https://docs.docker.com)
- [FastAPI Production](https://fastapi.tiangolo.com/deployment/)

