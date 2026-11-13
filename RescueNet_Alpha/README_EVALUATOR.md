# RescueNet FieldMesh — Portable Windows Evaluator & Deployment Package
> **Tagline:** *"When infrastructure fails, coordination survives."*

---

## 1. Quick Start: Single-Laptop Evaluator Demo (Procedure A)
*For evaluators, judges, and standalone demonstration on a single Windows laptop.*

Zero installation required. Does not require Python, pip, Node.js, VS Code, Git, or administrative privileges.

### 1-Click Launchers:
| Launcher | Description |
| :--- | :--- |
| **`RUN_DEMO.bat`** | **Start Here.** Executes an automated 3-node disaster coordination simulation over encrypted TCP links, demonstrating offline entry, transitive multi-hop sync, and resource escrow. |
| **`RUN_TESTS.bat`** | Runs the complete **75-test automated validation suite** and displays an instant PASS/FAIL integrity report. |
| **`LAUNCH_WEB_DASHBOARD.bat`** | Launches the **3D Digital Twin Command Center** on port 8000 and automatically opens `http://localhost:8000` in your web browser. |
| **`LAUNCH_ALPHA.bat`** | Starts **Station Alpha (Harbor Base Command)** on TCP port 8001 with strict zero-trust security. |
| **`LAUNCH_BETA.bat`** | Starts **Station Beta (Field Hospital Triage)** on TCP port 8002 with strict zero-trust security. |
| **`LAUNCH_GAMMA.bat`** | Starts **Station Gamma (Mountain Shelter Relay)** on TCP port 8003 with strict zero-trust security. |

---

## 2. Three-Physical-Laptop Deployment (Procedure B: Zero USB, Zero Internet)
*For real field deployment across three separate physical Windows 10/11 laptops over local Wi-Fi.*

### Physical Private Key Isolation Guarantee:
- **`RescueNet_Alpha.zip`** contains **only** Station Alpha's private key (`security/alpha-harbor/identity.key.enc`).
- **`RescueNet_Beta.zip`** contains **only** Station Beta's private key (`security/beta-hospital/identity.key.enc`).
- **`RescueNet_Gamma.zip`** contains **only** Station Gamma's private key (`security/gamma-mountain/identity.key.enc`).
- No laptop possesses or receives the private signing key of any other station.

### Step 1: Connect to Local Wi-Fi / Hotspot
1. Turn on a local Wi-Fi router OR activate a mobile phone hotspot.
2. **Turn mobile data (cellular/internet) OFF** to verify offline operation.
3. Connect all three laptops to the Wi-Fi network.
4. Check each laptop's IP address in Command Prompt via `ipconfig`:
   - Laptop Alpha: e.g. `192.168.43.10`
   - Laptop Beta: e.g. `192.168.43.20`
   - Laptop Gamma: e.g. `192.168.43.30`

### Step 2: Wireless Zero-USB Package Distribution
1. On Laptop Alpha, double-click **`START_WIFI_DISTRIBUTION_SERVER.bat`**.
2. **On Laptop Beta:** Open PowerShell and run:
   ```powershell
   Invoke-WebRequest -Uri "http://192.168.43.10:8888/RescueNet_Beta.zip" -OutFile "RescueNet_Beta.zip"
   Expand-Archive -Path "RescueNet_Beta.zip" -DestinationPath "C:\RescueNet"
   ```
3. **On Laptop Gamma:** Open PowerShell and run:
   ```powershell
   Invoke-WebRequest -Uri "http://192.168.43.10:8888/RescueNet_Gamma.zip" -OutFile "RescueNet_Gamma.zip"
   Expand-Archive -Path "RescueNet_Gamma.zip" -DestinationPath "C:\RescueNet"
   ```
4. On Laptop Alpha, press `Ctrl+C` to stop the distribution server.

### Step 3: Windows Firewall (Run once per laptop in PowerShell as Admin if prompted):
```powershell
New-NetFirewallRule -DisplayName "RescueNet Mesh" -Direction Inbound -LocalPort 8001-8003 -Protocol TCP -Action Allow
```

### Step 4: Launch Mesh Nodes with Strict Security
- **On Laptop Alpha:** Double-click `LAUNCH_ALPHA_LAN.bat` (Enter Beta: `192.168.43.20:8002`, Gamma: `192.168.43.30:8003`).
- **On Laptop Beta:** Double-click `LAUNCH_BETA_LAN.bat` (Enter Alpha: `192.168.43.10:8001`, Gamma: `192.168.43.30:8003`).
- **On Laptop Gamma:** Double-click `LAUNCH_GAMMA_LAN.bat` (Enter Alpha: `192.168.43.10:8001`, Beta: `192.168.43.20:8002`).

### Step 5: Test Verification & Synchronization
1. On Alpha's console, type:
   ```text
   EVENT shelter harbor-tent-1 CREATE {"name":"Harbor Evacuation Gym","capacity":250}
   SYNC beta-hospital
   ```
2. Verify on Beta that the event arrives with a valid Ed25519 signature.
3. **Partition Test:** Disconnect Wi-Fi on Gamma. Create an event on Alpha. Reconnect Gamma and run `SYNC alpha-harbor`. Confirm state converges without loss.

---

## 3. Cryptographic Security Model

- **Mutual Authentication:** Every station signs every event with its unique Ed25519 private key (`identity.key.enc`).
- **Encrypted Framing:** All peer-to-peer TCP frames are encrypted and authenticated using AES-256-GCM under the shared 256-bit Mesh Pre-Shared Key (`mesh_config.json`).
- **Zero-Trust Manifest:** Stations only communicate with peers pre-enrolled in `trusted_peers.json`. Unregistered connections or forged signatures are rejected instantly.
- **Process Privacy:** Secrets are loaded directly from disk configurations; keys are never exposed on the Windows process table or CLI parameters.
