// A tiny Chrome DevTools Protocol client (Node's built-in WebSocket, no packages).
// Used by gui_capture.mjs to drive headless Chromium against the headless GUI backend.
import fs from "node:fs";

export async function connect(port) {
  let targets;
  for (let i = 0; i < 100; i++) {
    try {
      targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      if (targets.some((t) => t.type === "page")) break;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const waiting = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && waiting.has(msg.id)) {
      const { res, rej } = waiting.get(msg.id);
      waiting.delete(msg.id);
      msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const n = ++id;
    waiting.set(n, { res, rej });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const api = {
    send, sleep,
    async goto(url) { await send("Page.navigate", { url }); await sleep(1500); },
    async eval(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description ?? ""));
      return r.result.value;
    },
    async size(w, h, dsf = 1) {
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dsf, mobile: false });
    },
    async shot(path, clip) {
      const params = { format: "png" };
      if (clip) params.clip = { ...clip, scale: 1 };
      const r = await send("Page.captureScreenshot", params);
      fs.writeFileSync(path, Buffer.from(r.data, "base64"));
    },
    /** Centre of the first element matching a selector (optionally containing text). */
    async rect(sel, text) {
      return api.eval(`(() => {
        const els = [...document.querySelectorAll(${JSON.stringify(sel)})];
        const el = ${text ? `els.find((e) => e.textContent.includes(${JSON.stringify(text)}))` : "els[0]"};
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, w: r.width, h: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
      })()`);
    },
    async click(sel, text, opts = {}) {
      const r = await api.rect(sel, text);
      if (!r) throw new Error(`no element ${sel} ${text ?? ""}`);
      await api.clickAt(opts.x ?? r.cx, opts.y ?? r.cy, opts);
      return r;
    },
    async clickAt(x, y, opts = {}) {
      const mods = (opts.ctrl ? 2 : 0);
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: opts.button ?? "left", clickCount: opts.clicks ?? 1, modifiers: mods });
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: opts.button ?? "left", clickCount: opts.clicks ?? 1, modifiers: mods });
      await sleep(opts.wait ?? 250);
    },
    async hover(x, y) {
      for (let i = 0; i < 6; i++) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + i, y }); await sleep(120); }
      await sleep(1000);
    },
    async type(text) {
      for (const ch of text) {
        await send("Input.dispatchKeyEvent", { type: "keyDown", text: ch, key: ch });
        await send("Input.dispatchKeyEvent", { type: "keyUp", key: ch });
      }
      await sleep(150);
    },
    /** key: "F7", "Enter", "Escape", "ArrowDown", or a single character with modifiers {ctrl}. */
    async key(key, mods = {}) {
      const modifiers = (mods.alt ? 1 : 0) | (mods.ctrl ? 2 : 0) | (mods.shift ? 8 : 0);
      const codes = { F6: 117, F7: 118, F8: 119, F11: 122, Enter: 13, Escape: 27, ArrowDown: 40, ArrowUp: 38, ArrowLeft: 37, ArrowRight: 39, Tab: 9, Backspace: 8, Home: 36, End: 35, ".": 190 };
      const vk = codes[key] ?? key.toUpperCase().charCodeAt(0);
      const codeOf = (k) => (k === "." ? "Period" : k.length === 1 ? "Key" + k.toUpperCase() : k);
      const text = key.length === 1 && !mods.ctrl ? key : undefined;
      await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key, code: codeOf(key), windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
      if (text) await send("Input.dispatchKeyEvent", { type: "char", text, key, modifiers });
      await send("Input.dispatchKeyEvent", { type: "keyUp", key, code: codeOf(key), windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
      await sleep(mods.wait ?? 300);
    },
    close() { ws.close(); },
  };
  await send("Page.enable");
  await send("Runtime.enable");
  return api;
}
