# SkyBots License Server & Admin Web Dashboard

This server manages license verification for the Android application and provides a beautiful Web Admin Panel for generating keys and uploading the patch file (`lib.zip`).

## Features:
1. **FastAPI Web Server**: Exposes `POST /verify` and `GET /download` to check license keys and download the active patch file directly from the database.
2. **Web Admin Panel**: A secure, modern Dark Mode dashboard served at the root URL (e.g. `https://your-service.onrender.com/`) to:
   - Login securely with your admin password.
   - Generate new 3-day keys.
   - List active keys, showing their Device ID binding and expiration status.
   - Delete keys.
   - Upload new patch files (`lib.zip`) via drag-and-drop.
3. **Database BLOB Storage**: Uploaded patch files are stored directly in the database (SQLite or PostgreSQL) as binary data. This means the patch files are **100% persistent** and will not be lost when Render restarts!

---

## How to Deploy on Render (render.com)

1. **Create a Web Service on Render**:
   - Select **Build and deploy from a Git repository**.
   - Connect the repository containing the `skybots-server` files.

2. **Configure Settings**:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`

3. **Add Environment Variables**:
   Under the **Environment** tab, add:
   - `ADMIN_PASSWORD`: Choose a secure password for your Web Admin Panel (e.g., `MySuperSecurePass123`). If not set, it defaults to `SkyBotsAdmin123`.
   - `DATABASE_URL` *(Highly Recommended)*: Create a free **PostgreSQL Database** on Render, and copy its **Internal Database URL** or **External Connection String** into this variable. This ensures your keys and uploaded patch files are safely persisted forever. If not set, it will use a local SQLite file (`keys.db`), which will reset whenever the server restarts.

4. **Keep-Alive (UptimeRobot)**:
   - Go to [UptimeRobot](https://uptimerobot.com/) (free service).
   - Create a HTTP monitor pointing to your Render Web Service URL (e.g. `https://your-service.onrender.com/`).
   - This will ping your app every 5 minutes and keep the server awake 24/7!
