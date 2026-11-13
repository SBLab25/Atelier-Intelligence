# Cloud Deployment Guide — Atelier Intelligence

This guide walks you through deploying **Atelier Intelligence** to production on **Render** (Backend, Collector & MCP) and **Vercel** (Next.js Cockpit) using **Supabase** (PostgreSQL) for **$0/month**.

---

## Architecture Overview

```
[ External Website(s) ]
        │
        │ (1) Sends telemetry & loads tracker.js
        ▼
┌──────────────────────────────────────────────────────────┐
│  Render Free Web Service (Docker)                        │
│  https://atelier-backend.onrender.com                    │
│                                                          │
│  • Caddy Reverse Proxy (:10000 -> :8000, :8006)          │
│  • Telemetry Collector (/collect/batch, /tracker.js)     │
│  • FastAPI Backend API (/api/v1/*)                       │
│  • 5 MCP Microservices (:8001–:8005)                     │
└────────────────────────────┬─────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌───────────────────────────┐   ┌──────────────────────────┐
│  Supabase PostgreSQL      │   │  Vercel Hobby Tier       │
│  (Cloud Database)         │   │  https://atelier.vercel  │
│                           │   │  • Next.js 16 Cockpit UI │
│  • live_events            │   │  • Bento Analytics       │
│  • tracking_events        │   │  • Encrypted Sessions    │
│  • api_keys               │   └──────────────────────────┘
└───────────────────────────┘
```

---

## Step 1: Deploy Backend & Collector to Render ($0/month)

### Option A: 1-Click Blueprint Deploy (Recommended)
1. Sign in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Blueprint**.
3. Select your GitHub repository: `Atelier-Intelligence`.
4. Render will detect `render.yaml` and configure the Web Service automatically.
5. In the configuration prompt, provide your environment secrets:
   - **`DATABASE_URL`**: Your Supabase PostgreSQL connection string:
     ```text
     postgresql://postgres.zllyrypoqkdliaykmeku:Krishna%402510%40Sovan%402510@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres
     ```
   - **`GROQ_API_KEY`**: Your Groq API key (`gsk_...`).
   - **`CJI_CORS_ORIGINS`**: The origin of the external website you want to track (e.g. `https://mywebsite.com` or `https://app.mywebsite.com`).
   - **`CJI_API_CORS_ORIGINS`**: Leave blank for now (you will set it to your Vercel URL in Step 2).
6. Click **Apply**.

### Option B: Manual Web Service Deploy
1. Click **New +** $\rightarrow$ **Web Service**.
2. Select your repository.
3. Choose **Docker** as the Runtime.
4. Set the **Instance Type** to **Free**.
5. Under **Environment Variables**, add:
   - `CJI_ENV` = `production`
   - `CJI_MODE` = `realtime`
   - `JOURNEY_NAME` = `user_onboarding`
   - `CJI_LOG_FORMAT` = `json`
   - `CJI_LLM_PROVIDER` = `groq`
   - `LLM_MODEL` = `openai/gpt-oss-120b`
   - `DATABASE_URL` = *(Your Supabase connection string)*
   - `GROQ_API_KEY` = *(Your Groq key)*
   - `CJI_ADMIN_KEY` = *(Generate 32+ random characters)*
   - `CJI_API_CURSOR_SECRET` = *(Generate 32+ random characters)*
   - `CJI_CORS_ORIGINS` = `https://yourwebsite.com`
6. Click **Create Web Service**.

> 💡 **Copy Your Initial Cockpit Token:**  
> When the build finishes and the service starts, open the **Logs** tab in Render. Look for:  
> `🔑 INITIAL PRODUCTION COCKPIT API TOKEN: tok_...`  
> Copy this token — you will use it to log in to the Next.js Cockpit.

---

## Step 2: Deploy Next.js Cockpit to Vercel ($0/month)

1. Sign in to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New...** $\rightarrow$ **Project**.
3. Import your GitHub repository: `Atelier-Intelligence`.
4. In the configuration screen:
   - **Root Directory:** Click *Edit* and select **`frontend`**.
   - **Framework Preset:** Next.js (auto-detected).
5. Expand **Environment Variables** and add:
   - **`CJI_API_BASE_URL`**: Your Render backend URL (e.g. `https://atelier-backend-xxxx.onrender.com`).
   - **`CJI_SESSION_SECRET`**: A 32+ character random string (e.g. `9h7IrS2wVGiv1ud0wOmCADvsJM6gK5RlQ9bQE8W4Uw0`).
6. Click **Deploy**.

> 🔄 **Update CORS on Render:**  
> Once Vercel assigns your domain (e.g. `https://atelier-cockpit.vercel.app`), go back to your Render Dashboard $\rightarrow$ **Environment** $\rightarrow$ update `CJI_API_CORS_ORIGINS` with that URL.

---

## Step 3: Embed the Tracker on Your Website

To track real user behavior in real time, add this snippet to your external website before the closing `</head>` tag:

```html
<!-- Atelier Intelligence Realtime Tracker -->
<script>
  window.CJI_CONFIG = {
    api_key: "cji_dev_localtest",
    journey_name: "user_onboarding",
    collector_url: "https://<YOUR-RENDER-BACKEND-URL>/collect/batch"
  };
</script>
<script src="https://<YOUR-RENDER-BACKEND-URL>/tracker.js" async></script>
```

### Creating Custom Tracker Keys for Multiple Sites
You can create separate tracker API keys per website or journey:
- **Via the Cockpit:** Go to **Connections** tab in the Cockpit $\rightarrow$ Click **Register New Site** or generate a new key.
- **Via the API:** Send a `POST https://<YOUR-RENDER-URL>/admin/api-keys` with header `X-CJI-Admin-Key: <CJI_ADMIN_KEY>`.

---

## Step 4: Verify Real-Time Telemetry

1. Open your external website where the snippet was installed.
2. Click buttons, navigate between steps, or simulate an error.
3. Open your browser DevTools $\rightarrow$ **Network** tab: you will see periodic `POST /collect/batch` requests returning HTTP `200 Stored`.
4. Open your **Atelier Cockpit on Vercel**:
   - Sign in using your Cockpit API Token.
   - Go to the **Analytics** / **Overview** screen: live telemetry, drop-offs, rage clicks, and friction calculations will update in real time directly from your Supabase database!

---

## Pro-Tip: Preventing Render Inactivity Sleep ($0 24/7 Uptime)

Render's free tier spins down after 15 minutes without requests. To keep your Collector and API awake 24/7 with zero cold starts:

1. Go to a free uptime monitor such as [cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com).
2. Create a monitor to ping your liveness endpoint every **10 minutes**:
   ```text
   GET https://<YOUR-RENDER-BACKEND-URL>/health/live
   ```
3. Your Render container will stay warm 24/7 at **$0.00 cost**!
