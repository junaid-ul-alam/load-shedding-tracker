# 📱 Mobile Access Guide
### How to open Load Shedding Tracker on your phone

---

## What changed in the code

Only **one line** in `app.py` was changed:

```python
# BEFORE — only this PC could connect
app.run(debug=True)

# AFTER — any device on your WiFi can connect
app.run(host="0.0.0.0", port=5000, debug=True)
```

`host="0.0.0.0"` tells Flask to listen on **all** network interfaces,
not just `localhost`. That's all it takes.

---

## Step 1 — Find your PC's IP address

### Windows
Open **Command Prompt** and run:
```
ipconfig
```
Look for **IPv4 Address** under your WiFi adapter:
```
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . : 192.168.1.105   ← this is your IP
```

### Mac
Open **Terminal** and run:
```
ipconfig getifaddr en0
```
Output will be something like: `192.168.1.105`

### Linux
Open **Terminal** and run:
```
hostname -I
```
First address shown is your local IP.

> **Tip:** When you run `python app.py`, the IP is now printed
> automatically in the startup message. Look for the 📱 line.

---

## Step 2 — Start the Flask server

```bash
python app.py
```

You will see:
```
==================================================
  ⚡ Load Shedding Tracker is running!
==================================================
  💻 On this PC     → http://127.0.0.1:5000
  📱 On mobile/WiFi → http://192.168.1.105:5000
==================================================
```

---

## Step 3 — Open on your mobile browser

1. Make sure your phone is connected to the **same WiFi** as your PC
2. Open any browser on your phone (Chrome, Firefox, Safari)
3. Type the address shown in the 📱 line, for example:
   ```
   http://192.168.1.105:5000
   ```
4. The app should load exactly as it does on your PC

---

## Troubleshooting — if the phone cannot connect

Work through these checks in order:

### ✅ Check 1 — Same WiFi network?
Your PC and phone must be on the **same router/WiFi**.
Mobile data (4G/5G) will not work — turn it off and use WiFi only.

### ✅ Check 2 — Is Flask actually running?
The terminal must show the startup message above.
If you closed it, run `python app.py` again.

### ✅ Check 3 — Windows Firewall (most common cause)

Windows Firewall blocks incoming connections by default.
Allow Flask through it with **one of these methods**:

**Method A — Quick (allow just port 5000):**
Open Command Prompt **as Administrator** and run:
```
netsh advfirewall firewall add rule name="Flask 5000" dir=in action=allow protocol=TCP localport=5000
```

**Method B — Through Windows Settings:**
1. Open **Windows Defender Firewall**
2. Click **Advanced Settings**
3. Click **Inbound Rules** → **New Rule**
4. Choose **Port** → Next
5. Enter `5000` → Next
6. Choose **Allow the connection** → Next → Next
7. Name it `Flask 5000` → Finish

To **undo** later (when project is done):
```
netsh advfirewall firewall delete rule name="Flask 5000"
```

### ✅ Check 4 — Mac Firewall

Usually off by default. To check:
**System Settings** → **Privacy & Security** → **Firewall**

If it is ON, click **Firewall Options** and add Python to the allowed list.

### ✅ Check 5 — Linux Firewall (UFW)

```bash
sudo ufw allow 5000
sudo ufw status       # verify it shows "5000/tcp  ALLOW"
```

### ✅ Check 6 — Antivirus software

Some antivirus programs (Avast, Kaspersky, etc.) have their own
firewall. Temporarily disable it or add an exception for port 5000.

### ✅ Check 7 — Try pinging the PC from your phone

Install a free "Ping" app on your phone and ping the PC's IP.
If ping fails, the issue is network-level (firewall, router isolation).
If ping works but Flask doesn't load, the issue is the Flask port.

---

## Security note

`host="0.0.0.0"` only exposes the app to your **local network**.
It does NOT expose it to the internet. Anyone outside your WiFi
router cannot reach it. This is safe for a local project.

When your project is done, you can switch back to:
```python
app.run(host="127.0.0.1", port=5000, debug=True)
```
to restrict access to your PC only again.

---

## Quick reference

| What | Address |
|---|---|
| From your PC | `http://127.0.0.1:5000` |
| From phone (same WiFi) | `http://<YOUR_PC_IP>:5000` |
| Find IP on Windows | `ipconfig` in CMD |
| Find IP on Mac | `ipconfig getifaddr en0` |
| Find IP on Linux | `hostname -I` |
| Allow firewall (Windows) | `netsh advfirewall firewall add rule name="Flask 5000" dir=in action=allow protocol=TCP localport=5000` |
