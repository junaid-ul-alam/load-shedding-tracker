# 🚀 Deploying Load Shedding Tracker to Render
### Go from local project → live public URL in ~10 minutes

---

## What you need before starting

- A free account at **github.com** (sign up if you don't have one)
- A free account at **render.com** (sign up with your GitHub account — easiest)
- Git installed on your PC ([git-scm.com](https://git-scm.com))

---

## Your final project structure

Make sure your folder looks exactly like this before uploading:

```
load-shedding-tracker/
├── app.py                  ← production-ready Flask app
├── wsgi.py                 ← gunicorn entry point
├── requirements.txt        ← flask, flask-cors, gunicorn
├── .gitignore              ← excludes .db files and __pycache__
└── templates/
    └── index.html          ← your frontend
```

> ⚠️ The `load_shedding.db` file is NOT included — the app creates it
> automatically on first startup.

---

## PART 1 — Upload project to GitHub

### Step 1 — Initialise a git repository

Open a terminal / Command Prompt inside your `load-shedding-tracker` folder:

```bash
cd path/to/load-shedding-tracker

git init
git add .
git commit -m "Initial commit — Load Shedding Tracker"
```

### Step 2 — Create a new GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `load-shedding-tracker`
3. Keep it **Public** (required for Render free tier)
4. Do **NOT** tick "Add README" or "Add .gitignore" — you already have them
5. Click **Create repository**

### Step 3 — Push your code to GitHub

GitHub will show you commands — they look like this (use YOUR username):

```bash
git remote add origin https://github.com/YOUR_USERNAME/load-shedding-tracker.git
git branch -M main
git push -u origin main
```

After this, refresh the GitHub page — you should see all your files there.

---

## PART 2 — Connect GitHub to Render

### Step 4 — Create a new Web Service on Render

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Click **Connect account** next to GitHub (if not already connected)
4. Find and select your `load-shedding-tracker` repository
5. Click **Connect**

### Step 5 — Configure the Web Service

Fill in these fields on the configuration page:

| Field | Value |
|---|---|
| **Name** | `load-shedding-tracker` (or any name you like) |
| **Region** | Singapore (closest to Dhaka) |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:app` |
| **Instance Type** | `Free` |

Everything else can stay as default.

### Step 6 — Deploy

Click **Create Web Service**.

Render will now:
1. Clone your GitHub repo
2. Run `pip install -r requirements.txt`
3. Run `gunicorn wsgi:app` (which calls `setup_database()` automatically)
4. Assign you a public URL

Watch the build logs — the whole process takes 1–3 minutes.

---

## PART 3 — Get your live URL

### Step 7 — Find your public URL

Once the status shows **Live** (green), look at the top of the page:

```
https://load-shedding-tracker.onrender.com
```

That's your public URL. Share it with anyone — it works from any device,
anywhere in the world.

---

## PART 4 — Keeping it alive (Free tier note)

Render's free tier **spins down** your app after 15 minutes of inactivity.
The next visitor will wait ~30 seconds for it to wake up.

**To prevent this**, you can use a free uptime service:

1. Go to [cron-job.org](https://cron-job.org) (free account)
2. Create a new cron job:
   - URL: `https://your-app-name.onrender.com/locations`
   - Schedule: Every 14 minutes
3. This pings your app regularly so it never goes to sleep

---

## PART 5 — Redeploying after code changes

Every time you update your code locally:

```bash
git add .
git commit -m "describe what you changed"
git push
```

Render detects the push automatically and redeploys within 1–2 minutes.
No manual steps needed.

---

## Important: SQLite on Render

Render's free tier uses an **ephemeral filesystem** — this means:

- ✅ The database works fine during a single deployment session
- ⚠️ All report data is **wiped** when you redeploy (push new code)
- ⚠️ The database may also reset after long periods of inactivity

This is fine for a demo project. If you want persistent data in the future,
upgrade to a managed database like:

- **Render PostgreSQL** (free 90-day trial, then paid)
- **Supabase** (free tier, PostgreSQL, no credit card)
- **PlanetScale** (free tier, MySQL)

---

## Quick reference

| What | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn wsgi:app` |
| Runtime | Python 3 |
| Recommended region | Singapore |
| Local dev command | `python app.py` |
| Port (local) | 5000 |
| Port (Render) | Auto-assigned via `PORT` env var |

---

## Troubleshooting

**Build fails with "No module named gunicorn"**
→ Make sure `gunicorn` is in your `requirements.txt`

**App shows "Internal Server Error"**
→ Check the Render logs tab for the Python traceback

**App spins up but shows blank page**
→ Make sure `templates/index.html` exists in your repo (check GitHub)

**"render: command not found" locally**
→ You don't need the Render CLI — everything is done through the dashboard

**Free tier URL is slow on first load**
→ Normal — the dyno is waking up. Set up cron-job.org (Part 4) to fix this.
