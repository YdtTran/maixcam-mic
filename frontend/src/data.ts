import { demoVideo } from "./demo";

export type Worker = {
  id: string;
  number: string;
  name: string;
  device: string;
  mode: "real" | "demo";
  battery: number | null;
  signal: string;
  recording: boolean;
  startedAt?: string;
};
export type Recording = {
  id: string;
  worker: string;
  createdAt: string;
  duration: number;
  filename: string;
  url: string;
  active?: boolean;
  source: "real" | "demo";
};
export type Preferences = { whep: string; demoVideo: string };

export const defaults: Preferences = {
  whep: `${location.protocol}//${location.hostname}:8889/maix01/whep`,
  demoVideo,
};

// Generic entity store: no UI component depends on IndexedDB. A future HTTP
// repository can implement this interface against any server-side database.
export interface Repository {
  list<T>(collection: string): Promise<T[]>;
  get<T>(collection: string, id: string): Promise<T | undefined>;
  put<T>(collection: string, id: string, value: T): Promise<void>;
}
export class BrowserRepository implements Repository {
  private database = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("workercam-admin", 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("entities", { keyPath: "key" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  private async operation<T>(
    mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => IDBRequest,
  ): Promise<T> {
    const db = await this.database;
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("entities", mode);
      const request = action(transaction.objectStore("entities"));
      transaction.oncomplete = () => resolve(request.result as T);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () =>
        reject(transaction.error || new Error("Database transaction aborted"));
    });
  }
  async list<T>(collection: string) {
    const entries = await this.operation<{ key: string; value: T }[]>(
      "readonly",
      (store) => store.getAll(),
    );
    return entries
      .filter((entry) => entry.key.startsWith(`${collection}/`))
      .map((entry) => entry.value);
  }
  async get<T>(collection: string, id: string) {
    const entry = await this.operation<{ value: T } | undefined>(
      "readonly",
      (store) => store.get(`${collection}/${id}`),
    );
    return entry?.value;
  }
  async put<T>(collection: string, id: string, value: T) {
    await this.operation("readwrite", (store) =>
      store.put({ key: `${collection}/${id}`, value }),
    );
  }
}
export const repository: Repository = new BrowserRepository();
export async function initialize() {
  if (!(await repository.get("meta", "seeded"))) {
    const workers: Worker[] = [
      {
        id: "cam-007",
        number: "07",
        name: "Nguyen A",
        device: "MaixCAM 07",
        mode: "real",
        battery: null,
        signal: "Unknown",
        recording: false,
      },
      {
        id: "cam-012",
        number: "12",
        name: "Tran B",
        device: "MaixCAM 12",
        mode: "demo",
        battery: 64,
        signal: "Fair",
        recording: false,
      },
    ];
    for (const worker of workers)
      await repository.put("workers", worker.id, worker);
    await repository.put("preferences", "default", defaults);
    await repository.put("meta", "seeded", true);
  }
  return {
    workers: await repository.list<Worker>("workers"),
    preferences:
      (await repository.get<Preferences>("preferences", "default")) || defaults,
  };
}

// This is intentionally local demo authentication; it does not secure backend
// endpoints. Replace AuthService with server sessions when implementing the BE.
export const auth = {
  current: () => sessionStorage.getItem("workercam-session") === "admin",
  async login(username: string, password: string) {
    if (username !== "admin" || password !== "admin")
      throw new Error("Incorrect username or password.");
    sessionStorage.setItem("workercam-session", "admin");
  },
  logout() {
    sessionStorage.removeItem("workercam-session");
  },
};

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    signal: AbortSignal.timeout(25000),
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(
      "WorkerCam backend is unavailable. Check that the PC server is running.",
    );
  }
  if (!response.ok)
    throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload as T;
}
export type RealStatus = { recording: boolean; duration_seconds: number };
export type BluetoothStatus = { connected: boolean; selected: string | null; fixed?: boolean };
export type BluetoothDevice = { mac: string; name: string };
export async function listRecordings(): Promise<Recording[]> {
  const items =
    await api<
      {
        id: string;
        created_at: string;
        duration_seconds: number;
        url: string;
        active: boolean;
      }[]
    >("/api/recordings");
  return items.map((item) => ({
    id: item.id,
    worker: "Nguyen A",
    createdAt: item.created_at,
    duration: item.duration_seconds,
    url: item.url,
    filename: `${item.id}.mp4`,
    active: item.active,
    source: "real",
  }));
}
export const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
