# RescueNet — Android Offline Deployment & Google Nearby Connections

This directory contains the native Android application for **RescueNet FieldMesh**, enabling offline peer-to-peer disaster communication directly between Android smartphones.

---

## 1. Architecture: Two Supported Android Operational Modes

RescueNet provides two distinct, production-grade modes for Android phones in disaster areas:

### Mode A: Browser PWA / Hotspot Mode (Zero Internet, Zero APK Install)
- **Mechanism**: One Android phone enables **Portable Hotspot** (or connects to an offline Wi-Fi travel router). Cellular data can be completely **disabled**.
- Any laptop or phone running `python run_fieldmesh.py --port 8000` serves the unified application over LAN.
- Other Android phones connect to the Wi-Fi hotspot and navigate to `http://<HOST_IP>:8000`.
- **Install as PWA**: Responders tap the **"Install App"** button (or Chrome menu &rarr; *Add to Home screen*).
- **Offline Self-Containment**:
  - The Service Worker (`sw.js`) caches the entire application shell (HTML, CSS, JS, icons).
  - Responders can disconnect from the hotspot, walk into zero-signal disaster zones, and open RescueNet directly from their home screen.
  - Incident, triage, and SOS reports are persisted in device **IndexedDB**.
  - When returning within Wi-Fi range of any mesh node, the **Outbox Queue** automatically flushes and synchronizes without data loss.

### Mode B: Native Android Google Nearby Connections (P2P Cluster)
- **Mechanism**: Direct phone-to-phone communication without an external router or hotspot.
- Uses Google Play Services Nearby Connections API (`com.google.android.gms:play-services-nearby:19.3.0`) with `Strategy.P2P_CLUSTER`.
- Devices simultaneously advertise and discover peers using Bluetooth Low Energy (BLE) and establish ad-hoc Wi-Fi Direct or hotspot links automatically.
- Wire Format: Uses the exact same 4-byte big-endian framed bytes:
  `[4-byte Length][Canonical JSON Payload]`
  signed with Ed25519 and encrypted with the 256-bit Mesh Pre-Shared Key (`AES-256-GCM`).
- Embedded WebView communicates with the native service via `@JavascriptInterface` (`window.AndroidNearby`).

---

## 2. Android Project Structure

```
android/
├── build.gradle.kts                      # Root Gradle build file
├── settings.gradle.kts                   # Project settings and plugin repositories
├── README.md                             # Android deployment & operational documentation
└── app/
    ├── build.gradle.kts                  # App module with Nearby Connections dependency
    └── src/
        └── main/
            ├── AndroidManifest.xml       # BLE, Wi-Fi Direct, and Location permissions
            └── java/org/rescuenet/offline/
                ├── MainActivity.kt       # WebView host and Android 12+ permission handling
                ├── NearbyMeshService.kt  # Google Nearby Connections P2P_CLUSTER engine
                └── NearbyWebBridge.kt    # JavaScript DOM bridge to window.AndroidNearby
```

---

## 3. How to Build the Android APK

### Prerequisites:
- Android Studio Ladybug / Meerkat (or JDK 17+ and Android SDK Command-line Tools)
- Android SDK Platform 35 (Android 15)

### Build Command:
Open a terminal in the `android/` directory:

```bash
# On Linux / macOS:
./gradlew assembleDebug

# On Windows:
gradlew.bat assembleDebug
```

The compiled APK will be generated at:
`android/app/build/outputs/apk/debug/app-debug.apk`

### Install onto Connected Android Phone:
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## 4. Running the Dashboard on Android Phones (Field Guide)

1. **Start the RescueNet Backend on Host**:
   ```bash
   python run_fieldmesh.py --port 8000
   ```
   Note the displayed LAN IP address (e.g., `http://192.168.43.10:8000`).

2. **Connect Android Phone to Hotspot**:
   - Turn on Wi-Fi on the phone and join the same network as the host.
   - Open Chrome / Edge and browse to `http://192.168.43.10:8000`.

3. **Install PWA**:
   - Tap the cyan **"Install App"** button on the top status bar.
   - Confirm "Add to Home screen".

4. **Verify Offline Functionality**:
   - Turn on **Airplane Mode** on the Android phone.
   - Close the browser and tap the **RescueNet** app icon from the home screen.
   - Observe the Amber **"OFFLINE FIELD MODE (LOCAL CACHE & INDEXEDDB ACTIVE)"** status bar.
   - Enter new incident reports or triage records in the Stations view.
   - Note the **"⚡ 1 offline action queued"** indicator.
   - Turn off Airplane Mode and tap **"Sync Now"** to verify automatic synchronization!
