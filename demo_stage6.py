"""
RescueNet Stage 6 Demonstration:
Field-Level Encryption at Rest, Ed25519 Event Signing, and "Seized Device" Forensic Demo.

Run this script to see:
1. Field medical officer logging highly sensitive disaster records on an offline laptop.
2. Digital signatures preventing forged updates and message tampering.
3. Physical device seizure simulation: An attacker inspecting the raw SQLite database
   finds only encrypted AES-256-GCM ciphertexts with zero PII leakage.
4. An adversary's forged event rejected by peer nodes at the protocol boundary.
5. Authorized recovery unlocking full cleartext state with the volunteer passphrase.
"""

import os
import sys
import json
import sqlite3

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from crypto.ciphers import FieldEncryptor, CryptoError
from crypto.signatures import Signer
from crypto.keyring import NodeKeyring
from sync.node import Node
from transport.in_memory import InMemoryTransport
from transport.base import TransportMessage
from sync.messages import MSG_SYNC_DELTA
from events.event import Event


def print_title(title: str):
    print("\n" + "=" * 76)
    print(f" {title}")
    print("=" * 76)


def main():
    print_title("RescueNet Stage 6: Encryption at Rest & Seized Device Forensic Demo")

    db_path = "seized_medic_alpha.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # -------------------------------------------------------------
    # STEP 1: FIELD DOCTOR LOGS SENSITIVE HUMANITARIAN RECORDS
    # -------------------------------------------------------------
    print_title("Step 1: Authorized Field Doctor Logs Sensitive Patient Records")
    passphrase = "TriageResponder2026!Key"
    print(f"Volunteer: Dr. Maya (Node 'medic-alpha')")
    print(f"Passphrase: '{passphrase}' (PBKDF2-HMAC-SHA256, 100k rounds -> AES-256-GCM)")

    keyring_alpha = NodeKeyring("medic-alpha", passphrase=passphrase)
    node_alpha = Node("medic-alpha", db_path=db_path, keyring=keyring_alpha)

    print("\nLogging 3 critical events to local SQLite log:")
    e1 = node_alpha.record_event(
        entity_type="person",
        entity_id="patient-lucas",
        operation="CREATE",
        payload={
            "name": "Lucas Vance (Age 7)",
            "condition": "Severe Asthma, needs inhaler urgently",
            "last_seen": "Bridge 14 flooded zone",
            "contact": "Mother: Clara Vance +1-555-8821",
            "triage_urgency": "RED_CRITICAL",
        },
    )
    print(f"  + Logged missing child: {e1.entity_id} (Signed with Ed25519: {e1.signature[:16]}...)")

    e2 = node_alpha.record_event(
        entity_type="person",
        entity_id="patient-elena",
        operation="CREATE",
        payload={
            "name": "Elena Rostova",
            "condition": "Severe internal bleeding, Type O-Negative required",
            "current_location": "Hidden Basement Clinic, Sector 4",
            "triage_urgency": "RED_CRITICAL",
        },
    )
    print(f"  + Logged trauma victim:  {e2.entity_id} (Signed with Ed25519: {e2.signature[:16]}...)")

    e3 = node_alpha.record_event(
        entity_type="shelter",
        entity_id="shelter-secret",
        operation="CREATE",
        payload={
            "name": "St. Jude Undisclosed Underground Triage",
            "capacity": 35,
            "address": "404 River Road, Hidden Cellar Entrance",
            "status": "OPERATIONAL",
        },
    )
    print(f"  + Logged triage shelter: {e3.entity_id}")

    # Close and disconnect node (simulating device being dropped or left behind)
    node_alpha.close()
    print(f"\n[!] Laptop powered down. Raw SQLite database stored on disk at: {db_path}")

    # -------------------------------------------------------------
    # STEP 2: SIMULATED DEVICE SEIZURE / ATTACKER FORENSIC AUDIT
    # -------------------------------------------------------------
    print_title("Step 2: Device Seizure Simulation (Attacker Inspects Raw Disk)")
    print("A hostile actor or thief seizes the laptop and opens the SQLite database file directly:")

    raw_conn = sqlite3.connect(db_path)
    cur = raw_conn.cursor()
    cur.execute("SELECT event_id, entity_type, entity_id, payload_json, signature FROM events")
    rows = cur.fetchall()

    print(f"\nRaw Database Rows Dump ({len(rows)} events found):")
    for row in rows:
        eid, etype, entity_id, payload_json, sig = row
        print(f"\n  [EVENT: {eid[:12]}...] Entity: {etype}/{entity_id} | Signature: {sig[:16]}...")
        print(f"  Raw Payload Stored in SQLite:")
        # Print formatted raw payload
        parsed_payload = json.loads(payload_json)
        print(f"  {json.dumps(parsed_payload, indent=4)[:350]} ...")

    # Forensic check for sensitive strings
    raw_db_bytes = open(db_path, "rb").read()
    print("\n--- FORENSIC PLAINTEXT LEAKAGE SCAN ---")
    sensitive_words = ["Lucas Vance", "Severe Asthma", "Elena Rostova", "internal bleeding", "Hidden Cellar"]
    leaks = [w for w in sensitive_words if w.encode() in raw_db_bytes]

    if not leaks:
        print("  [PASSED] ZERO PLAINTEXT LEAKS FOUND in raw database binary!")
        print("  All names, medical notes, family contacts, and locations are encrypted.")
        print("  Non-sensitive operational metadata (triage_urgency: RED_CRITICAL) remains readable for routing.")
    else:
        print(f"  [FAILED] Leaks detected: {leaks}")

    raw_conn.close()

    # -------------------------------------------------------------
    # STEP 3: ATTACKER ATTEMPTS TO FORGE AN EVENT
    # -------------------------------------------------------------
    print_title("Step 3: Attacker Attempts Event Forgery (Anti-Tamper Test)")
    print("The attacker attempts to send a forged evacuation order to Base Camp (Node 'base-camp'):")
    print("Forged Message: 'Dr. Maya orders all teams to evacuate to Sector 9 (Ambush Zone)'")

    transport = InMemoryTransport()
    kr_base = NodeKeyring("base-camp")
    # Base Camp trusts Dr. Maya's known public key
    kr_base.register_peer("medic-alpha", keyring_alpha.public_key_hex)
    node_base = Node("base-camp", ":memory:", transport, keyring=kr_base)

    # Attacker signs event with their own rogue key
    attacker_priv, attacker_pub = Signer.generate_keypair()
    forged_event = Event(
        node_id="medic-alpha",  # Impersonating Dr. Maya!
        counter=4,
        timestamp=1000.0,
        entity_type="need",
        entity_id="fake-order",
        operation="CREATE",
        payload={"order": "Evacuate to Sector 9 immediately"},
    )
    forged_signed = Signer.sign_event(forged_event, attacker_priv)

    # Attacker transmits forged event over the network to Base Camp
    print("\nAttacker delivers forged message to Base Camp via transport...")
    attack_msg = TransportMessage(
        sender_id="attacker",
        recipient_id="base-camp",
        message_type=MSG_SYNC_DELTA,
        payload={"events": [forged_signed.to_dict()]},
    )
    transport.send(attack_msg)

    # Verify Base Camp rejected the forged event
    stored_at_base = node_base.store.get_event(forged_signed.event_id)
    if stored_at_base is None:
        print("  [SECURITY ALERT] Base Camp REJECTED the forged event!")
        print("  Cryptographic verification failed: Ed25519 signature does not match Dr. Maya's public key.")
        print("  The malicious payload was discarded and NEVER touched Base Camp's SQLite database.")
    else:
        print("  [SECURITY FAILURE] Forged event was accepted!")

    # -------------------------------------------------------------
    # STEP 4: AUTHORIZED RECOVERY WITH VOLUNTEER PASSPHRASE
    # -------------------------------------------------------------
    print_title("Step 4: Authorized Rescue Personnel Unlock Device")
    print("Emergency physician with valid passphrase unlocks the seized laptop:")

    # Initialize node with correct passphrase
    auth_keyring = NodeKeyring(
        node_id="medic-alpha",
        passphrase=passphrase,
        salt=keyring_alpha.salt,
        private_key=keyring_alpha.private_key,
        public_key_hex=keyring_alpha.public_key_hex,
    )
    unlocked_node = Node("medic-alpha", db_path=db_path, keyring=auth_keyring)

    state = unlocked_node.get_state()
    print("\nAuthorized Materialized State View:")
    print("  --- PATIENTS (DECRYPTED) ---")
    for pid, pdata in state["person"].items():
        print(f"  * [{pid}] {pdata['name']}")
        print(f"    - Condition: {pdata.get('condition')}")
        print(f"    - Location:  {pdata.get('current_location') or pdata.get('last_seen')}")
        if pdata.get("contact"):
            print(f"    - Contact:   {pdata['contact']}")

    print("\n  --- SHELTERS (DECRYPTED) ---")
    for sid, sdata in state["shelter"].items():
        print(f"  * [{sid}] {sdata['name']}")
        print(f"    - Address:  {sdata.get('address')}")
        print(f"    - Capacity: {sdata['capacity']}")

    unlocked_node.close()
    node_base.close()

    if os.path.exists(db_path):
        os.remove(db_path)

    print("\n[OK] Stage 6 security and seized device demonstration completed successfully!\n")


if __name__ == "__main__":
    main()
