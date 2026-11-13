/**
 * IndexedDB Offline Data Store & Mutation Outbox for RescueNet FieldMesh.
 * 
 * Provides defense-grade local persistence for emergency responders operating
 * with zero cellular or network connectivity:
 * 1. Object Stores: 'incidents', 'victims', 'alerts', 'stations', 'outbox'.
 * 2. Automatic Local Caching: Telemetry & queries fetched from the backend are mirrored locally.
 * 3. Store-and-Forward Outbox: Actions performed offline are queued locally in IndexedDB,
 *    persisted across browser reloads, and auto-synchronized when mesh connection is restored.
 */

export interface OfflineIncident {
  id: string;
  title: string;
  category: 'MEDEVAC' | 'COLLAPSE' | 'FIRE' | 'FLOOD' | 'HAZMAT' | 'SUPPLY_DEFICIT';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  status: 'OPEN' | 'ASSIGNED' | 'IN_PROGRESS' | 'RESOLVED';
  location: string;
  lat?: number;
  lon?: number;
  reported_by: string;
  created_at: number;
  synced: boolean;
}

export interface OfflineVictim {
  id: string;
  name: string;
  triage_color: 'RED' | 'YELLOW' | 'GREEN' | 'BLACK';
  status: 'TRAPPED' | 'IN_TRANSIT' | 'AT_TRIAGE' | 'HOSPITALIZED' | 'DISCHARGED';
  location: string;
  vitals?: string;
  updated_at: number;
  synced: boolean;
}

export interface OfflineAlert {
  id: string;
  message: string;
  urgency: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'INFO';
  source_id: string;
  timestamp: number;
  acknowledged: boolean;
}

export interface OutboxMutation {
  id: string;
  url: string;
  method: string;
  body: any;
  headers?: Record<string, string>;
  timestamp: number;
  status: 'PENDING' | 'SYNCING' | 'FAILED';
  retryCount: number;
  error?: string;
}

const DB_NAME = 'RescueNet_FieldMesh_DB';
const DB_VERSION = 1;

class OfflineStorageManager {
  private dbPromise: Promise<IDBDatabase> | null = null;
  private listeners: Set<(pendingCount: number) => void> = new Set();

  constructor() {
    if (typeof window !== 'undefined' && 'indexedDB' in window) {
      this.initDB();
    }
  }

  private initDB(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;

    this.dbPromise = new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) {
        reject(new Error('IndexedDB not supported in this environment'));
        return;
      }

      const request = window.indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = (event: IDBVersionChangeEvent) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Incidents store
        if (!db.objectStoreNames.contains('incidents')) {
          const store = db.createObjectStore('incidents', { keyPath: 'id' });
          store.createIndex('severity', 'severity', { unique: false });
          store.createIndex('status', 'status', { unique: false });
          store.createIndex('created_at', 'created_at', { unique: false });
        }

        // Victims triage store
        if (!db.objectStoreNames.contains('victims')) {
          const store = db.createObjectStore('victims', { keyPath: 'id' });
          store.createIndex('triage_color', 'triage_color', { unique: false });
          store.createIndex('status', 'status', { unique: false });
        }

        // Emergency alerts store
        if (!db.objectStoreNames.contains('alerts')) {
          const store = db.createObjectStore('alerts', { keyPath: 'id' });
          store.createIndex('urgency', 'urgency', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }

        // Stations cache store
        if (!db.objectStoreNames.contains('stations')) {
          db.createObjectStore('stations', { keyPath: 'id' });
        }

        // Outbox mutation store for offline store-and-forward sync
        if (!db.objectStoreNames.contains('outbox')) {
          const store = db.createObjectStore('outbox', { keyPath: 'id' });
          store.createIndex('status', 'status', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };

      request.onsuccess = () => {
        resolve(request.result);
        this.notifyListeners();
      };

      request.onerror = () => {
        console.error('[IndexedDB] Failed to open database:', request.error);
        reject(request.error);
      };
    });

    return this.dbPromise;
  }

  // ----------------------------------------------------------------
  // Generic Store Helpers
  // ----------------------------------------------------------------

  async getAll<T>(storeName: string): Promise<T[]> {
    try {
      const db = await this.initDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const req = store.getAll();
        req.onsuccess = () => resolve((req.result || []) as T[]);
        req.onerror = () => reject(req.error);
      });
    } catch {
      return [];
    }
  }

  async put<T>(storeName: string, item: T): Promise<void> {
    try {
      const db = await this.initDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const req = store.put(item);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch (e) {
      console.warn(`[IndexedDB] Error putting to ${storeName}:`, e);
    }
  }

  async putBatch<T>(storeName: string, items: T[]): Promise<void> {
    if (!items || items.length === 0) return;
    try {
      const db = await this.initDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        items.forEach((item) => store.put(item));
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    } catch (e) {
      console.warn(`[IndexedDB] Error batch putting to ${storeName}:`, e);
    }
  }

  async delete(storeName: string, key: IDBValidKey): Promise<void> {
    try {
      const db = await this.initDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const req = store.delete(key);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch (e) {
      console.warn(`[IndexedDB] Error deleting from ${storeName}:`, e);
    }
  }

  // ----------------------------------------------------------------
  // Incidents Store Operations
  // ----------------------------------------------------------------

  async saveIncidents(incidents: OfflineIncident[]): Promise<void> {
    await this.putBatch('incidents', incidents);
  }

  async addLocalIncident(incident: Omit<OfflineIncident, 'id' | 'created_at' | 'synced'>): Promise<OfflineIncident> {
    const fullIncident: OfflineIncident = {
      ...incident,
      id: `inc-local-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      created_at: Date.now(),
      synced: false,
    };
    await this.put('incidents', fullIncident);

    // Queue in Outbox
    await this.queueOutboxAction('/api/actions/incident', 'POST', fullIncident);
    return fullIncident;
  }

  async getIncidents(): Promise<OfflineIncident[]> {
    return this.getAll<OfflineIncident>('incidents');
  }

  // ----------------------------------------------------------------
  // Victims Store Operations
  // ----------------------------------------------------------------

  async saveVictims(victims: OfflineVictim[]): Promise<void> {
    await this.putBatch('victims', victims);
  }

  async addLocalVictim(victim: Omit<OfflineVictim, 'id' | 'updated_at' | 'synced'>): Promise<OfflineVictim> {
    const fullVictim: OfflineVictim = {
      ...victim,
      id: `vic-local-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      updated_at: Date.now(),
      synced: false,
    };
    await this.put('victims', fullVictim);

    // Queue in Outbox
    await this.queueOutboxAction('/api/actions/victim', 'POST', fullVictim);
    return fullVictim;
  }

  async getVictims(): Promise<OfflineVictim[]> {
    return this.getAll<OfflineVictim>('victims');
  }

  // ----------------------------------------------------------------
  // Alerts & SOS Store Operations
  // ----------------------------------------------------------------

  async saveAlerts(alerts: OfflineAlert[]): Promise<void> {
    await this.putBatch('alerts', alerts);
  }

  async addLocalSOSAlert(sourceId: string, message: string): Promise<OfflineAlert> {
    const alert: OfflineAlert = {
      id: `sos-${Date.now()}-${sourceId}`,
      message,
      urgency: 'CRITICAL',
      source_id: sourceId,
      timestamp: Date.now(),
      acknowledged: false,
    };
    await this.put('alerts', alert);

    // Queue in outbox
    await this.queueOutboxAction('/api/actions/sos', 'POST', {
      source_id: sourceId,
      message,
      urgency: 'CRITICAL',
    });
    return alert;
  }

  async getAlerts(): Promise<OfflineAlert[]> {
    return this.getAll<OfflineAlert>('alerts');
  }

  // ----------------------------------------------------------------
  // Outbox Store-and-Forward Mutation Queue
  // ----------------------------------------------------------------

  async queueOutboxAction(url: string, method: string, body: any, headers?: Record<string, string>): Promise<string> {
    const mutationId = `mut-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const mutation: OutboxMutation = {
      id: mutationId,
      url,
      method: method.toUpperCase(),
      body,
      headers,
      timestamp: Date.now(),
      status: 'PENDING',
      retryCount: 0,
    };
    await this.put('outbox', mutation);
    await this.notifyListeners();
    console.log(`[IndexedDB Outbox] Queued offline mutation [${method} ${url}]:`, mutationId);
    return mutationId;
  }

  async getPendingMutations(): Promise<OutboxMutation[]> {
    const all = await this.getAll<OutboxMutation>('outbox');
    return all.filter((m) => m.status === 'PENDING' || m.status === 'FAILED');
  }

  async getPendingCount(): Promise<number> {
    const pending = await this.getPendingMutations();
    return pending.length;
  }

  async flushOutbox(
    apiFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  ): Promise<{ synced: number; failed: number }> {
    const pending = await this.getPendingMutations();
    if (pending.length === 0) {
      return { synced: 0, failed: 0 };
    }

    console.log(`[IndexedDB Outbox] Synchronizing ${pending.length} pending offline mutations to mesh...`);
    let synced = 0;
    let failed = 0;

    for (const mutation of pending) {
      try {
        mutation.status = 'SYNCING';
        await this.put('outbox', mutation);

        const res = await apiFetch(mutation.url, {
          method: mutation.method,
          headers: {
            'Content-Type': 'application/json',
            ...(mutation.headers || {}),
          },
          body: mutation.body ? JSON.stringify(mutation.body) : undefined,
        });

        if (res.ok) {
          await this.delete('outbox', mutation.id);
          synced++;
        } else {
          mutation.status = 'FAILED';
          mutation.retryCount += 1;
          mutation.error = `HTTP ${res.status}: ${res.statusText}`;
          await this.put('outbox', mutation);
          failed++;
        }
      } catch (err: any) {
        mutation.status = 'FAILED';
        mutation.retryCount += 1;
        mutation.error = err?.message || 'Network unreachable';
        await this.put('outbox', mutation);
        failed++;
      }
    }

    await this.notifyListeners();
    console.log(`[IndexedDB Outbox] Sync complete: ${synced} synced, ${failed} failed.`);
    return { synced, failed };
  }

  // ----------------------------------------------------------------
  // Subscriptions & Change Notifications
  // ----------------------------------------------------------------

  subscribe(callback: (pendingCount: number) => void): () => void {
    this.listeners.add(callback);
    this.getPendingCount().then(callback);
    return () => this.listeners.delete(callback);
  }

  private async notifyListeners() {
    try {
      const count = await this.getPendingCount();
      this.listeners.forEach((cb) => {
        try {
          cb(count);
        } catch {}
      });
    } catch {}
  }
}

export const offlineStorage = new OfflineStorageManager();
