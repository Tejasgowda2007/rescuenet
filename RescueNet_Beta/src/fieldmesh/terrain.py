"""
FieldMesh 3D Procedural Mountainous & Forest Terrain Engine.

Generates a realistic 50 km x 50 km digital twin of a disaster-affected mountainous
and forested zone with deterministic elevation, ridges, valleys, rivers, roads,
bridges, forest density, and settlements.

Includes 3D line-of-sight (LOS) ray-marching and Fresnel zone obstruction calculations
to feed the radio propagation model.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field


# Geographic anchor: Disaster response zone (50 km x 50 km)
BASE_LATITUDE = 30.3165   # Uttarakhand / Himalayan foothills region
BASE_LONGITUDE = 78.0322
TERRAIN_WIDTH_KM = 50.0
TERRAIN_HEIGHT_KM = 50.0

# Elevation bounds (meters)
MIN_ELEVATION_M = 320.0    # River valley floor
MAX_ELEVATION_M = 2840.0   # High rocky peak


@dataclass(frozen=True)
class TerrainFeature:
    id: str
    name: str
    feature_type: str  # river, road, trail, bridge, settlement, rescue_zone, ridge
    coordinates: List[Tuple[float, float]]  # [(x_km, y_km), ...]
    elevation_m: float
    description: str


@dataclass
class LineOfSightResult:
    has_los: bool
    distance_3d_m: float
    distance_2d_m: float
    tx_elevation_m: float
    rx_elevation_m: float
    min_clearance_m: float
    max_obstruction_m: float
    obstruction_point_km: Optional[Tuple[float, float, float]]
    first_fresnel_radius_m: float
    fresnel_clearance_ratio: float
    terrain_samples_count: int


class TerrainModel:
    """
    Procedural terrain model over a 50 km x 50 km disaster operations grid.
    Uses multi-octave deterministic value/gradient synthesis to produce realistic
    mountain ranges, river gorges, forested valleys, and isolated peaks.
    """

    def __init__(
        self,
        seed: int = 42,
        resolution: int = 256,  # 256x256 grid ~ 195 m per sample point
    ) -> None:
        self.seed = seed
        self.resolution = resolution
        self.width_km = TERRAIN_WIDTH_KM
        self.height_km = TERRAIN_HEIGHT_KM
        self.grid_spacing_km = self.width_km / (self.resolution - 1)

        # Generate elevation heightmap and feature maps
        self.elevation_map = self._generate_elevation()
        self.forest_map = self._generate_forest_density()
        self.features: List[TerrainFeature] = self._generate_features()

    def _generate_elevation(self) -> np.ndarray:
        """
        Synthesize deterministic 2D elevation grid with realistic geomorphology:
        - Major diagonal mountain ridge running SW to NE (barrier between Alpha and Charlie).
        - Secondary western spur and eastern alpine massif.
        - River gorge running north-to-south in the western valley.
        - High plateau in the northeast.
        """
        rng = np.random.default_rng(self.seed)
        res = self.resolution
        x = np.linspace(0, 1, res)
        y = np.linspace(0, 1, res)
        xx, yy = np.meshgrid(x, y)

        # Base regional tilt (higher in Northeast, lower in Southwest)
        elevation = 0.25 * (0.6 * xx + 0.8 * yy)

        # Primary Mountain Ridge (prominent diagonal barrier)
        # Ridge line centered around line y = -0.8 * x + 0.95
        dist_to_ridge = np.abs(yy + 0.75 * xx - 0.85) / np.sqrt(1 + 0.75**2)
        primary_ridge = np.exp(- (dist_to_ridge / 0.12)**2) * 0.55
        elevation += primary_ridge

        # Secondary Alpine Peak Massif (North-Central/East)
        peak_dist1 = np.sqrt((xx - 0.82)**2 + (yy - 0.68)**2)
        peak1 = np.exp(- (peak_dist1 / 0.14)**2) * 0.45
        elevation += peak1

        # High Ridge for Relay Echo (Center-East summit at ~22 km, 25 km)
        echo_dist = np.sqrt((xx - 0.46)**2 + (yy - 0.50)**2)
        echo_ridge = np.exp(- (echo_dist / 0.08)**2) * 0.50
        elevation += echo_ridge

        # Western River Gorge & Valley (Depression where HQ Alpha and Bravo valley sit)
        river_axis = 0.22 + 0.08 * np.sin(yy * 6.0)
        dist_to_river = np.abs(xx - river_axis)
        gorge_cut = -0.22 * np.exp(- (dist_to_river / 0.07)**2)
        elevation += gorge_cut

        # Multi-octave sinusoidal & fractal noise for rugged terrain texture
        octaves = [
            (2.5, 0.12),
            (5.0, 0.06),
            (11.0, 0.03),
            (23.0, 0.015),
            (47.0, 0.007),
        ]
        for freq, amp in octaves:
            # Deterministic phase offsets
            phase_x = float(rng.uniform(0, 2 * np.pi))
            phase_y = float(rng.uniform(0, 2 * np.pi))
            octave_layer = np.sin(freq * xx * 2 * np.pi + phase_x) * np.cos(freq * yy * 2 * np.pi + phase_y)
            elevation += amp * octave_layer

        # Normalize to [0, 1] then scale to [MIN_ELEVATION_M, MAX_ELEVATION_M]
        elevation = (elevation - elevation.min()) / (elevation.max() - elevation.min())
        elevation_meters = MIN_ELEVATION_M + elevation * (MAX_ELEVATION_M - MIN_ELEVATION_M)

        # Smooth slightly to preserve natural slope angles
        from scipy.ndimage import gaussian_filter
        elevation_meters = gaussian_filter(elevation_meters, sigma=1.2)
        return elevation_meters

    def _generate_forest_density(self) -> np.ndarray:
        """
        Generate vegetation density map (0.0 = bare rock/snow, 1.0 = dense temperate forest).
        Dense in mid-valleys (400m - 1500m), sparse on high peaks (> 2000m).
        """
        res = self.resolution
        elev = self.elevation_map
        density = np.zeros_like(elev)

        # Optimal forest zone: 500m to 1600m
        mask = (elev >= 450.0) & (elev <= 1900.0)
        density[mask] = 0.85 * np.exp(- ((elev[mask] - 1000.0) / 450.0)**2)
        # High peaks: rocky/alpine tundra
        high_peaks = elev > 2100.0
        density[high_peaks] = 0.05

        return np.clip(density, 0.0, 1.0)

    def _generate_features(self) -> List[TerrainFeature]:
        """Define strategic geographic reference points across the 50x50 km area."""
        features = [
            TerrainFeature(
                id="feat-river-bhagirathi",
                name="Bhagirathi Gorge River",
                feature_type="river",
                coordinates=[(10.0, 0.0), (12.5, 12.0), (15.0, 25.0), (18.0, 38.0), (20.0, 50.0)],
                elevation_m=380.0,
                description="Fast-flowing mountain river running through the western valley.",
            ),
            TerrainFeature(
                id="feat-ridge-trishul",
                name="Trishul Barrier Ridge",
                feature_type="ridge",
                coordinates=[(15.0, 45.0), (25.0, 32.0), (35.0, 18.0), (45.0, 5.0)],
                elevation_m=2420.0,
                description="High rocky mountain ridge rising to 2,420m that severs radio line-of-sight.",
            ),
            TerrainFeature(
                id="feat-bridge-valley",
                name="Suspension Bridge #4",
                feature_type="bridge",
                coordinates=[(15.2, 23.0)],
                elevation_m=510.0,
                description="Critical vehicle bridge connecting Highway 10 to Bravo Medical Camp.",
            ),
            TerrainFeature(
                id="feat-road-hwy10",
                name="National Disaster Highway 10",
                feature_type="road",
                coordinates=[(8.0, 0.0), (10.5, 8.2), (14.0, 20.0), (22.0, 35.0)],
                elevation_m=460.0,
                description="Primary ground evacuation artery along the valley.",
            ),
            TerrainFeature(
                id="feat-settlement-dhar",
                name="Dhar Isolated Settlement",
                feature_type="settlement",
                coordinates=[(35.5, 36.0)],
                elevation_m=1680.0,
                description="Cut off mountain village with ~350 inhabitants requiring medical aid.",
            ),
            TerrainFeature(
                id="feat-zone-mudslide",
                name="Zone Charlie Mudslide Sector",
                feature_type="rescue_zone",
                coordinates=[(38.0, 40.0)],
                elevation_m=1880.0,
                description="Active search and rescue sector for missing tourists and residents.",
            ),
        ]
        return features

    def get_elevation_at(self, x_km: float, y_km: float) -> float:
        """
        Query interpolated terrain elevation at arbitrary continuous (x, y) in kilometers.
        Clamped to [0, 50] km bounds.
        """
        x_clamped = max(0.0, min(self.width_km, float(x_km)))
        y_clamped = max(0.0, min(self.height_km, float(y_km)))

        col = (x_clamped / self.width_km) * (self.resolution - 1)
        row = (y_clamped / self.height_km) * (self.resolution - 1)

        c0, r0 = int(math.floor(col)), int(math.floor(row))
        c1 = min(self.resolution - 1, c0 + 1)
        r1 = min(self.resolution - 1, r0 + 1)

        fx, fy = col - c0, row - r0

        # Bilinear interpolation
        z00 = self.elevation_map[r0, c0]
        z01 = self.elevation_map[r0, c1]
        z10 = self.elevation_map[r1, c0]
        z11 = self.elevation_map[r1, c1]

        z = (1.0 - fx) * (1.0 - fy) * z00 + fx * (1.0 - fy) * z01 + (1.0 - fx) * fy * z10 + fx * fy * z11
        return float(z)

    def get_forest_density_at(self, x_km: float, y_km: float) -> float:
        """Query forest vegetation density [0.0 - 1.0] at (x, y) km."""
        x_clamped = max(0.0, min(self.width_km, float(x_km)))
        y_clamped = max(0.0, min(self.height_km, float(y_km)))
        col = int((x_clamped / self.width_km) * (self.resolution - 1))
        row = int((y_clamped / self.height_km) * (self.resolution - 1))
        return float(self.forest_map[row, col])

    def to_lat_lon(self, x_km: float, y_km: float) -> Tuple[float, float]:
        """Convert local (x_km, y_km) to approximate geographic (lat, lon)."""
        # ~111 km per degree latitude, ~96 km per degree longitude at ~30 deg N
        lat = BASE_LATITUDE + (y_km / 111.0)
        lon = BASE_LONGITUDE + (x_km / (111.0 * math.cos(math.radians(BASE_LATITUDE))))
        return round(lat, 5), round(lon, 5)

    def check_line_of_sight(
        self,
        tx_pos: Tuple[float, float],  # (x_km, y_km)
        rx_pos: Tuple[float, float],  # (x_km, y_km)
        tx_mast_height_m: float = 12.0,
        rx_mast_height_m: float = 12.0,
        frequency_mhz: float = 866.0,  # LoRa 865-867 MHz band default
        samples: int = 150,
    ) -> LineOfSightResult:
        """
        Ray-march between two antenna points across the heightmap to determine:
        1. Direct optical line of sight (LOS).
        2. Maximum terrain penetration / minimum clearance.
        3. First Fresnel Zone radius and clearance ratio.
        """
        x1, y1 = float(tx_pos[0]), float(tx_pos[1])
        x2, y2 = float(rx_pos[0]), float(rx_pos[1])

        z1 = self.get_elevation_at(x1, y1) + tx_mast_height_m
        z2 = self.get_elevation_at(x2, y2) + rx_mast_height_m

        dx_m = (x2 - x1) * 1000.0
        dy_m = (y2 - y1) * 1000.0
        dz_m = z2 - z1
        distance_2d_m = math.sqrt(dx_m**2 + dy_m**2)
        distance_3d_m = math.sqrt(distance_2d_m**2 + dz_m**2)

        if distance_2d_m < 1.0:
            return LineOfSightResult(
                has_los=True,
                distance_3d_m=0.0,
                distance_2d_m=0.0,
                tx_elevation_m=z1,
                rx_elevation_m=z2,
                min_clearance_m=tx_mast_height_m,
                max_obstruction_m=0.0,
                obstruction_point_km=None,
                first_fresnel_radius_m=0.0,
                fresnel_clearance_ratio=1.0,
                terrain_samples_count=1,
            )

        wavelength_m = 300.0 / frequency_mhz  # c / f in MHz
        mid_fresnel_r = 0.5 * math.sqrt(wavelength_m * distance_3d_m)

        min_clearance_m = float("inf")
        max_obstruction_m = 0.0
        worst_obstruction_pt: Optional[Tuple[float, float, float]] = None

        t_values = np.linspace(0.02, 0.98, samples)
        for t in t_values:
            sx = x1 + t * (x2 - x1)
            sy = y1 + t * (y2 - y1)
            ray_z = z1 + t * (z2 - z1)

            # Local terrain elevation
            ground_z = self.get_elevation_at(sx, sy)
            # Tree canopy clearance
            canopy_m = self.get_forest_density_at(sx, sy) * 12.0  # up to 12m forest canopy
            effective_obstacle_z = ground_z + canopy_m

            clearance = ray_z - effective_obstacle_z
            if clearance < min_clearance_m:
                min_clearance_m = clearance

            if effective_obstacle_z > ray_z:
                obstruction = effective_obstacle_z - ray_z
                if obstruction > max_obstruction_m:
                    max_obstruction_m = obstruction
                    worst_obstruction_pt = (round(sx, 2), round(sy, 2), round(effective_obstacle_z, 1))

        has_los = bool(max_obstruction_m == 0.0)
        fresnel_ratio = float(min_clearance_m / max(0.1, mid_fresnel_r)) if mid_fresnel_r > 0 else 1.0

        return LineOfSightResult(
            has_los=has_los,
            distance_3d_m=round(float(distance_3d_m), 1),
            distance_2d_m=round(float(distance_2d_m), 1),
            tx_elevation_m=round(float(z1), 1),
            rx_elevation_m=round(float(z2), 1),
            min_clearance_m=round(float(min_clearance_m), 1),
            max_obstruction_m=round(float(max_obstruction_m), 1),
            obstruction_point_km=worst_obstruction_pt,
            first_fresnel_radius_m=round(float(mid_fresnel_r), 1),
            fresnel_clearance_ratio=round(float(fresnel_ratio), 2),
            terrain_samples_count=samples,
        )

    def export_subsampled_grid(self, step: int = 4) -> Dict[str, Any]:
        """
        Export subsampled elevation matrix and metadata for Three.js 3D mesh rendering.
        A step of 4 turns 256x256 into a lightweight 64x64 grid (4,096 vertices)
        which renders at 60 FPS on any browser without lag.
        """
        sub = self.elevation_map[::step, ::step]
        nrows, ncols = sub.shape

        features_data = [
            {
                "id": f.id,
                "name": f.name,
                "type": f.feature_type,
                "coords": f.coordinates,
                "elevation": f.elevation_m,
                "desc": f.description,
            }
            for f in self.features
        ]

        return {
            "width_km": self.width_km,
            "height_km": self.height_km,
            "min_elevation_m": round(float(self.elevation_map.min()), 1),
            "max_elevation_m": round(float(self.elevation_map.max()), 1),
            "rows": nrows,
            "cols": ncols,
            "heightmap": sub.round(1).tolist(),
            "features": features_data,
            "anchor_lat": BASE_LATITUDE,
            "anchor_lon": BASE_LONGITUDE,
            "seed": self.seed,
        }
