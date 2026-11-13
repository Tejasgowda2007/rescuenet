"""
Automated Test Suite for RescueNet PWA, Service Worker, and Android Offline Capabilities.

Verifies:
1. Web App Manifest syntax, icons, and standalone PWA compliance for Android.
2. Service Worker presence, pre-cache assets, and offline fallback handlers.
3. Android icon assets (192px, 512px, maskable, SVG) verification.
4. Static frontend mounting and offline index fallback verification.
"""

import json
import os
import pytest
from api.server import app, DIST_DIR


def test_pwa_manifest_exists_and_valid():
    """Verify manifest.webmanifest exists in web/dist and contains mandatory PWA fields."""
    manifest_path = os.path.join(DIST_DIR, "manifest.webmanifest")
    assert os.path.isfile(manifest_path), f"manifest.webmanifest missing from {DIST_DIR}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("name") == "RescueNet — Offline Emergency Response"
    assert data.get("short_name") == "RescueNet"
    assert data.get("display") == "standalone"
    assert data.get("start_url") in ["./", "/"]
    assert "theme_color" in data
    assert "background_color" in data
    assert len(data.get("icons", [])) >= 2


def test_pwa_icon_assets_exist():
    """Verify that all required Android PWA icon files are present in web/dist."""
    required_icons = [
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-192.png",
        "icon-maskable-512.png",
        "icon.svg",
    ]
    for icon_name in required_icons:
        icon_path = os.path.join(DIST_DIR, icon_name)
        assert os.path.isfile(icon_path), f"PWA icon missing: {icon_path}"
        assert os.path.getsize(icon_path) > 100, f"Icon {icon_name} appears empty or corrupted"


def test_service_worker_asset_exists_and_configured():
    """Verify sw.js exists in web/dist and contains precaching and offline fallback."""
    sw_path = os.path.join(DIST_DIR, "sw.js")
    assert os.path.isfile(sw_path), f"sw.js missing from {DIST_DIR}"

    with open(sw_path, "r", encoding="utf-8") as f:
        sw_code = f.read()

    assert "caches.open" in sw_code
    assert "index.html" in sw_code
    assert "manifest.webmanifest" in sw_code
    assert "QUEUED_OFFLINE" in sw_code or "offline" in sw_code.lower()


def test_index_html_has_pwa_meta_tags():
    """Verify index.html contains manifest link and mobile web app meta tags."""
    index_path = os.path.join(DIST_DIR, "index.html")
    assert os.path.isfile(index_path)

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert "manifest.webmanifest" in html
    assert "theme-color" in html
    assert "mobile-web-app-capable" in html
    assert "viewport-fit=cover" in html


def test_fastapi_static_mount_serves_pwa_files():
    """Verify FastAPI routes mount StaticFiles correctly configured for root PWA delivery."""
    mounted_names = [getattr(route, "name", None) for route in app.routes]
    assert "frontend" in mounted_names

    frontend_route = next(r for r in app.routes if getattr(r, "name", None) == "frontend")
    static_app = frontend_route.app
    assert os.path.isdir(static_app.directory)

    # Ensure all required PWA files reside in the static directory
    for fname in ["manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png", "index.html"]:
        fpath = os.path.join(static_app.directory, fname)
        assert os.path.isfile(fpath), f"File {fname} not found in mounted static directory"
