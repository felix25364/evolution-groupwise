/* SPDX-License-Identifier: LGPL-2.1-or-later */
class GroupwiseTransport {
  constructor(runtime, timeout = 40000) {
    this.runtime = runtime; this.timeout = timeout; this.sequence = 0;
    this.pending = new Map(); this.port = null;
  }
  connect() {
    if (this.port) return;
    const port = this.runtime.connectNative("org.evolution_groupwise.host");
    this.port = port;
    port.onMessage.addListener(response => {
      const p = this.pending.get(response?.id);
      if (!p) return;
      clearTimeout(p.timer); this.pending.delete(response.id);
      if (response.ok) p.resolve(response.result);
      else p.reject(Object.assign(new Error(response.error?.message || "GroupWise failed"), {code:response.error?.code || "HOST_ERROR"}));
    });
    port.onDisconnect.addListener(() => { if (this.port === port) this.fail("HOST_DISCONNECTED"); });
  }
  fail(code) {
    this.port = null;
    for (const p of this.pending.values()) {
      clearTimeout(p.timer); p.reject(Object.assign(new Error(code), {code}));
    }
    this.pending.clear();
  }
  request(op, args = {}) {
    if (this.pending.size >= 64) return Promise.reject(new Error("TOO_MANY_REQUESTS"));
    if (new TextEncoder().encode(JSON.stringify(args)).length > 240000) return Promise.reject(new Error("REQUEST_TOO_LARGE"));
    this.connect();
    return new Promise((resolve, reject) => {
      const id = String(++this.sequence);
      const timer = setTimeout(() => { this.close("HOST_TIMEOUT"); }, this.timeout);
      this.pending.set(id, {resolve, reject, timer});
      try { this.port.postMessage({...args, op, id}); }
      catch (_) { this.close("HOST_UNAVAILABLE"); }
    });
  }
  close(code = "HOST_CLOSED") {
    const port = this.port; this.fail(code);
    if (port) port.disconnect();
  }
}
if (typeof module !== "undefined") module.exports = GroupwiseTransport;
