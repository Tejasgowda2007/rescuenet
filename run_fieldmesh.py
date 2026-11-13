"""
RescueNet FieldMesh Unified Backend & Digital Twin Launcher.

Usage:
------
Run server:
  python run_fieldmesh.py --port 8000 --host 0.0.0.0

Opens:
- REST API & WebSocket: http://localhost:8000/docs
- Live Command Center:  http://localhost:8000/
"""

from __future__ import annotations
import argparse
import sys
import os

# Ensure rescuenet root on path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import socket
import uvicorn


def get_lan_ip() -> str:
    """Detect primary LAN IPv4 address for local Wi-Fi / Hotspot deployment."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="RescueNet FieldMesh Digital Twin Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument(
    "--port",
    type=int,
    default=int(os.environ.get("PORT", 8000)),
    help="Port to bind"
)
    parser.add_argument("--reload", action="store_true", help="Enable hot reload")
    args = parser.parse_args()

    lan_ip = get_lan_ip()

    print("\n" + "=" * 78)
    print("  RESCUENET FIELDMESH — DIGITAL TWIN SIMULATION BACKEND")
    print("  Tagline: 'When infrastructure fails, coordination survives.'")
    print("=" * 78)
    print(f"  * Terrain:        50 km x 50 km Mountainous & Dense Forest (Uttarakhand)")
    print(f"  * Physics:        LoRa 865-867 MHz WPC India ISM + Knife-Edge Diffraction")
    print(f"  * Routing:        Cost-Aware Dijkstra Multi-Hop with SimPy Discrete Events")
    print(f"  * Application:    RescueNet Event Sourcing, Version Vectors & Escrow Safety")
    print(f"  * Host Binding:   {args.host} (All Network Interfaces)")
    print(f"  * Local Access:   http://localhost:{args.port}/")
    print(f"  * LAN Access URL: http://{lan_ip}:{args.port}/ (For Alpha, Beta & Gamma laptops)")
    print(f"  * REST API Docs:  http://{lan_ip}:{args.port}/docs")
    print(f"  * WebSocket Feed: ws://{lan_ip}:{args.port}/ws")
    print("=" * 78 + "\n")

    uvicorn.run("api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
