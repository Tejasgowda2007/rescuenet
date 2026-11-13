# RescueNet: Offline Three-Laptop Deployment Guide

This guide describes how to deploy and operate the **RescueNet Decentralized Emergency Response Communication System** across three physically separate Windows laptops over a local Wi-Fi router or mobile phone hotspot with **zero internet connection**.

---

## 1. Network & Hardware Prerequisites

### Hardware Requirements
- **3x Windows Laptops** (Windows 10 or 11, 64-bit).
- **1x Local Wi-Fi Router or Mobile Phone Hotspot**:
  - Cellular Data must be toggled **OFF** on the hotspot device to prove 100% internet independence.
  - No external WAN / Internet cable needed.

### Node Roles & Identity Assignment
| Node ID | Assigned Name | Physical Laptop Role | Default Web Port | TCP Sync Port | UDP Discovery |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `alpha-harbor` | Alpha Harbor Base | Coastal Incident Command Post | `8000` | `8001` | `8002` |
| `beta-hospital` | Beta Field Hospital | Field Hospital & Triage Coordination | `8000` | `8001` | `8002` |
| `gamma-mountain` | Gamma Mountain Relay | Evacuation Shelter & Mountain Relay | `8000` | `8001` | `8002` |

---

## 2. Windows Network & Firewall Configuration

### Step 1: Connect All Three Laptops to the Same Local Wi-Fi / Hotspot
1. On your phone or battery-powered travel router, enable the Wi-Fi hotspot.
2. Ensure **Mobile Data / Cellular Internet is turned OFF**.
3. Connect Laptop Alpha, Laptop Beta, and Laptop Gamma to this Wi-Fi network.

### Step 2: Determine Each Laptop's Local IPv4 Address
Open PowerShell or Command Prompt on each laptop and run:
```cmd
ipconfig
```
Locate the IPv4 Address under `Wireless LAN adapter Wi-Fi` (e.g., `192.168.43.10`, `192.168.43.20`, `192.168.43.30`).

### Step 3: Configure Windows Firewall
Windows Defender Firewall may block incoming peer connections by default. Run the following command in an **Administrator PowerShell** on each laptop:

```powershell
# Open ports for RescueNet Mesh (HTTP 8000, TCP Sync 8001, UDP Discovery 8002)
New-NetFirewallRule -DisplayName "RescueNet Web UI" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "RescueNet TCP Sync" -Direction Inbound -LocalPort 8001 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "RescueNet UDP Discovery" -Direction Inbound -LocalPort 8002 -Protocol UDP -Action Allow
```
*(Alternatively, when prompted by Windows Security upon first launch, click **"Allow access"** on Private networks).*

---

## 3. Physical Node Launch Procedures

### Laptop Alpha (Harbor Command Center)
1. Double-click **`LAUNCH_ALPHA_HARBOR.bat`**.
2. The launcher will automatically start the node service on TCP port `8001`, start UDP discovery beacon on port `8002`, and open your browser to:
   ```
   http://localhost:8000/
   ```
   *(Operators on other devices on the LAN can also open `http://<Alpha_IP>:8000/`)*.

### Laptop Beta (Field Hospital)
1. Double-click **`LAUNCH_BETA_HOSPITAL.bat`**.
2. The launcher starts the beta node on TCP port `8001`, starts UDP discovery, and opens:
   ```
   http://localhost:8000/
   ```

### Laptop Gamma (Mountain Shelter & Relay)
1. Double-click **`LAUNCH_GAMMA_MOUNTAIN.bat`**.
2. The launcher starts the gamma node on TCP port `8001`, starts UDP discovery, and opens:
   ```
   http://localhost:8000/
   ```

---

## 4. Peer Discovery vs. Manual Fallback

### Mode A: Automatic Zero-Configuration (UDP Broadcast)
If your Wi-Fi router allows local UDP broadcasting, RescueNet's `PeerDiscoveryBeacon` broadcasts heartbeats every 2.5 seconds on UDP port `8002`.
- When Alpha turns on, it broadcasts its identity.
- When Beta turns on, Beta automatically discovers Alpha and initiates an anti-entropy sync.
- Both dashboards will display each other as **ONLINE** within 3 seconds.

### Mode B: Manual IP Configuration (AP Isolation Fallback)
Some mobile hotspots (especially carrier-locked phones) enforce **AP Client Isolation**, which blocks local UDP broadcast packets.

If peers do not appear automatically within 10 seconds:
1. Open the file **`peer_ips.txt`** in the RescueNet root directory on each laptop.
2. Add the IP addresses of the other two laptops:
   ```txt
   # On Laptop Alpha (specify Beta and Gamma's IPs):
   beta-hospital=192.168.43.20:8001
   gamma-mountain=192.168.43.30:8001
   ```
   ```txt
   # On Laptop Beta (specify Alpha and Gamma's IPs):
   alpha-harbor=192.168.43.10:8001
   gamma-mountain=192.168.43.30:8001
   ```
   ```txt
   # On Laptop Gamma (specify Alpha and Beta's IPs):
   alpha-harbor=192.168.43.10:8001
   beta-hospital=192.168.43.20:8001
   ```
3. Save the file. The node reads `peer_ips.txt` dynamically, or you can register peers directly from the dashboard or via CLI.

---

## 5. Live Operational Verification Workflow

To demonstrate genuine three-laptop offline coordination to mentors or judges:

### 1. Incident Creation (Alpha -> Beta & Gamma)
1. On Laptop Alpha, navigate to the **Incident Command** panel.
2. Click **"New Incident"**, enter:
   - **Title**: `Seawall Structural Breach`
   - **Severity**: `CRITICAL`
   - **Location**: `Pier 4 Harbor Warehouse`
3. Click **Submit**.
4. **Watch Laptop Beta and Laptop Gamma**: Within 100 milliseconds, without touching or refreshing either screen, the new incident appears live on both dashboards via WebSocket!

### 2. Casualty Triage & Medical Update (Beta -> Alpha & Gamma)
1. On Laptop Beta (Field Hospital), navigate to **Victims & Triage**.
2. Click **"Log Casualty"**:
   - **Name**: `Marcus Vance`
   - **Triage**: `RED (Immediate)`
   - **Medical Needs**: `Surgical stabilization for compound fracture`
3. Click **Submit**.
4. Both Alpha and Gamma's casualty counters and triage tables update immediately.

### 3. Emergency Alert & Acknowledgment (Gamma -> Alpha)
1. On Laptop Gamma (Mountain Shelter), click **"Broadcast Emergency Alert"**:
   - **Title**: `Mountain Ridge Rockslide`
   - **Message**: `Route 12 completely impassable to vehicular traffic`
2. Alpha receives the pop-up alert and clicks **"Acknowledge"**.
3. Gamma's alert banner updates from `UNACKNOWLEDGED` to `ACKNOWLEDGED by alpha-harbor`.

### 4. Offline Photo / Attachment Transfer
1. On Laptop Alpha, go to **Field Attachments** and upload a situational photo or map diagram.
2. The file is hashed with SHA-256 and synchronized over the TCP mesh.
3. On Laptop Beta and Gamma, the photo appears in the attachment gallery and can be downloaded or previewed directly.

### 5. Partition Tolerance & Store-and-Forward Reconnection
1. On Laptop Gamma, toggle Wi-Fi **OFF** (simulating walking out of radio range into a canyon).
2. On Laptop Alpha and Beta, log 3 new incidents and a field chat message.
3. Observe that Alpha and Beta sync normally while Gamma is recorded as **UNREACHABLE**.
4. On Laptop Gamma, toggle Wi-Fi **ON**.
5. Within 3 seconds, Gamma automatically reconnects, receives the missed delta stream, and catches up completely with zero data loss!

---

## 6. Single-Laptop Demonstration Mode

If testing on a single machine before physical deployment:
1. Double-click **`LAUNCH_LOCAL_3NODE_DEMO.bat`**.
2. This spawns 3 isolated processes on loopback:
   - Alpha on `http://localhost:8000/` (TCP 18001)
   - Beta on `http://localhost:8080/` (TCP 18002)
   - Gamma on `http://localhost:8090/` (TCP 18003)
3. Opens all three browser windows side-by-side for instant demonstration.
