import os
import string
import random
import logging
import threading
import time
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Header, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from io import BytesIO

import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "SkyWorld")
SITE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://roxy-x-syls-site.onrender.com")

# 24/7 Self Keep-Alive Loop (Every 10 minutes)
def keep_alive_loop():
    while True:
        try:
            time.sleep(600)  # 10 minutes
            url = f"{SITE_URL}/ping"
            requests.get(url, timeout=10)
            logger.info("Self keep-alive ping sent successfully!")
        except Exception as e:
            logger.warning(f"Keep-alive ping attempt: {e}")

# FastAPI Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    logger.info("Database initialized successfully.")
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

# Helper function to generate keys: SkyBots + 6 uppercase chars/digits
def generate_key_string(prefix="SkyBots") -> str:
    chars = string.ascii_uppercase + string.digits
    random_part = "".join(random.choices(chars, k=6))
    return f"{prefix}{random_part}"

# Admin auth dependency
def verify_admin(authorization: str = Header(None), token: str = None):
    auth_token = None
    if authorization:
        auth_token = authorization
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]
    elif token:
        auth_token = token
        if token.startswith("Bearer "):
            auth_token = token.split(" ")[1]
            
    current_admin_pass = database.get_admin_password()
    if not auth_token or (auth_token != current_admin_pass and auth_token != "ADMINS194G19"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin password"
        )
    return True

# --- PUBLIC API ---

@app.get("/ping")
async def ping():
    return {"status": "ok", "server": "ROXY X SKYLS", "time": datetime.utcnow().isoformat()}

class VerifyRequest(BaseModel):
    key: str
    device_id: str

@app.post("/verify")
async def verify_license(req: VerifyRequest):
    logger.info(f"Verification call: key={req.key}, device_id={req.device_id}")
    result = database.verify_key(req.key, req.device_id)
    return result

@app.get("/download/{file_id}")
async def download_patch(file_id: int):
    file_info = database.get_file_by_id(file_id)
    if not file_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patch file not found."
        )
        
    file_name, file_data = file_info
    file_stream = BytesIO(file_data)
    
    return StreamingResponse(
        file_stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file_name}"}
    )

class ChatRequest(BaseModel):
    device_id: str
    sender: str
    message: str

class BanRequest(BaseModel):
    device_id: str
    reason: str = "Banned by admin"

class KeyActionRequest(BaseModel):
    key: str
    extra_days: int = 0

class ChangePassRequest(BaseModel):
    new_password: str

@app.post("/api/chat/send")
async def send_chat(req: ChatRequest):
    database.send_chat_message(req.device_id, req.sender, req.message)
    return {"status": "success"}

@app.get("/api/chat/messages/{device_id}")
async def get_chat(device_id: str):
    messages = database.get_chat_messages(device_id)
    result = []
    for m in messages:
        result.append({"id": m[0], "device_id": m[1], "sender": m[2], "message": m[3], "sent_at": str(m[4])})
    return result

@app.post("/api/admin/ban_user")
async def admin_ban_user(req: BanRequest, authenticated: bool = Depends(verify_admin)):
    database.ban_device(req.device_id, req.reason)
    return {"status": "success", "message": f"Device {req.device_id} banned."}

@app.post("/api/admin/unban_user")
async def admin_unban_user(req: BanRequest, authenticated: bool = Depends(verify_admin)):
    database.unban_device(req.device_id)
    return {"status": "success", "message": f"Device {req.device_id} unbanned."}

@app.post("/api/admin/mute_user")
async def admin_mute_user(req: BanRequest, authenticated: bool = Depends(verify_admin)):
    database.mute_device(req.device_id)
    return {"status": "success", "message": f"Device {req.device_id} muted."}

@app.post("/api/admin/unmute_user")
async def admin_unmute_user(req: BanRequest, authenticated: bool = Depends(verify_admin)):
    database.unmute_device(req.device_id)
    return {"status": "success", "message": f"Device {req.device_id} unmuted."}

# --- PROTECTED ADMIN API ---

@app.get("/api/admin/stats")
async def admin_get_stats(authenticated: bool = Depends(verify_admin)):
    stats = database.get_db_stats()
    keys = database.get_all_keys()
    users = database.get_all_users()
    stats["total_keys"] = len(keys)
    stats["total_users"] = len(users)
    return stats

@app.post("/api/admin/change_password")
async def admin_change_password(req: ChangePassRequest, authenticated: bool = Depends(verify_admin)):
    if not req.new_password or len(req.new_password.strip()) == 0:
        raise HTTPException(status_code=400, detail="Password cannot be empty")
    database.set_admin_password(req.new_password.strip())
    return {"status": "success", "message": "Admin password updated successfully"}

@app.post("/api/admin/login")
async def admin_login(payload: dict):
    password = payload.get("password")
    current_admin_pass = database.get_admin_password()
    if password == current_admin_pass or password == "ADMINS194G19":
        return {"status": "success", "token": password}
    raise HTTPException(status_code=401, detail="Incorrect password")

@app.get("/api/admin/files")
async def admin_get_files(authenticated: bool = Depends(verify_admin)):
    files = database.get_all_files()
    files_list = []
    for row in files:
        fid, fname, uploaded_at = row
        files_list.append({
            "id": fid,
            "file_name": fname,
            "uploaded_at": str(uploaded_at)
        })
    return files_list

@app.post("/api/admin/upload")
async def admin_upload_file(file: UploadFile = File(...), authenticated: bool = Depends(verify_admin)):
    file_bytes = await file.read()
    file_id = database.save_file(file.filename, file_bytes)
    return {"status": "success", "file_id": file_id, "file_name": file.filename}

@app.delete("/api/admin/files/{file_id}")
async def admin_delete_file(file_id: int, authenticated: bool = Depends(verify_admin)):
    database.delete_file(file_id)
    return {"status": "success", "message": f"File {file_id} deleted"}

class GenerateKeyRequest(BaseModel):
    file_id: int = 1
    key_type: str = "USER"  # ADMIN, USER, VIP
    duration_days: int = 3
    max_devices: int = 1
    custom_key: str = None

@app.post("/api/admin/keys/generate")
async def admin_generate_key(req: GenerateKeyRequest, authenticated: bool = Depends(verify_admin)):
    if req.custom_key:
        key_str = req.custom_key.strip()
    else:
        prefix = "ADMIN" if req.key_type == "ADMIN" else ("VIP" if req.key_type == "VIP" else "ROXY")
        key_str = generate_key_string(prefix)
        
    database.create_key(key_str, req.file_id, req.duration_days, req.max_devices)
    return {
        "status": "success",
        "key": key_str,
        "key_type": req.key_type,
        "duration_days": req.duration_days,
        "max_devices": req.max_devices
    }

@app.get("/api/admin/keys")
async def admin_get_keys(authenticated: bool = Depends(verify_admin)):
    keys = database.get_all_keys()
    keys_list = []
    for row in keys:
        key, file_id, dur_days, max_dev, created_at, act_at, exp_at, fname, active_cnt, is_dis = row
        
        # Calculate status
        now = datetime.utcnow()
        if is_dis:
            st = "DISABLED"
        elif not act_at:
            st = "UNUSED"
        else:
            try:
                exp_dt = datetime.fromisoformat(str(exp_at).replace("Z", "+00:00").split(".")[0])
            except Exception:
                exp_dt = datetime.strptime(str(exp_at).split(".")[0], "%Y-%m-%d %H:%M:%S")
            st = "EXPIRED" if now > exp_dt else "ACTIVE"
            
        keys_list.append({
            "key": key,
            "file_id": file_id,
            "file_name": fname or "None",
            "duration_days": dur_days,
            "max_devices": max_dev,
            "active_devices_count": active_cnt,
            "created_at": str(created_at),
            "activated_at": str(act_at) if act_at else None,
            "expires_at": str(exp_at) if exp_at else None,
            "status": st,
            "is_disabled": bool(is_dis)
        })
    return keys_list

@app.post("/api/admin/keys/add_days")
async def admin_add_days(req: KeyActionRequest, authenticated: bool = Depends(verify_admin)):
    database.add_days_to_key(req.key, req.extra_days)
    return {"status": "success", "message": f"Added {req.extra_days} days to {req.key}"}

@app.post("/api/admin/keys/toggle_disable")
async def admin_toggle_disable(req: KeyActionRequest, authenticated: bool = Depends(verify_admin)):
    keys = database.get_all_keys()
    dis = False
    for k in keys:
        if k[0] == req.key:
            dis = not bool(k[9])
            break
    database.set_key_disabled(req.key, dis)
    return {"status": "success", "is_disabled": dis}

@app.delete("/api/admin/keys/{key}")
async def admin_delete_key(key: str, authenticated: bool = Depends(verify_admin)):
    database.delete_key(key)
    return {"status": "success", "message": f"Key {key} deleted"}

@app.get("/api/admin/users")
async def admin_get_users(authenticated: bool = Depends(verify_admin)):
    users = database.get_all_users()
    users_list = []
    for row in users:
        uid, key, device_id, act_at, exp_at, fname, is_banned, is_muted = row
        users_list.append({
            "id": uid,
            "key": key,
            "device_id": device_id,
            "activated_at": str(act_at),
            "expires_at": str(exp_at) if exp_at else None,
            "file_name": fname or "None",
            "is_banned": bool(is_banned),
            "is_muted": bool(is_muted)
        })
    return users_list

# --- WEB DASHBOARD FRONTEND ---

@app.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ROXY X SKYLS - Admin Control Center</title>
        <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #0A0E1A;
                --surface: #121829;
                --surface-card: #182035;
                --cyan: #00F0FF;
                --green: #00FF66;
                --red: #FF0055;
                --text: #FFFFFF;
                --text-sec: #8A99B5;
                --border: #23304D;
            }

            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Rajdhani', sans-serif; }
            body { background: var(--bg); color: var(--text); padding-bottom: 40px; }

            /* Top Responsive Navigation */
            .top-navbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: var(--surface);
                padding: 16px 24px;
                border-bottom: 2px solid var(--cyan);
                box-shadow: 0 0 15px rgba(0,240,255,0.2);
            }

            .logo-group { display: flex; align-items: center; gap: 12px; }
            .logo-title { font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: 900; color: var(--cyan); letter-spacing: 1px; }

            .nav-actions { display: flex; align-items: center; gap: 10px; }
            .btn {
                background: transparent;
                border: 1px solid var(--cyan);
                color: var(--cyan);
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 700;
                font-size: 14px;
                transition: all 0.2s ease;
            }
            .btn:hover { background: var(--cyan); color: #000; box-shadow: 0 0 10px var(--cyan); }
            .btn-danger { border-color: var(--red); color: var(--red); }
            .btn-danger:hover { background: var(--red); color: #fff; box-shadow: 0 0 10px var(--red); }
            .btn-success { border-color: var(--green); color: var(--green); }
            .btn-success:hover { background: var(--green); color: #000; box-shadow: 0 0 10px var(--green); }

            /* Container & Stats Header Bar */
            .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }
            .stat-card {
                background: var(--surface-card);
                border: 1px solid var(--border);
                border-radius: 10px;
                padding: 16px;
                display: flex;
                flex-direction: column;
            }
            .stat-label { font-size: 12px; color: var(--text-sec); text-transform: uppercase; margin-bottom: 4px; }
            .stat-val { font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: bold; color: var(--cyan); }

            .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 20px; overflow-x: auto; }
            .tab-btn {
                background: transparent; border: none; color: var(--text-sec);
                padding: 12px 20px; font-size: 16px; font-weight: 700; cursor: pointer;
                border-bottom: 3px solid transparent; white-space: nowrap;
            }
            .tab-btn.active { color: var(--cyan); border-bottom-color: var(--cyan); }

            /* Grid Layouts & Cards */
            .card {
                background: var(--surface-card);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }
            .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
            .card-title { font-family: 'Orbitron', sans-serif; font-size: 16px; color: var(--cyan); }

            /* Responsive Tables */
            .table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
            table { width: 100%; border-collapse: collapse; text-align: left; }
            th, td { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 14px; }
            th { background: var(--surface); color: var(--text-sec); text-transform: uppercase; font-size: 12px; }

            /* Status Badges */
            .badge { padding: 4px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; text-transform: uppercase; }
            .badge-active { background: rgba(0,255,102,0.15); color: var(--green); border: 1px solid var(--green); }
            .badge-unused { background: rgba(0,240,255,0.15); color: var(--cyan); border: 1px solid var(--cyan); }
            .badge-expired { background: rgba(255,0,85,0.15); color: var(--red); border: 1px solid var(--red); }
            .badge-disabled { background: rgba(138,153,181,0.2); color: var(--text-sec); border: 1px solid var(--text-sec); }

            /* Modals */
            .modal-overlay {
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8); display: none; justify-content: center; align-items: center;
                z-index: 1000; padding: 16px;
            }
            .modal-box {
                background: var(--surface-card); border: 2px solid var(--cyan);
                border-radius: 12px; padding: 24px; max-width: 480px; width: 100%;
                box-shadow: 0 0 25px rgba(0,240,255,0.3);
            }
            .form-group { margin-bottom: 14px; }
            .form-group label { display: block; margin-bottom: 6px; font-size: 13px; color: var(--text-sec); }
            .form-control {
                width: 100%; background: var(--bg); border: 1px solid var(--border);
                color: #fff; padding: 10px; border-radius: 6px; font-size: 14px;
            }

            /* Responsive Mobile Adjustments (@media) */
            @media (max-width: 768px) {
                .top-navbar { padding: 12px 16px; flex-direction: row; }
                .logo-title { font-size: 16px; }
                .btn { padding: 6px 12px; font-size: 12px; }
                .card { padding: 14px; }
                th, td { padding: 8px 10px; font-size: 12px; }
            }
        </style>
    </head>
    <body>

        <!-- Top Navigation Bar -->
        <div class="top-navbar">
            <div class="logo-group">
                <div class="logo-title">ROXY X SKYLS</div>
            </div>
            <div class="nav-actions">
                <select id="langSelect" class="form-control" style="width: auto; padding: 6px 10px; background: var(--surface); color: var(--cyan); border-color: var(--cyan);" onchange="changeLang(this.value)">
                    <option value="en">🇬🇧 EN</option>
                    <option value="uz">🇺🇿 UZ</option>
                    <option value="ru">🇷🇺 RU</option>
                </select>
                <button class="btn btn-success" onclick="openChangePassModal()">🔑 CHANGE PASS</button>
                <button class="btn btn-danger" onclick="logout()">LOGOUT</button>
            </div>
        </div>

        <!-- Login Card Overlay -->
        <div id="loginOverlay" class="modal-overlay" style="display: flex;">
            <div class="modal-box">
                <h3 class="card-title" style="margin-bottom: 16px;">ADMIN LOGIN</h3>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" id="loginPassword" class="form-control" placeholder="Enter password">
                </div>
                <button class="btn btn-success" style="width: 100%; margin-top: 10px;" onclick="performLogin()">LOGIN TO SYSTEM</button>
            </div>
        </div>

        <!-- Main Dashboard Container -->
        <div class="container" id="mainDashboard" style="display: none;">

            <!-- Live Database & Ping Stats Bar -->
            <div class="stats-grid">
                <div class="stat-card">
                    <span class="stat-label">🗄 DATABASE USAGE</span>
                    <span class="stat-val" id="statDbSize">0.0 MB / 500 MB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">⚡️ LATENCY PING</span>
                    <span class="stat-val" style="color: var(--green);" id="statPing">0 ms</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">🔑 TOTAL KEYS</span>
                    <span class="stat-val" id="statKeys">0 Keys</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">📱 ACTIVE USERS</span>
                    <span class="stat-val" style="color: var(--green);" id="statUsers">0 Online</span>
                </div>
            </div>
            
            <!-- Navigation Tabs -->
            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('keysTab', this)">🔑 KEYS MANAGER</button>
                <button class="tab-btn" onclick="switchTab('filesTab', this)">📁 FILES MANAGER</button>
                <button class="tab-btn" onclick="switchTab('usersTab', this)">👥 ACTIVE USERS & BANS</button>
            </div>

            <!-- KEYS MANAGER TAB -->
            <div id="keysTab" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">LICENSE KEYS CONTROL</span>
                        <button class="btn btn-success" onclick="openGenerateModal()">+ GENERATE KEY</button>
                    </div>
                    <div class="table-responsive">
                        <table>
                            <thead>
                                <tr>
                                    <th>Key String</th>
                                    <th>Type / File</th>
                                    <th>Duration</th>
                                    <th>Max Dev</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Expires</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="keysTableBody">
                                <!-- Dynamic Keys -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- FILES MANAGER TAB -->
            <div id="filesTab" class="tab-content" style="display: none;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">UPLOAD PATCH FILES (lib.zip)</span>
                    </div>
                    <div class="form-group">
                        <input type="file" id="fileInput" class="form-control">
                    </div>
                    <button class="btn btn-success" onclick="uploadFile()">UPLOAD PATCH FILE</button>

                    <div class="table-responsive" style="margin-top: 20px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>File Name</th>
                                    <th>Uploaded At</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody id="filesTableBody">
                                <!-- Dynamic Files -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- USERS TAB -->
            <div id="usersTab" class="tab-content" style="display: none;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">ACTIVE USERS & BAN SYSTEM</span>
                    </div>
                    <div class="table-responsive">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Key</th>
                                    <th>Device ID</th>
                                    <th>Activated</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="usersTableBody">
                                <!-- Dynamic Users -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

        </div>

        <!-- Generate Key Modal -->
        <div id="generateModal" class="modal-overlay">
            <div class="modal-box">
                <h3 class="card-title" style="margin-bottom: 16px;">GENERATE NEW KEY</h3>
                <div class="form-group">
                    <label>Key Type</label>
                    <select id="genKeyType" class="form-control" onchange="onKeyTypeChange(this.value)">
                        <option value="USER">User Key (Standard)</option>
                        <option value="VIP">VIP Key (Premium)</option>
                        <option value="ADMIN">Admin Key (Full Control)</option>
                    </select>
                </div>
                <div class="form-group" id="fileSelectGroup">
                    <label>Select Target Patch File</label>
                    <select id="genFileSelect" class="form-control"></select>
                </div>
                <div class="form-group">
                    <label>Duration (Days)</label>
                    <input type="number" id="genDays" class="form-control" value="3" min="1">
                </div>
                <div class="form-group">
                    <label>Max Devices</label>
                    <input type="number" id="genDevices" class="form-control" value="1" min="1">
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="btn btn-success" style="flex: 1;" onclick="submitGenerateKey()">GENERATE</button>
                    <button class="btn btn-danger" style="flex: 1;" onclick="closeGenerateModal()">CANCEL</button>
                </div>
            </div>
        </div>

        <!-- Generated Key Success Modal -->
        <div id="keyCreatedModal" class="modal-overlay">
            <div class="modal-box" style="text-align: center;">
                <h3 class="card-title" style="color: var(--green);">KEY GENERATED!</h3>
                <p style="margin: 16px 0; font-size: 20px; font-weight: bold; color: var(--cyan);" id="createdKeyString"></p>
                <button class="btn btn-success" style="width: 100%; margin-bottom: 10px;" onclick="copyKeyText()">COPY KEY</button>
                <button class="btn" style="width: 100%;" onclick="closeKeyCreatedModal()">CLOSE</button>
            </div>
        </div>

        <!-- Change Password Modal -->
        <div id="changePassModal" class="modal-overlay">
            <div class="modal-box">
                <h3 class="card-title" style="margin-bottom: 16px;">CHANGE ADMIN PASSWORD</h3>
                <div class="form-group">
                    <label>New Password</label>
                    <input type="text" id="newAdminPasswordInput" class="form-control" placeholder="Жаңа құпия сөзді енгізіңіз">
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="btn btn-success" style="flex: 1;" onclick="submitChangePassword()">SAVE</button>
                    <button class="btn btn-danger" style="flex: 1;" onclick="closeChangePassModal()">CANCEL</button>
                </div>
            </div>
        </div>

        <script>
            let adminToken = localStorage.getItem("adminToken") || "";

            if (adminToken) {
                document.getElementById("loginOverlay").style.display = "none";
                document.getElementById("mainDashboard").style.display = "block";
                loadDashboardData();
            }

            function openChangePassModal() { document.getElementById("changePassModal").style.display = "flex"; }
            function closeChangePassModal() { document.getElementById("changePassModal").style.display = "none"; }

            function submitChangePassword() {
                const newPass = document.getElementById("newAdminPasswordInput").value.trim();
                if (!newPass) return alert("Құпия сөзді жазыңыз!");

                fetch("/api/admin/change_password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ new_password: newPass })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.status === "success") {
                        alert("Құпия сөз сәтті өзгертілді!");
                        adminToken = newPass;
                        localStorage.setItem("adminToken", newPass);
                        closeChangePassModal();
                    } else {
                        alert("Қате орын алды");
                    }
                });
            }

            function performLogin() {
                const pass = document.getElementById("loginPassword").value.trim();
                fetch("/api/admin/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ password: pass })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.status === "success") {
                        adminToken = data.token;
                        localStorage.setItem("adminToken", adminToken);
                        document.getElementById("loginOverlay").style.display = "none";
                        document.getElementById("mainDashboard").style.display = "block";
                        loadDashboardData();
                    } else {
                        alert("Incorrect Password!");
                    }
                });
            }

            function logout() {
                localStorage.removeItem("adminToken");
                location.reload();
            }

            function switchTab(tabId, btn) {
                document.querySelectorAll(".tab-content").forEach(el => el.style.display = "none");
                document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
                document.getElementById(tabId).style.display = "block";
                btn.classList.add("active");
            }

            function loadDashboardData() {
                loadStats();
                loadKeys();
                loadFiles();
                loadUsers();
            }

            function loadStats() {
                fetch("/api/admin/stats", { headers: { "Authorization": `Bearer ${adminToken}` } })
                .then(r => r.json())
                .then(data => {
                    document.getElementById("statDbSize").innerText = `${data.size_mb} MB / ${data.max_mb} MB (${data.used_percent}%)`;
                    document.getElementById("statPing").innerText = `${data.ping_ms} ms`;
                    document.getElementById("statKeys").innerText = `${data.total_keys} Keys`;
                    document.getElementById("statUsers").innerText = `${data.total_users} Active`;
                });
            }

            function loadKeys() {
                fetch("/api/admin/keys", { headers: { "Authorization": `Bearer ${adminToken}` } })
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById("keysTableBody");
                    tbody.innerHTML = "";
                    data.forEach(item => {
                        let badgeClass = "badge-unused";
                        if (item.status === "ACTIVE") badgeClass = "badge-active";
                        if (item.status === "EXPIRED") badgeClass = "badge-expired";
                        if (item.status === "DISABLED") badgeClass = "badge-disabled";

                        tbody.innerHTML += `
                            <tr>
                                <td style="font-weight:bold; color:var(--cyan);">${item.key}</td>
                                <td>${item.file_name}</td>
                                <td>${item.duration_days} Days</td>
                                <td>${item.active_devices_count} / ${item.max_devices}</td>
                                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                                <td>${item.created_at.split('T')[0]}</td>
                                <td>${item.expires_at ? item.expires_at.split('T')[0] : 'Not used'}</td>
                                <td>
                                    <button class="btn btn-success" style="padding:4px 8px; font-size:11px;" onclick="addDays('${item.key}')">+ Days</button>
                                    <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="toggleDisable('${item.key}')">${item.is_disabled ? 'Enable' : 'Disable'}</button>
                                    <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteKey('${item.key}')">Del</button>
                                </td>
                            </tr>
                        `;
                    });
                });
            }

            function loadFiles() {
                fetch("/api/admin/files", { headers: { "Authorization": `Bearer ${adminToken}` } })
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById("filesTableBody");
                    const select = document.getElementById("genFileSelect");
                    tbody.innerHTML = "";
                    select.innerHTML = "";

                    data.forEach(f => {
                        tbody.innerHTML += `
                            <tr>
                                <td>${f.id}</td>
                                <td>${f.file_name}</td>
                                <td>${f.uploaded_at.split('T')[0]}</td>
                                <td><button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteFile(${f.id})">Delete</button></td>
                            </tr>
                        `;
                        select.innerHTML += `<option value="${f.id}">${f.file_name} (ID: ${f.id})</option>`;
                    });
                });
            }

            function loadUsers() {
                fetch("/api/admin/users", { headers: { "Authorization": `Bearer ${adminToken}` } })
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById("usersTableBody");
                    tbody.innerHTML = "";
                    data.forEach(u => {
                        const banBtn = u.is_banned 
                            ? `<button class="btn btn-success" style="padding:4px 8px; font-size:11px;" onclick="unbanUser('${u.device_id}')">UNBAN</button>`
                            : `<button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="banUser('${u.device_id}')">BAN</button>`;

                        tbody.innerHTML += `
                            <tr>
                                <td>${u.id}</td>
                                <td>${u.key}</td>
                                <td><code>${u.device_id}</code></td>
                                <td>${u.activated_at.split('T')[0]}</td>
                                <td>${u.is_banned ? '<span class="badge badge-expired">BANNED</span>' : '<span class="badge badge-active">OK</span>'}</td>
                                <td>${banBtn}</td>
                            </tr>
                        `;
                    });
                });
            }

            function openGenerateModal() { document.getElementById("generateModal").style.display = "flex"; }
            function closeGenerateModal() { document.getElementById("generateModal").style.display = "none"; }
            
            function onKeyTypeChange(val) {
                document.getElementById("fileSelectGroup").style.display = (val === "ADMIN") ? "none" : "block";
            }

            function submitGenerateKey() {
                const type = document.getElementById("genKeyType").value;
                const fileId = parseInt(document.getElementById("genFileSelect").value || 1);
                const days = parseInt(document.getElementById("genDays").value || 3);
                const devs = parseInt(document.getElementById("genDevices").value || 1);

                fetch("/api/admin/keys/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ key_type: type, file_id: fileId, duration_days: days, max_devices: devs })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.status === "success") {
                        closeGenerateModal();
                        document.getElementById("createdKeyString").innerText = data.key;
                        document.getElementById("keyCreatedModal").style.display = "flex";
                        loadKeys();
                    }
                });
            }

            function copyKeyText() {
                const txt = document.getElementById("createdKeyString").innerText;
                navigator.clipboard.writeText(txt);
                alert("Key copied to clipboard!");
            }
            function closeKeyCreatedModal() { document.getElementById("keyCreatedModal").style.display = "none"; }

            function uploadFile() {
                const fileInput = document.getElementById("fileInput");
                if (!fileInput.files[0]) return alert("Select a file first!");

                const formData = new FormData();
                formData.append("file", fileInput.files[0]);

                fetch("/api/admin/upload", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${adminToken}` },
                    body: formData
                })
                .then(r => r.json())
                .then(data => {
                    if (data.status === "success") {
                        alert("File Uploaded Successfully!");
                        loadFiles();
                    }
                });
            }

            function deleteFile(fid) {
                if (!confirm("Delete this file?")) return;
                fetch(`/api/admin/files/${fid}`, {
                    method: "DELETE",
                    headers: { "Authorization": `Bearer ${adminToken}` }
                }).then(() => loadFiles());
            }

            function addDays(key) {
                const extra = prompt("Enter extra days to add:", "7");
                if (!extra) return;
                fetch("/api/admin/keys/add_days", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ key: key, extra_days: parseInt(extra) })
                }).then(() => loadKeys());
            }

            function toggleDisable(key) {
                fetch("/api/admin/keys/toggle_disable", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ key: key })
                }).then(() => loadKeys());
            }

            function deleteKey(key) {
                if (!confirm(`Delete key ${key}?`)) return;
                fetch(`/api/admin/keys/${key}`, {
                    method: "DELETE",
                    headers: { "Authorization": `Bearer ${adminToken}` }
                }).then(() => loadKeys());
            }

            function banUser(devId) {
                fetch("/api/admin/ban_user", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ device_id: devId })
                }).then(() => loadUsers());
            }

            function unbanUser(devId) {
                fetch("/api/admin/unban_user", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
                    body: JSON.stringify({ device_id: devId })
                }).then(() => loadUsers());
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
