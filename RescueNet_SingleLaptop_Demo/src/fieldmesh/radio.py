"""
FieldMesh Radio Propagation Model.

Provides physical-layer approximations for:
1. Long-Range LoRa Mesh Links (865-867 MHz Indian ISM band / 915 MHz).
2. High-Bandwidth Directional Microwave Point-to-Point Links (2.4 GHz / 5.8 GHz).

Models:
- 3D Euclidean distance and free-space path loss (FSPL).
- Single/multiple knife-edge diffraction terrain obstruction attenuation.
- Forest canopy clutter attenuation (modified Weissberger model).
- Monsoon rain / weather attenuation.
- Exact LoRa airtime, symbol duration, and packet serialization latency.
- Link margin, SNR, Packet Error Rate (PER), and effective throughput.
- Regulatory WPC (India) compliance metadata and disclaimers.
"""

from __future__ import annotations
import math
from typing import Dict, Any, Optional
from dataclasses import dataclass
from .terrain import LineOfSightResult


WPC_REGULATORY_NOTICE = (
    "WPC COMPLIANCE NOTICE (INDIA): The 865-867 MHz band is delicensed in India for low-power "
    "wireless devices under GSR 564(E) up to 1 Watt (30 dBm) ERP with 200 kHz channel bandwidth. "
    "All figures produced here are simulated mathematical estimates, not certified field RF measurements. "
    "Deployments on Indian territory require verification against latest WPC spectrum schedules."
)


@dataclass
class RadioProfile:
    name: str
    frequency_mhz: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    rx_antenna_gain_dbi: float
    rx_sensitivity_dbm: float
    bandwidth_khz: float
    spreading_factor: int       # 7 to 12 (LoRa only)
    coding_rate: int            # 5 for 4/5, 8 for 4/8
    max_payload_bytes: int
    is_directional: bool = False


# Default field radio profiles
LORA_DEFAULT_PROFILE = RadioProfile(
    name="LoRa-866MHz-SF9",
    frequency_mhz=866.0,
    tx_power_dbm=17.0,           # +17 dBm (50 mW) typical handheld transceiver
    tx_antenna_gain_dbi=2.5,     # Omnidirectional rubber-ducky dipole
    rx_antenna_gain_dbi=2.5,
    rx_sensitivity_dbm=-131.0,   # High sensitivity at SF9
    bandwidth_khz=125.0,
    spreading_factor=9,
    coding_rate=5,               # 4/5
    max_payload_bytes=222,
    is_directional=False,
)

DIRECTIONAL_P2P_PROFILE = RadioProfile(
    name="Microwave-5GHz-P2P",
    frequency_mhz=5800.0,
    tx_power_dbm=24.0,           # +24 dBm (250 mW)
    tx_antenna_gain_dbi=19.0,    # High-gain parabolic dish
    rx_antenna_gain_dbi=19.0,
    rx_sensitivity_dbm=-88.0,
    bandwidth_khz=20000.0,       # 20 MHz channel
    spreading_factor=0,
    coding_rate=0,
    max_payload_bytes=1500,
    is_directional=True,
)


@dataclass
class RadioLinkAssessment:
    profile_name: str
    frequency_mhz: float
    distance_3d_km: float
    has_los: bool
    free_space_loss_db: float
    terrain_diffraction_loss_db: float
    foliage_loss_db: float
    rain_loss_db: float
    total_path_loss_db: float
    tx_eirp_dbm: float
    rx_power_dbm: float
    rx_sensitivity_dbm: float
    link_margin_db: float
    snr_db: float
    link_status: str             # "ACTIVE", "DEGRADED", "BLOCKED"
    packet_error_rate: float     # 0.0 to 1.0
    nominal_bitrate_bps: float
    effective_throughput_bps: float
    one_way_latency_ms: float
    airtime_per_100b_ms: float
    regulatory_notice: str = WPC_REGULATORY_NOTICE


class RadioPropagationModel:
    """
    Computes terrain-aware radio propagation, link budgets, and packet error rates.
    """

    @staticmethod
    def calculate_free_space_loss(distance_m: float, frequency_mhz: float) -> float:
        """
        Free-Space Path Loss: FSPL(dB) = 20*log10(d) + 20*log10(f_MHz) - 27.55 (d in m).
        """
        if distance_m <= 1.0:
            return 0.0
        return 20.0 * math.log10(distance_m) + 20.0 * math.log10(frequency_mhz) - 27.55

    @staticmethod
    def calculate_knife_edge_diffraction(los: LineOfSightResult, frequency_mhz: float) -> float:
        r"""
        Single knife-edge diffraction loss via standard ITU-R P.526 approximation.
        v = h * sqrt( (2/lambda) * (1/d1 + 1/d2) )
        """
        if los.has_los and los.fresnel_clearance_ratio >= 0.6:
            return 0.0  # Clear Fresnel zone has negligible diffraction loss

        wavelength_m = 300.0 / frequency_mhz
        d_total_m = max(10.0, los.distance_3d_m)
        d1_m = d_total_m * 0.5
        d2_m = d_total_m * 0.5

        # h is positive when terrain penetrates above LOS ray
        h_m = los.max_obstruction_m if los.max_obstruction_m > 0 else -los.min_clearance_m

        geom_factor = math.sqrt((2.0 / wavelength_m) * (1.0 / d1_m + 1.0 / d2_m))
        v = h_m * geom_factor

        if v <= -0.7:
            return 0.0
        # Standard ITU-R P.526 piecewise approximation
        diff_loss = 6.9 + 20.0 * math.log10(math.sqrt((v - 0.1)**2 + 1.0) + v - 0.1)
        # Deep mountain shadowing can exceed 50 dB; clamp to 65 dB
        return max(0.0, min(65.0, diff_loss))

    @staticmethod
    def calculate_foliage_loss(distance_km: float, frequency_mhz: float, forest_density: float = 0.5) -> float:
        r"""
        Modified Weissberger foliage attenuation model for rays penetrating canopy:
        L = 1.33 * f^0.284 * d_trees^0.588 for d_trees <= 400m.
        """
        if forest_density < 0.1:
            return 0.0
        # Estimate path length through tree canopy (e.g. 50m to 200m near valley stations)
        d_canopy_m = min(180.0, distance_km * 1000.0 * 0.04 * forest_density)
        if d_canopy_m <= 1.0:
            return 0.0
        freq_ghz = frequency_mhz / 1000.0
        loss = 1.33 * (freq_ghz ** 0.284) * (d_canopy_m ** 0.588)
        return min(25.0, float(loss))

    @staticmethod
    def calculate_rain_loss(distance_km: float, frequency_mhz: float, rain_rate_mm_h: float = 0.0) -> float:
        """
        Approximate rainfall attenuation: negligible below 1 GHz; substantial at 5.8 GHz.
        """
        if rain_rate_mm_h <= 0.0 or distance_km <= 0.0:
            return 0.0
        # Frequency power-law scaling
        if frequency_mhz < 1000.0:
            k = 0.00003
            alpha = 1.05
        else:
            k = 0.003
            alpha = 1.15
        gamma = k * (rain_rate_mm_h ** alpha)
        return round(float(gamma * distance_km), 2)

    @staticmethod
    def calculate_lora_airtime(payload_bytes: int, profile: RadioProfile) -> float:
        """
        Calculate exact LoRa physical layer airtime in milliseconds for given payload size.
        Follows Semtech SX1261/SX1276 LoRa Air-Time calculation specification.
        """
        sf = profile.spreading_factor
        bw = profile.bandwidth_khz * 1000.0
        cr = profile.coding_rate

        # Symbol duration
        tsym_ms = (2.0 ** sf) / bw * 1000.0

        # Preamble duration (default 8 symbols + 4.25 sync)
        n_preamble = 8.0
        t_preamble_ms = (n_preamble + 4.25) * tsym_ms

        # Payload symbol count
        de = 1 if (sf >= 11 and bw <= 125000.0) else 0  # Low Data Rate Optimization
        h = 0  # Explicit header
        numerator = 8 * payload_bytes - 4 * sf + 28 + 16 - 20 * h
        denominator = 4 * (sf - 2 * de)
        n_payload = 8 + max(0, math.ceil(numerator / denominator) * cr)

        t_payload_ms = n_payload * tsym_ms
        return round(t_preamble_ms + t_payload_ms, 1)

    @staticmethod
    def evaluate_link(
        los: LineOfSightResult,
        profile: Optional[RadioProfile] = None,
        rain_rate_mm_h: float = 0.0,
        forest_density: float = 0.4,
    ) -> RadioLinkAssessment:
        """
        Compute full link budget, link margin, PER, and effective bandwidth.
        """
        prof = profile if profile is not None else LORA_DEFAULT_PROFILE

        dist_m = max(10.0, los.distance_3d_m)
        dist_km = dist_m / 1000.0

        fspl_db = RadioPropagationModel.calculate_free_space_loss(dist_m, prof.frequency_mhz)
        diff_db = RadioPropagationModel.calculate_knife_edge_diffraction(los, prof.frequency_mhz)
        foliage_db = RadioPropagationModel.calculate_foliage_loss(dist_km, prof.frequency_mhz, forest_density)
        rain_db = RadioPropagationModel.calculate_rain_loss(dist_km, prof.frequency_mhz, rain_rate_mm_h)

        # Directional microwave requires strict line of sight
        if prof.is_directional and not los.has_los:
            diff_db += 40.0  # Parabolic microwave beam drops abruptly when obstructed

        total_loss_db = fspl_db + diff_db + foliage_db + rain_db

        tx_eirp_dbm = prof.tx_power_dbm + prof.tx_antenna_gain_dbi
        rx_power_dbm = tx_eirp_dbm - total_loss_db + prof.rx_antenna_gain_dbi

        link_margin_db = rx_power_dbm - prof.rx_sensitivity_dbm

        # Compute SNR (Thermal noise floor = -174 dBm/Hz + 10*log10(BW) + 6 dB noise figure)
        noise_floor_dbm = -174.0 + 10.0 * math.log10(prof.bandwidth_khz * 1000.0) + 6.0
        snr_db = rx_power_dbm - noise_floor_dbm

        # Link status classification
        if link_margin_db >= 10.0:
            status = "ACTIVE"
            per = max(0.01, 1.0 / (1.0 + math.exp((link_margin_db - 8.0) * 0.4)))
        elif link_margin_db >= 0.0:
            status = "DEGRADED"
            # Degraded link experiences 15% to 65% packet loss
            per = 0.15 + (1.0 - (link_margin_db / 10.0)) * 0.50
        else:
            status = "BLOCKED"
            per = 1.0

        # Nominal bit rate
        if prof.spreading_factor > 0:
            # LoRa nominal bitrate = SF * (BW / 2^SF) * (4 / CR)
            nominal_bps = (
                prof.spreading_factor
                * ((prof.bandwidth_khz * 1000.0) / (2.0 ** prof.spreading_factor))
                * (4.0 / prof.coding_rate)
            )
            airtime_100b = RadioPropagationModel.calculate_lora_airtime(100, prof)
        else:
            # High-speed microwave P2P
            nominal_bps = 54_000_000.0 if link_margin_db > 15.0 else 12_000_000.0
            airtime_100b = 0.2  # < 1 ms

        effective_bps = round(nominal_bps * max(0.0, 1.0 - per), 1)

        # Propagation delay (speed of light 3e5 km/s) + channel serialization
        prop_delay_ms = (dist_km / 300_000.0) * 1000.0
        one_way_ms = round(prop_delay_ms + airtime_100b, 1)

        return RadioLinkAssessment(
            profile_name=prof.name,
            frequency_mhz=prof.frequency_mhz,
            distance_3d_km=round(dist_km, 2),
            has_los=los.has_los,
            free_space_loss_db=round(fspl_db, 1),
            terrain_diffraction_loss_db=round(diff_db, 1),
            foliage_loss_db=round(foliage_db, 1),
            rain_loss_db=round(rain_db, 1),
            total_path_loss_db=round(total_loss_db, 1),
            tx_eirp_dbm=round(tx_eirp_dbm, 1),
            rx_power_dbm=round(rx_power_dbm, 1),
            rx_sensitivity_dbm=round(prof.rx_sensitivity_dbm, 1),
            link_margin_db=round(link_margin_db, 1),
            snr_db=round(snr_db, 1),
            link_status=status,
            packet_error_rate=round(per, 3),
            nominal_bitrate_bps=round(nominal_bps, 1),
            effective_throughput_bps=effective_bps,
            one_way_latency_ms=one_way_ms,
            airtime_per_100b_ms=airtime_100b,
        )
