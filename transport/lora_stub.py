"""
LoRa (Long Range Radio) Transport Stub for Sub-GHz Disaster Mesh Networks.

Design Decisions:
1. Why LoRa for Disasters?
   - In massive disasters (earthquakes, floods, grid collapse), Wi-Fi routers and cellular towers
     are dead, and Wi-Fi range is limited to ~30-50m through debris.
   - LoRa operates on sub-GHz ISM bands (868 MHz / 915 MHz / 433 MHz) and reaches 5 km to 15+ km
     line-of-sight with milliwatt power consumption, running on small batteries or solar panels.
2. Perfect Match for RescueNet's Compact Protocol:
   - LoRa has very limited bandwidth (~0.3 kbps to 5.5 kbps) and small packet sizes (~50-256 bytes).
   - RescueNet is purpose-built for this constraint: Version Vector handshakes ({node: counter})
     and delta-event payloads fit within standard LoRa MTU packet boundaries.
3. Architecture Decoupling:
   - Because RescueNet decouples the Storage and Sync layers from the Transport layer,
     swapping TCP or BLE for LoRa requires zero modifications to the core event log or state machine.
   - Hardware implementation connects to LoRa transceivers (e.g. Semtech SX1262, Heltec ESP32,
     or Meshtastic devices) via USB serial (pyserial) or UART/SPI.
"""

from __future__ import annotations
import json
from typing import Dict, Any, Callable, Optional
from .base import Transport, TransportMessage


class LoRaStubTransport(Transport):
    """
    LoRa Radio Transport implementation for long-range, low-bandwidth mesh synchronization.
    Interfaces with physical LoRa hardware modules (SX1262 / SX1276 / Meshtastic / Heltec ESP32)
    over a serial port (UART/USB).
    """

    def __init__(
        self,
        node_id: str,
        frequency_mhz: float = 868.0,
        bandwidth_khz: float = 125.0,
        spreading_factor: int = 7,
        serial_port: str = "/dev/ttyUSB0",
        baud_rate: int = 115200,
    ) -> None:
        self.node_id = node_id
        self.frequency_mhz = frequency_mhz
        self.bandwidth_khz = bandwidth_khz
        self.spreading_factor = spreading_factor
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.handler: Optional[Callable[[TransportMessage], Optional[TransportMessage]]] = None
        self._total_bytes: int = 0
        self._total_messages: int = 0

    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]]
    ) -> None:
        self.node_id = node_id
        self.handler = handler

    def unregister_node(self, node_id: str) -> None:
        self.handler = None

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Hardware-backed execution over physical LoRa serial interface:
        1. Encodes TransportMessage into compact JSON or binary CBOR.
        2. Splits payload if exceeding radio MTU (~250 bytes) into numbered fragments.
        3. Transmits over serial UART (AT+SEND or raw packet mode) to SX1262 / ESP32.
        4. Waits for peer ACK or delta sync reply packet on the configured RF channel.
        """
        raw_bytes = message.to_bytes()
        self._total_bytes += len(raw_bytes)
        self._total_messages += 1

        # In stub/simulation mode without attached physical LoRa USB dongle:
        # Real hardware integration:
        # import serial
        # with serial.Serial(self.serial_port, self.baud_rate, timeout=2.0) as ser:
        #     ser.write(raw_bytes + b"\n")
        #     reply = ser.readline()
        #     if reply:
        #         return TransportMessage.from_dict(json.loads(reply.decode("utf-8")))
        return None

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_bytes": self._total_bytes,
            "total_messages": self._total_messages,
            "frequency_mhz": int(self.frequency_mhz),
            "spreading_factor": self.spreading_factor,
        }

    def reset_stats(self) -> None:
        self._total_bytes = 0
        self._total_messages = 0
