import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { TerrainData, StationData, LinkData } from '../../types';
import {
  Layers,
  Radio,
  Mountain,
  Battery,
  ShieldCheck,
  Compass,
  ArrowRight,
  Maximize2,
  Minimize2,
  X,
  Zap,
  Activity,
  Cpu,
  RefreshCw,
  Sun,
  AlertTriangle,
} from 'lucide-react';

interface Terrain3DViewProps {
  terrain: TerrainData | null;
  stations: Record<string, StationData>;
  links: LinkData[];
  onSelectStation?: (stationId: string) => void;
  selectedStationId?: string | null;
}

export const Terrain3DView: React.FC<Terrain3DViewProps> = ({
  terrain,
  stations,
  links,
  onSelectStation,
  selectedStationId,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [wireframe, setWireframe] = useState(false);
  const [showLinks, setShowLinks] = useState(true);
  const [showContour, setShowContour] = useState(true);
  const [hoveredStation, setHoveredStation] = useState<StationData | null>(null);
  const [focusedStationId, setFocusedStationId] = useState<string | null>(selectedStationId || 'alpha');

  // Three.js internal references
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (selectedStationId) {
      setFocusedStationId(selectedStationId);
    }
  }, [selectedStationId]);

  useEffect(() => {
    if (!mountRef.current || !terrain) return;

    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight || 580;

    // 1. Scene & Realistic Aerial Atmosphere
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    const skyColor = 0xdce4ec; // Clean daylight aerial haze
    scene.background = new THREE.Color(skyColor);
    scene.fog = new THREE.FogExp2(skyColor, 0.008);

    // 2. Camera Setup
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 350);
    camera.up.set(0, 0, 1);
    cameraRef.current = camera;

    // Camera Spherical coordinate state
    const spherical = {
      radius: 46,
      theta: Math.PI / 4,
      phi: Math.PI / 3.3,
      target: new THREE.Vector3(0, 0, 1.8),
    };

    function syncCamera() {
      camera.position.x = spherical.target.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.position.y = spherical.target.y - spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.position.z = Math.max(3.5, spherical.target.z + spherical.radius * Math.cos(spherical.phi));
      camera.lookAt(spherical.target);
    }
    syncCamera();

    // 3. Renderer with soft shadows
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;

    mountRef.current.innerHTML = '';
    mountRef.current.appendChild(renderer.domElement);

    // 4. Natural Directional Sun Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfffdfa, 1.25);
    sunLight.position.set(-25, -35, 45);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 1024;
    sunLight.shadow.mapSize.height = 1024;
    scene.add(sunLight);

    const skyFill = new THREE.DirectionalLight(0xb0c4de, 0.35);
    skyFill.position.set(30, 30, 20);
    scene.add(skyFill);

    // 5. Realistic Topographic Surface Colormap
    const rows = terrain.rows;
    const cols = terrain.cols;
    const geom = new THREE.PlaneGeometry(48, 48, cols - 1, rows - 1);
    const posAttr = geom.attributes.position;
    const vertexCount = posAttr.count;

    const colors = new Float32Array(vertexCount * 3);
    const minElev = terrain.min_elevation_m;
    const maxElev = terrain.max_elevation_m;

    for (let i = 0; i < vertexCount; i++) {
      const r = Math.floor(i / cols);
      const c = i % cols;
      const elev = terrain.heightmap[r]?.[c] ?? minElev;
      const zNorm = (elev - minElev) / (maxElev - minElev);
      const zVal = zNorm * 6.6;
      posAttr.setZ(i, zVal);

      // Natural geographic colormap
      const color = new THREE.Color();
      if (zNorm < 0.18) {
        // Bhagirathi River Gorge & lower valley
        color.setRGB(0.24, 0.44, 0.28);
      } else if (zNorm < 0.45) {
        // Forested slopes
        color.setRGB(0.18, 0.36, 0.22);
      } else if (zNorm < 0.72) {
        // Alpine shale & rocky slope
        color.setRGB(0.42, 0.40, 0.36);
      } else if (zNorm < 0.88) {
        // Trishul Granite barrier ridge
        color.setRGB(0.35, 0.38, 0.44);
      } else {
        // High summit snow / glaciers
        color.setRGB(0.88, 0.90, 0.94);
      }

      // Contour stripe incision every 200m
      if (showContour) {
        const contourStep = (elev % 200.0) / 200.0;
        if (contourStep < 0.08) {
          color.multiplyScalar(0.78);
        }
      }

      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }

    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geom.computeVertexNormals();

    const terrainMat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.88,
      metalness: 0.08,
      wireframe: wireframe,
    });

    const terrainMesh = new THREE.Mesh(geom, terrainMat);
    terrainMesh.receiveShadow = true;
    scene.add(terrainMesh);

    // Coordinate mapping helper from (x_km, y_km) to 3D world
    function mapCoordsTo3D(x_km: number, y_km: number): THREE.Vector3 {
      const sx = ((x_km / 50.0) - 0.5) * 48.0;
      const sy = (((50.0 - y_km) / 50.0) - 0.5) * 48.0;
      const c = Math.max(0, Math.min(cols - 1, Math.round((x_km / 50.0) * (cols - 1))));
      const r = Math.max(0, Math.min(rows - 1, Math.round((y_km / 50.0) * (rows - 1))));
      const h = terrain?.heightmap[r]?.[c] ?? minElev;
      const sz = ((h - minElev) / (maxElev - minElev)) * 6.6;
      return new THREE.Vector3(sx, sy, sz);
    }

    // 6. Station Towers, Mast Geometry, and Clean Status Beacons
    const stationGroup = new THREE.Group();
    const stationMeshes: THREE.Mesh[] = [];

    Object.values(stations).forEach((stn) => {
      const pos = mapCoordsTo3D(stn.coords[0], stn.coords[1]);
      const mastHeight = (stn.antenna_mast_m / 1000.0) * (48.0 / 50.0) * 14.0 + 1.0;

      // Realistic Galvanized Steel Tower Mast
      const towerGeom = new THREE.CylinderGeometry(0.12, 0.28, mastHeight, 8);
      const towerMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8, roughness: 0.3 });
      const tower = new THREE.Mesh(towerGeom, towerMat);
      tower.position.set(pos.x, pos.y, pos.z + mastHeight / 2);
      tower.rotation.x = Math.PI / 2;
      tower.castShadow = true;

      // Operational Status Beacon Sphere
      let beaconColor = 0x166534; // Online (Forest Green)
      if (stn.status === 'DEGRADED') beaconColor = 0xb45309;
      if (stn.status === 'POWER_DEPLETED' || stn.status === 'DESTROYED') beaconColor = 0xb91c1c;

      const beaconGeom = new THREE.SphereGeometry(0.38, 16, 16);
      const beaconMat = new THREE.MeshStandardMaterial({ color: beaconColor, roughness: 0.2 });
      const beacon = new THREE.Mesh(beaconGeom, beaconMat);
      beacon.position.set(pos.x, pos.y, pos.z + mastHeight + 0.2);
      beacon.userData = { stationId: stn.id };
      stationMeshes.push(beacon);

      // Station Base Pad
      const padGeom = new THREE.CylinderGeometry(0.8, 0.9, 0.15, 16);
      const padMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.9 });
      const pad = new THREE.Mesh(padGeom, padMat);
      pad.position.set(pos.x, pos.y, pos.z + 0.08);
      pad.rotation.x = Math.PI / 2;

      const stnContainer = new THREE.Group();
      stnContainer.add(tower);
      stnContainer.add(beacon);
      stnContainer.add(pad);
      stnContainer.name = stn.id;
      stnContainer.userData = { stationId: stn.id };

      stationGroup.add(stnContainer);
    });
    scene.add(stationGroup);

    // 7. Radio Link Communication Arcs
    const linkGroup = new THREE.Group();
    const packetBeams: { curve: THREE.QuadraticBezierCurve3; particle: THREE.Mesh; speed: number; progress: number }[] = [];

    if (showLinks) {
      links.forEach((link, lIdx) => {
        const s1 = stations[link.node_a];
        const s2 = stations[link.node_b];
        if (!s1 || !s2) return;

        const p1 = mapCoordsTo3D(s1.coords[0], s1.coords[1]);
        p1.z += 1.4;
        const p2 = mapCoordsTo3D(s2.coords[0], s2.coords[1]);
        p2.z += 1.4;

        let lineColor = 0x166534; // Forest Green (Healthy LoRa link)
        if (link.status === 'DEGRADED') lineColor = 0xb45309;
        if (link.status === 'BLOCKED' || link.status === 'CUT' || link.is_manually_cut) lineColor = 0xdc2626;

        if (link.is_connected && !link.is_manually_cut && link.status !== 'BLOCKED') {
          const midPoint = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
          midPoint.z += 0.85; // Clean parabolic propagation arc
          const curve = new THREE.QuadraticBezierCurve3(p1, midPoint, p2);
          const points = curve.getPoints(24);
          const lineGeom = new THREE.BufferGeometry().setFromPoints(points);
          const lineMat = new THREE.LineBasicMaterial({
            color: lineColor,
            linewidth: 2,
            transparent: true,
            opacity: 0.9,
          });
          const line = new THREE.Line(lineGeom, lineMat);
          linkGroup.add(line);

          // Flowing data packet indicator sphere
          const packetGeom = new THREE.SphereGeometry(0.18, 8, 8);
          const packetMat = new THREE.MeshBasicMaterial({ color: 0x0f172a });
          const packetMesh = new THREE.Mesh(packetGeom, packetMat);
          linkGroup.add(packetMesh);

          packetBeams.push({
            curve,
            particle: packetMesh,
            speed: 0.35 + (lIdx % 3) * 0.12,
            progress: (lIdx * 0.25) % 1.0,
          });
        } else {
          // Severed / blocked dashed red line
          const lineGeom = new THREE.BufferGeometry().setFromPoints([p1, p2]);
          const lineMat = new THREE.LineDashedMaterial({
            color: 0xdc2626,
            dashSize: 0.8,
            gapSize: 0.5,
            transparent: true,
            opacity: 0.7,
          });
          const line = new THREE.Line(lineGeom, lineMat);
          line.computeLineDistances();
          linkGroup.add(line);
        }
      });
    }
    scene.add(linkGroup);

    // 8. Trishul Ridge Summit Pin
    const pinGroup = new THREE.Group();
    const trishulPos = mapCoordsTo3D(24.0, 27.0);
    const pinGeom = new THREE.ConeGeometry(0.4, 1.4, 5);
    const pinMat = new THREE.MeshStandardMaterial({ color: 0x475569 });
    const trishulPin = new THREE.Mesh(pinGeom, pinMat);
    trishulPin.position.set(trishulPos.x, trishulPos.y, trishulPos.z + 1.2);
    trishulPin.rotation.x = Math.PI;
    pinGroup.add(trishulPin);
    scene.add(pinGroup);

    // 9. Interactive Raycasting (Hover & Click)
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const dom = renderer.domElement;
    let isDragging = false;
    let dragStart = { x: 0, y: 0 };
    let hasMovedSignificantly = false;

    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      hasMovedSignificantly = false;
      dragStart = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e: MouseEvent) => {
      const rect = dom.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (isDragging) {
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
          hasMovedSignificantly = true;
        }
        dragStart = { x: e.clientX, y: e.clientY };

        spherical.theta -= dx * 0.008;
        spherical.phi = Math.max(0.12, Math.min(Math.PI / 2.05, spherical.phi - dy * 0.008));
        syncCamera();
      } else {
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(stationMeshes, false);
        if (intersects.length > 0) {
          dom.style.cursor = 'pointer';
          const hitId = intersects[0].object.userData.stationId;
          if (hitId && stations[hitId]) {
            setHoveredStation(stations[hitId]);
          }
        } else {
          dom.style.cursor = 'grab';
          setHoveredStation(null);
        }
      }
    };

    const onMouseUp = (e: MouseEvent) => {
      if (!hasMovedSignificantly) {
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(stationMeshes, false);
        if (intersects.length > 0) {
          const clickedId = intersects[0].object.userData.stationId;
          if (clickedId) {
            setFocusedStationId(clickedId);
            onSelectStation?.(clickedId);
          }
        }
      }
      isDragging = false;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      spherical.radius = Math.max(8, Math.min(85, spherical.radius + e.deltaY * 0.04));
      syncCamera();
    };

    dom.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    dom.addEventListener('wheel', onWheel, { passive: false });

    // 10. Animation Loop
    const clock = new THREE.Clock();

    const animate = () => {
      animFrameRef.current = requestAnimationFrame(animate);
      const delta = clock.getDelta();

      // Flowing data packet pulses along link curves
      packetBeams.forEach((pb) => {
        pb.progress = (pb.progress + delta * pb.speed) % 1.0;
        const pt = pb.curve.getPoint(pb.progress);
        pb.particle.position.copy(pt);
      });

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight || 580;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      dom.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      dom.removeEventListener('wheel', onWheel);
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
      geom.dispose();
      terrainMat.dispose();
    };
  }, [terrain, stations, links, wireframe, showLinks, showContour]);

  const focusedStation = focusedStationId ? stations[focusedStationId] : null;

  return (
    <div className="relative w-full h-[580px] bg-[#DCE4EC] rounded border border-slate-300 overflow-hidden shadow-xs">
      {/* Three.js Canvas Container */}
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing select-none" />

      {/* Top Left Toolbar */}
      <div className="absolute top-3 left-3 flex flex-wrap items-center gap-2 z-20">
        <div className="bg-white px-3 py-1.5 rounded border border-slate-300 shadow-xs text-xs font-bold text-[#0F172A] flex items-center gap-2">
          <Mountain className="w-4 h-4 text-[#1B4332]" />
          <span>50 km &times; 50 km Mountain Digital Elevation Model</span>
          <span className="text-[11px] text-slate-500 font-mono font-normal">
            ({terrain?.min_elevation_m}m &ndash; {terrain?.max_elevation_m}m)
          </span>
        </div>

        <button
          onClick={() => setWireframe(!wireframe)}
          className={`px-2.5 py-1.5 rounded border text-xs font-semibold transition flex items-center gap-1.5 shadow-xs ${
            wireframe ? 'bg-[#1B4332] border-[#1B4332] text-white' : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>{wireframe ? 'Shaded Elevation' : 'Wireframe Mesh'}</span>
        </button>

        <button
          onClick={() => setShowLinks(!showLinks)}
          className={`px-2.5 py-1.5 rounded border text-xs font-semibold transition flex items-center gap-1.5 shadow-xs ${
            showLinks ? 'bg-[#1B4332] border-[#1B4332] text-white' : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>{showLinks ? 'LoRa Links ON' : 'LoRa Links OFF'}</span>
        </button>

        <button
          onClick={() => setShowContour(!showContour)}
          className={`px-2.5 py-1.5 rounded border text-xs font-semibold transition flex items-center gap-1.5 shadow-xs ${
            showContour ? 'bg-[#1B4332] border-[#1B4332] text-white' : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}
        >
          <Compass className="w-3.5 h-3.5" />
          <span>{showContour ? 'Contours (200m)' : 'No Contours'}</span>
        </button>
      </div>

      {/* Top Right Hover Indicator */}
      {hoveredStation && (
        <div className="absolute top-3 right-3 bg-white p-2.5 rounded border border-slate-300 shadow-md text-xs z-20 pointer-events-none">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${hoveredStation.status === 'ONLINE' ? 'bg-emerald-600' : 'bg-amber-500'}`} />
            <span className="font-bold text-[#0F172A]">{hoveredStation.name}</span>
          </div>
          <div className="text-[11px] text-slate-600 mt-0.5">
            Elev: <strong>{hoveredStation.elevation_m}m</strong> &bull; Bat: <strong>{hoveredStation.battery_pct}%</strong>
          </div>
        </div>
      )}

      {/* Floating Station HUD Card */}
      {focusedStation && (
        <div className="absolute bottom-14 right-3 w-80 bg-white border border-slate-300 rounded p-3.5 shadow-md z-20 space-y-2.5 text-xs">
          <div className="flex items-start justify-between gap-2 border-b border-slate-200 pb-2">
            <div>
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${focusedStation.status === 'ONLINE' ? 'bg-emerald-600' : 'bg-amber-500'}`} />
                <h4 className="font-bold text-sm text-[#0F172A]">{focusedStation.name}</h4>
              </div>
              <span className="text-[10px] font-mono text-slate-500 block mt-0.5">
                Node ID: {focusedStation.id.toUpperCase()} &bull; {focusedStation.role}
              </span>
            </div>
            <button
              onClick={() => setFocusedStationId(null)}
              className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-slate-50 p-2 rounded border border-slate-200">
              <span className="text-[10px] text-slate-500 font-semibold block">Elevation &amp; Mast</span>
              <span className="font-mono font-bold text-slate-900">{focusedStation.elevation_m} m</span>
              <span className="text-[10px] text-slate-600 block">Mast: {focusedStation.antenna_mast_m} m</span>
            </div>

            <div className="bg-slate-50 p-2 rounded border border-slate-200">
              <span className="text-[10px] text-slate-500 font-semibold block">Battery Runtime</span>
              <span className="font-mono font-bold text-slate-900">{focusedStation.battery_pct}%</span>
              <span className="text-[10px] text-slate-600 block">{focusedStation.battery_wh} Wh</span>
            </div>
          </div>

          <div className="bg-slate-50 p-2 rounded border border-slate-200 space-y-1 text-slate-700">
            <div className="flex justify-between">
              <span className="text-slate-500">Local SQLite Events:</span>
              <span className="font-mono font-bold text-slate-900">{focusedStation.events_count} immutable</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Node Type:</span>
              <span className="font-mono text-[10px] font-bold text-[#1B4332]">
                {focusedStation.id === 'alpha' ? 'PHYSICAL BASE' : 'SIMULATED LORA STUB'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">RF Transceiver:</span>
              <span className="font-mono text-[10px] font-bold text-slate-900">
                SX1276 LoRa &bull; 865–867 MHz
              </span>
            </div>
          </div>

          <button
            onClick={() => onSelectStation?.(focusedStation.id)}
            className="w-full py-1.5 px-3 rounded bg-[#1B4332] hover:bg-[#143827] text-white font-semibold text-xs flex items-center justify-center gap-1.5 transition shadow-xs"
          >
            <span>Inspect Station SQLite Store</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Bottom Bar: Station Selector Buttons */}
      <div className="absolute bottom-3 left-3 right-3 flex flex-wrap items-center justify-between gap-2 bg-white/95 px-3 py-2 rounded border border-slate-300 text-xs shadow-xs z-10">
        <div className="flex items-center gap-2 overflow-x-auto">
          <span className="text-slate-500 font-bold text-[11px] uppercase tracking-wider shrink-0">
            Select Station:
          </span>
          {Object.values(stations).map((stn) => {
            const isSelected = focusedStationId === stn.id;
            const isOnline = stn.status === 'ONLINE';

            return (
              <button
                key={stn.id}
                onClick={() => {
                  setFocusedStationId(stn.id);
                  onSelectStation?.(stn.id);
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition shrink-0 ${
                  isSelected
                    ? 'bg-[#1B4332] text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-200'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <span>{stn.name.split(' ')[0]}</span>
                <span className="text-[10px] text-slate-400 font-mono font-normal">{stn.elevation_m}m</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3 text-[11px] text-slate-600 shrink-0">
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-1 bg-[#166534] rounded" />
            <span>LoRa Link</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-1 border-t border-dashed border-red-600" />
            <span>Ridge Cut</span>
          </div>
        </div>
      </div>
    </div>
  );
};
