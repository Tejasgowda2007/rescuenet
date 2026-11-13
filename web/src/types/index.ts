export interface TerrainData {
  width_km: number;
  height_km: number;
  min_elevation_m: number;
  max_elevation_m: number;
  rows: number;
  cols: number;
  heightmap: number[][];
  features: {
    id: string;
    name: string;
    type: string;
    coords: [number, number][];
    elevation: number;
    desc: string;
  }[];
  anchor_lat: number;
  anchor_lon: number;
  seed: number;
}

export interface StationData {
  id: string;
  name: string;
  role: string;
  coords: [number, number];
  elevation_m: number;
  lat: number;
  lon: number;
  antenna_mast_m: number;
  status: 'ONLINE' | 'DEGRADED' | 'POWER_DEPLETED' | 'DESTROYED' | string;
  is_relay_only: boolean;
  has_p2p: boolean;
  battery_pct: number;
  battery_wh: number;
  events_count: number;
  version_vector: Record<string, number>;
  tx_packets: number;
  rx_packets: number;
  dropped_packets: number;
  bytes_sent: number;
  bytes_received: number;
  queue_depth: number;
  last_seen: number;
}

export interface LinkData {
  node_a: string;
  node_b: string;
  is_connected: boolean;
  is_manually_cut: boolean;
  status: 'ACTIVE' | 'DEGRADED' | 'BLOCKED' | 'CUT' | string;
  distance_km: number;
  has_los: boolean;
  margin_db: number;
  rx_power_dbm: number;
  snr_db: number;
  per: number;
  throughput_bps: number;
  latency_ms: number;
  frequency_mhz: number;
  free_space_loss_db: number;
  terrain_diffraction_loss_db: number;
}

export interface PacketRecord {
  packet_id: string;
  original_id: string;
  source: string;
  destination: string;
  hop_src: string;
  hop_dst: string;
  msg_type: string;
  priority: number;
  bytes: number;
  start: number;
  end: number;
  latency_ms: number;
  delivered: boolean;
  reason?: string;
  route?: string[];
}

export interface LiveMetrics {
  disclaimer: string;
  stations: {
    total: number;
    online: number;
    degraded: number;
    power_depleted: number;
    destroyed: number;
    availability_pct: number;
  };
  network: {
    active_links: number;
    is_partitioned: boolean;
    connected_islands: number;
    islands: string[][];
    packets_sent: number;
    packets_delivered: number;
    packets_dropped: number;
    delivery_ratio_pct: number;
    total_wire_bytes: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
    effective_throughput_bps: number;
    queue_depth_total: number;
  };
  application: {
    total_unique_events: number;
    conflicts_detected: number;
  };
  invariants: {
    state_convergence_match: boolean;
    zero_lost_updates_safe: boolean;
    boat_active_allocations: number;
    boat_double_alloc_detected: boolean;
    escrow_sum_conserved: boolean;
  };
}

export interface ScenarioPreset {
  id: string;
  name: string;
  hazard_type: string;
  severity: string;
  description: string;
  rain_mm_h: number;
  cut_links: [string, string][];
  destroyed_stations: string[];
}

export interface EventRecord {
  event_id: string;
  node_id: string;
  counter: number;
  timestamp: number;
  entity_type: string;
  entity_id: string;
  operation: string;
  payload: Record<string, any>;
  signature?: string;
}
