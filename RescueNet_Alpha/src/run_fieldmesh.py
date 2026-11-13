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

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="RescueNet FieldMesh Digital Twin Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload")
    args = parser.parse_args()

    print("\n" + "=" * 78)
    print("  RESCUENET FIELDMESH — DIGITAL TWIN SIMULATION BACKEND")
    print("  Tagline: 'When infrastructure fails, coordination survives.'")
    print("=" * 78)
    print(f"  * Terrain:       50 km x 50 km Mountainous & Dense Forest (Uttarakhand)")
    print(f"  * Physics:       LoRa 866 MHz + 5.8 GHz Microwave P2P + Knife-Edge Diffraction")
    print(f"  * Routing:       Cost-Aware Dijkstra Multi-Hop with SimPy Discrete Events")
    print(f"  * Application:   RescueNet Event Sourcing, Version Vectors & Escrow Safety")
    print(f"  * HTTP & WS API: http://localhost:{args.port}")
    print(f"  * API Docs:      http://localhost:{args.port}/docs")
    print("=" * 78 + "\n")

    uvicorn.run("api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
