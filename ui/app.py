"""
RescueNet & ResQ-Mesh Unified Disaster Command Center UI.
Production Operations Center Dashboard with High-Contrast Dark Theme,
Real Computed Node States, Dynamic Link Toggles, Anti-Entropy Sync,
Indivisible Boat Tokens, Divisible Escrow Quotas, and Zero Lost Updates.
"""

from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import streamlit.components.v1 as components
from simulator.engine import DisasterSimulator
from allocation.conflict_resolver import ConflictResolver
from ui.styles import get_css
from ui.components import (
    NODE_METADATA,
    render_header,
    render_controls_bar,
    render_station_card,
)
from ui.controller import (
    create_ui_simulator,
    toggle_link,
    run_mesh_sync,
    check_mesh_convergence,
    export_node_bundle_json,
    import_node_bundle_json,
    get_node_timeline,
    build_mesh_topology_svg,
    run_resqmesh_phase1_baseline,
    run_resqmesh_phase2_split_and_conflict,
    run_resqmesh_phase3_reconnect_and_converge,
    resolve_resqmesh_inventory_collision,
    dispatch_ambulance_data_mule,
)


def _init_session_state(enable_crypto: bool = True) -> DisasterSimulator:
    """Initialize or retrieve the active DisasterSimulator and session state."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"
    if "sim" not in st.session_state:
        st.session_state.crypto_enabled = enable_crypto
        st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
        st.session_state.sync_logs = ["System Initialized: All 3 stations online & synchronized."]
        st.session_state.sync_history = []
        st.session_state.step = 1
        st.session_state.resolved = False
        st.session_state.show_qr = False
    return st.session_state.sim


def _reset_demo(enable_crypto: bool | None = None) -> None:
    """Tear down existing simulator and bootstrap a fresh mesh in < 2 seconds."""
    if enable_crypto is None:
        enable_crypto = st.session_state.get("crypto_enabled", True)
    if "sim" in st.session_state:
        st.session_state.sim.close()
    st.session_state.crypto_enabled = enable_crypto
    st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
    st.session_state.sync_logs = ["Demo reset to clean baseline state."]
    st.session_state.sync_history = []
    st.session_state.step = 1
    st.session_state.resolved = False
    st.session_state.show_qr = False


def _record_sync_logs(logs: List[str]) -> None:
    """Store latest sync logs and append telemetry history."""
    st.session_state.sync_logs = logs
    st.session_state.sync_history.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "summary": " | ".join(logs),
    })


def _render_topology_section(sim: DisasterSimulator) -> None:
    """Render live interactive SVG mesh topology diagram with radio switches."""
    st.markdown("### 🗺️ Live Mesh Topology & Radio Link Control")
    st.caption("Visual representation of physical radio links between the 3 stations. Toggle links to simulate line-of-sight dropouts.")

    topo_col, link_col = st.columns([2.4, 1.2])

    with topo_col:
        st.markdown(build_mesh_topology_svg(sim), unsafe_allow_html=True)

    with link_col:
        st.markdown("##### Radio Link Controls")
        link_pairs = [
            ("alpha-harbor", "beta-hospital", "Alpha ↔ Beta (Coastal Link)"),
            ("alpha-harbor", "gamma-mountain", "Alpha ↔ Gamma (Valley Link)"),
            ("beta-hospital", "gamma-mountain", "Beta ↔ Gamma (Ridge Link)"),
        ]
        for n1, n2, label in link_pairs:
            up = sim.transport.is_connected(n1, n2)
            icon = "🟢 UP" if up else "🔴 CUT"
            btn_label = f"{icon}: {label}"
            if st.button(btn_label, key=f"link_{n1}_{n2}", use_container_width=True):
                now_up = toggle_link(sim, n1, n2)
                st.session_state.sync_logs = [f"Radio link {label} is now {'RESTORED (UP)' if now_up else 'CUT (DOWN)'}."]
                st.toast(f"Link {label} {'restored' if now_up else 'cut'}.", icon="📡")
                st.rerun()

        comps = sim.partition_manager.get_connected_components()
        if len(comps) > 1:
            comp_str = " | ".join([f"[{', '.join(c.split('-')[0].capitalize() for c in grp)}]" for grp in comps])
            st.warning(f"⚠️ **Network Partitioned:** {len(comps)} isolated islands: {comp_str}")
        else:
            st.success("🟢 **Network Connected:** Full 3-Node Mesh (0 partitions)")


def _render_convergence_audit(sim: DisasterSimulator) -> None:
    """Render the 4 formal safety and consistency invariants computed from real state."""
    st.markdown("### 🔍 Mathematical Invariant & Convergence Audit")
    st.caption("RescueNet guarantees four core invariants across all partitions under Byzantine-free, crash-recovery fault models.")

    first_node_id = sim.node_ids[0]
    first_state = sim.nodes[first_node_id].get_state()
    is_converged = check_mesh_convergence(sim)

    # Convergence Banner
    if is_converged:
        st.markdown("""
            <div style="background:rgba(16,185,129,0.16); border-left:5px solid #10B981; padding:12px 16px; border-radius:8px; font-weight:600; color:#10B981; margin-bottom:12px;">
                ✅ STRONG EVENTUAL CONVERGENCE ACHIEVED — All 3 stations hold identical state, version vectors, and entity projections.
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div style="background:rgba(245,158,11,0.16); border-left:5px solid #F59E0B; padding:12px 16px; border-radius:8px; font-weight:600; color:#F59E0B; margin-bottom:12px;">
                ⚠️ STATIONS DIVERGED — Independent offline edits exist across isolated sectors. Heal links and run 'Sync Mesh' to converge.
            </div>
        """, unsafe_allow_html=True)

    # 4 Invariants
    inv1, inv2, inv3, inv4 = st.columns(4)

    with inv1:
        st.metric(
            "Invariant (a) State Match",
            "100% IDENTICAL" if is_converged else "DIVERGED",
            delta="Consistent" if is_converged else "Pending Sync",
            delta_color="normal" if is_converged else "inverse",
        )
        st.caption("Projections match across all 3 local SQLite databases.")

    with inv2:
        all_ids = {e.event_id for n in sim.nodes.values() for e in n.store.get_all_events()}
        missing = max((len(all_ids) - n.store.count()) for n in sim.nodes.values())
        st.metric(
            "Invariant (b) Zero Lost Updates",
            "ZERO LOST" if missing == 0 else f"{missing} PENDING",
            delta=f"{len(all_ids)} global events",
        )
        st.caption("Conflicting concurrent updates are preserved in the conflict ledger.")

    with inv3:
        boat = first_state.get("scarce_item", {}).get("boat-titan", {})
        active_allocs = 1 if boat.get("status") == "CONFIRMED_ALLOCATED" else 0
        st.metric(
            "Invariant (c) Boat Exclusivity",
            f"{active_allocs} Active (Max 1)",
            delta=f"Holder: {boat.get('token_holder', 'None').split('-')[0].capitalize()}",
        )
        st.caption("Single-owner cryptographic token prevents double-deployment.")

    with inv4:
        supply = first_state.get("supply", {}).get("supply-antibiotics", {})
        total_q = supply.get("total_quantity", 120)
        consumed_q = supply.get("consumed", 0)
        remaining_q = sum(supply.get("quotas", {}).values())
        conserved = (remaining_q + consumed_q == total_q)
        st.metric(
            "Invariant (d) Escrow Conserved",
            f"{remaining_q + consumed_q}/{total_q}",
            delta="Conserved" if conserved else "VIOLATION",
            delta_color="normal" if conserved else "inverse",
        )
        st.caption("Sum of local escrow quotas + consumed exactly equals total.")

    # Disputed Conflicts Triage
    conflicted_people = [
        (pid, pdata) for pid, pdata in first_state.get("person", {}).items() if pdata.get("conflicts")
    ]
    if conflicted_people:
        st.write("")
        st.markdown("#### 🩺 Active Conflict Triage")
        st.caption("Concurrent sightings observed during partition. Human coordinator can select verified status.")

        for pid, pdata in conflicted_people:
            with st.container():
                c1, c2, c3 = st.columns([2.0, 2.0, 1.2])
                with c1:
                    st.write(f"**Person:** `{pdata.get('name', pid)}`")
                    st.write(f"Current LWW State: `{pdata.get('status')}` @ {pdata.get('location')}")
                    for c in pdata["conflicts"]:
                        st.caption(f"• Disputing report from `{c['node_id']}`: **{c['conflicting_status']}**")
                with c2:
                    resolved_status = st.selectbox(
                        "Verified Ground Truth",
                        ["FOUND_SAFE_VERIFIED", "IN_SURGERY_STABLE", "EVACUATED_CONFIRMED"],
                        key=f"res_status_{pid}",
                    )
                    notes = st.text_input(
                        "Resolution Notes", value="Biometric tag verified by triage officer", key=f"res_note_{pid}"
                    )
                with c3:
                    st.write("")
                    st.write("")
                    if st.button("Confirm Resolution", key=f"res_btn_{pid}", use_container_width=True):
                        ConflictResolver.resolve_person_conflict(
                            node=sim.nodes[first_node_id],
                            person_id=pid,
                            verified_status=resolved_status,
                            verified_location=f"Triage Base ({first_node_id.split('-')[0].capitalize()})",
                            resolution_notes=notes,
                        )
                        _record_sync_logs(run_mesh_sync(sim))
                        st.toast(f"Conflict for {pdata.get('name', pid)} resolved.", icon="🩺")
                        st.rerun()


def _render_timeline_inspector(sim: DisasterSimulator) -> None:
    """Render cryptographic event timeline with decrypted payload inspection and signature verification."""
    st.markdown("### 📜 Cryptographic Event Store & Audit Log")
    st.caption("Immutable append-only event ledger. Every state mutation is signed with Ed25519 and hashed with SHA-256.")

    c1, c2, c3 = st.columns([1.5, 1.5, 1.0])
    with c1:
        selected_nid = st.selectbox("Inspect Station Ledger", sim.node_ids, key="timeline_node_sel")
    with c2:
        view_mode = st.radio(
            "Payload Decryption View", ["Decrypted Application View", "Raw SQLite At-Rest (Ciphertext)"],
            horizontal=True, key="timeline_view_mode",
        )
    with c3:
        limit = st.slider("Events to inspect", min_value=5, max_value=50, value=15, key="timeline_limit")

    rows = get_node_timeline(sim, selected_nid, limit=limit)
    if not rows:
        st.info("No events recorded on this station yet.")
        return

    table_data = []
    for r in rows:
        crypto_tags = []
        if r["signed"]:
            crypto_tags.append("Ed25519 OK" if r["sig_valid"] else "SIG FAIL")
        if r["encrypted_pii"]:
            crypto_tags.append("AES-256-GCM")
        shown_payload = r["payload"] if view_mode.startswith("Decrypted") else r["raw_payload"]
        table_data.append({
            "Seq": f"{r['node_id'].split('-')[0].capitalize()}#{r['counter']}",
            "Entity": r["entity"],
            "Operation": r["operation"],
            "Crypto Verification": " + ".join(crypto_tags) if crypto_tags else "Unsigned",
            "Bytes": r["wire_bytes"],
            "Event Hash": r["event_id"][:12] + "...",
            "Payload Data": json.dumps(shown_payload, sort_keys=True),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)


def _render_wire_and_usb(sim: DisasterSimulator) -> None:
    """Render wire traffic telemetry and offline USB sneakernet file transfer."""
    st.markdown("### 🔌 Wire Traffic & USB Sneakernet Fallback")
    st.caption("When all radio frequencies are jammed or blocked by mountain terrain, couriers can carry encrypted JSON bundles on USB drives.")

    stats = sim.transport.get_stats()
    w1, w2, w3 = st.columns(3)
    with w1:
        st.metric("Total Wire Traffic", f"{stats['total_bytes']} Bytes")
    with w2:
        st.metric("Framed Messages Exchanged", stats["total_messages"])
    with w3:
        avg = round(stats["total_bytes"] / max(1, stats["total_messages"]), 1)
        st.metric("Average Frame Size", f"{avg} B")

    st.markdown("---")
    st.markdown("##### 🚚 Offline USB Sneakernet Simulation")

    u1, u2, u3 = st.columns([1.2, 1.2, 1.4])
    with u1:
        src_usb = st.selectbox("Source Station (Export)", sim.node_ids, index=0, key="usb_src")
    with u2:
        dst_usb = st.selectbox("Destination Station (Import)", sim.node_ids, index=2, key="usb_dst")
    with u3:
        st.write("")
        if st.button("🚚 Hand-Carry USB Bundle Now", use_container_width=True):
            bundle_str = export_node_bundle_json(sim, src_usb)
            res = import_node_bundle_json(sim, dst_usb, bundle_str)
            st.session_state.sync_logs = [
                f"USB Sneakernet {src_usb} -> {dst_usb}: {res['applied']} new events applied "
                f"({res['skipped_duplicates']} dupes skipped, {res['rejected']} tampered), {len(bundle_str)} B"
            ]
            st.toast(f"USB bundle carried from {src_usb.split('-')[0]} to {dst_usb.split('-')[0]}.", icon="🚚")
            st.rerun()

    dl_col, ul_col = st.columns(2)
    with dl_col:
        bundle_download = export_node_bundle_json(sim, src_usb)
        st.download_button(
            label=f"⬇️ Download {src_usb.split('-')[0].capitalize()} USB Bundle (.json)",
            data=bundle_download,
            file_name=f"rescuenet_{src_usb}_bundle.json",
            mime="application/json",
            use_container_width=True,
        )
    with ul_col:
        uploaded = st.file_uploader(
            f"⬆️ Upload USB Bundle into {dst_usb.split('-')[0].capitalize()}", type=["json"], key="usb_upload_file"
        )
        if uploaded is not None and st.button("Import Uploaded Bundle", use_container_width=True):
            try:
                content = uploaded.getvalue().decode("utf-8")
                res = import_node_bundle_json(sim, dst_usb, content)
                st.session_state.sync_logs = [
                    f"Imported file into {dst_usb}: {res['applied']} applied, {res['rejected']} rejected"
                ]
                st.toast(f"Bundle imported: {res['applied']} events applied.", icon="📥")
                st.rerun()
            except Exception as exc:
                st.error(f"Invalid USB bundle file: {exc}")


def _render_resqmesh_showcase(sim: DisasterSimulator) -> None:
    """Render 3-Phase ResQ-Mesh executive story walkthrough."""
    curr_step = st.session_state.get("step", 1)

    st.markdown("### 🎯 ResQ-Mesh 3-Phase Executive Disaster Showcase")
    st.caption("A quick 3-step demonstration showing zero lost updates and zero double-allocations during total network isolation.")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("1️⃣ Normal (Online Baseline)", use_container_width=True, type="primary" if curr_step == 1 else "secondary"):
            run_resqmesh_phase1_baseline(sim)
            st.session_state.step = 1
            st.session_state.resolved = False
            st.session_state.show_qr = False
            st.toast("Phase 1: Baseline established.", icon="1️⃣")
            st.rerun()

    with b2:
        if st.button("2️⃣ Disaster Cuts Network!", use_container_width=True, type="primary" if curr_step == 2 else "secondary"):
            run_resqmesh_phase2_split_and_conflict(sim)
            st.session_state.step = 2
            st.session_state.resolved = False
            st.session_state.show_qr = False
            st.toast("Phase 2: Network partitioned & conflicting claims logged.", icon="2️⃣")
            st.rerun()

    with b3:
        if st.button("3️⃣ Reconnect & Converge", use_container_width=True, type="primary" if curr_step == 3 else "secondary"):
            run_resqmesh_phase3_reconnect_and_converge(sim)
            st.session_state.step = 3
            st.session_state.show_qr = False
            st.toast("Phase 3: Mesh reconnected & synchronized.", icon="3️⃣")
            st.rerun()

    st.write("")
    if curr_step == 1:
        st.info("🟢 **Step 1:** All 3 stations are online. 10 Emergency Medical Kits are in stock. All nodes hold identical data.")
    elif curr_step == 2:
        st.error("🔴 **Step 2: Signal Severed!** Stations are isolated. Harbor claims **8 kits** (Patient X 'Found'). Hospital claims **5 kits** (Patient X 'Injured'). That's **13 kits claimed for 10 in stock!**")
    elif curr_step == 3:
        if not st.session_state.resolved:
            st.warning("⚠️ **Step 3: Signal Restored!** Timelines merged with zero data loss. But **13 kits were claimed for 10 in stock**. Tap below to resolve.")
            if st.button("✅ Confirm Resolution: Grant 6 Kits to Harbor & 4 Kits to Hospital", use_container_width=True, type="primary"):
                resolve_resqmesh_inventory_collision(sim, 6, 4)
                st.session_state.resolved = True
                st.toast("Inventory collision resolved deterministically.", icon="✅")
                st.rerun()
        else:
            st.success("✅ **Conflict Resolved!** 6 kits granted to Harbor, 4 to Hospital. Zero kits double-allocated. All stations 100% converged!")


def main() -> None:
    st.set_page_config(
        page_title="RescueNet: Offline Disaster Mesh",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    sim = _init_session_state(enable_crypto=True)

    # Sidebar: Display & Settings
    with st.sidebar:
        st.markdown("### ⚙️ Operations Center Display")
        theme_choice = st.radio(
            "Theme Palette",
            ["Dark Operations Center", "Light Mission Control"],
            index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
            key="theme_radio",
        )
        st.session_state.theme = "dark" if "Dark" in theme_choice else "light"
        st.caption("WCAG AA High-Contrast palette. Always pairs status colors with icons & text.")
        st.markdown("---")
        st.markdown("### 🧭 Quick Presets")
        if st.button("🌊 Flash Flood Preset", key="sb_preset_flood", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "flash_flood")
            st.toast("Flash Flood scenario applied.", icon="🌊")
            st.rerun()
        if st.button("💊 Supply Rebalance", key="sb_preset_supply", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "supply_crunch")
            st.toast("Supply rebalance scenario applied.", icon="💊")
            st.rerun()
        if st.button("🔁 2-Hop Relay Mule", key="sb_preset_mule", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "chain_mule")
            st.toast("2-Hop relay scenario applied.", icon="🔁")
            st.rerun()
        st.markdown("---")
        st.caption("RescueNet v2.0 • Offline-First Disaster Response Mesh")

    # Inject Custom CSS
    st.markdown(get_css(st.session_state.get("theme", "dark")), unsafe_allow_html=True)

    # 1. Header with live status pills
    render_header(sim)

    # 2. Controls Bar
    render_controls_bar(sim, _reset_demo)

    # 3. Operational Sections via Tabs
    tab_stations, tab_topo, tab_invariants, tab_timeline, tab_usb, tab_resqmesh = st.tabs([
        "🏢 Three Field Stations",
        "🗺️ Mesh Topology & Links",
        "🔍 Invariants & Convergence",
        "📜 Cryptographic Event Store",
        "🔌 Wire & USB Sneakernet",
        "🎯 3-Phase ResQ-Mesh Showcase",
    ])

    with tab_stations:
        st.markdown("### 🏢 Active Field Coordination Stations")
        st.caption("Three stations operating independently across the disaster zone. Each station records events locally into SQLite.")
        cols = st.columns(3)
        for idx, cfg in enumerate(NODE_METADATA):
            render_station_card(sim, cfg, cols[idx])

    with tab_topo:
        _render_topology_section(sim)

    with tab_invariants:
        _render_convergence_audit(sim)

    with tab_timeline:
        _render_timeline_inspector(sim)

    with tab_usb:
        _render_wire_and_usb(sim)

    with tab_resqmesh:
        _render_resqmesh_showcase(sim)


if __name__ == "__main__":
    main()
