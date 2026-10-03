// How the UI reaches the Python core. Three transports, picked at startup:
//   pywebview  window.pywebview.api.<method>(...)   (the real app)
//   http       POST /api/<method>                   (chisel.gui.devserver)
//   none       no core available -> the in-memory mock bridge (npm run dev)
// Every bridge call resolves to {ok: true, ...} or {ok: false, error}; it never throws.

export type BridgeResult<T = object> = ({ ok: true } & T) | { ok: false; error: string };
export type Transport = "pywebview" | "http" | "none";
export type Call = <T = object>(method: string, ...args: unknown[]) => Promise<BridgeResult<T>>;

interface PywebviewApi { [method: string]: (...args: unknown[]) => Promise<unknown> }
declare global { interface Window { pywebview?: { api: PywebviewApi } } }

let transport: Transport = "none";
export const getTransport = () => transport;

const pywebviewReady = () => new Promise<void>((resolve) => {
  if (window.pywebview?.api) return resolve();
  window.addEventListener("pywebviewready", () => resolve(), { once: true });
});

/** Detect the transport once; resolves quickly when there is no core. */
export async function initTransport(): Promise<Transport> {
  if (typeof window === "undefined") return (transport = "none");
  // pywebview injects its bridge shortly after load; wait briefly for it.
  if (window.pywebview?.api) return (transport = "pywebview");
  const pv = await Promise.race([
    pywebviewReady().then(() => true),
    new Promise<boolean>((r) => setTimeout(() => r(false), 400)),
  ]);
  if (pv) return (transport = "pywebview");
  try {
    const res = await fetch("api/ping", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (res.ok && (await res.json()).ok) return (transport = "http");
  } catch { /* no devserver */ }
  return (transport = "none");
}

export async function call<T = object>(method: string, ...args: unknown[]): Promise<BridgeResult<T>> {
  try {
    if (transport === "pywebview") return (await window.pywebview!.api[method](...args)) as BridgeResult<T>;
    if (transport === "http") {
      const res = await fetch(`api/${method}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ args }),
      });
      return (await res.json()) as BridgeResult<T>;
    }
    return (await import("./mock")).mockCall(method, args) as BridgeResult<T>;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}
