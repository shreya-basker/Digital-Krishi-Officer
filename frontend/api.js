// Shared helpers for talking to the Agrisathi backend (served from the same origin).
const Api = {
  base: "/api",

  token() { return localStorage.getItem("agrisathiToken"); },
  user() { try { return JSON.parse(localStorage.getItem("agrisathiUser")) || null; } catch { return null; } },
  farmId() { return localStorage.getItem("agrisathiFarmId"); },

  saveSession(data) {
    localStorage.setItem("agrisathiToken", data.access_token);
    localStorage.setItem("agrisathiUser", JSON.stringify(data.user));
  },

  logout() {
    ["agrisathiToken", "agrisathiUser", "agrisathiFarmId"].forEach(k => localStorage.removeItem(k));
    location.href = "index.html";
  },

  // Redirects to login when there is no session.
  requireAuth() {
    if (!this.token()) { location.href = "index.html"; return false; }
    return true;
  },

  async request(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (this.token()) headers.Authorization = `Bearer ${this.token()}`;
    const resp = await fetch(this.base + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    if (resp.status === 401 && this.token()) { this.logout(); throw new Error("Session expired"); }
    const data = resp.headers.get("content-type")?.includes("json") ? await resp.json() : null;
    if (!resp.ok) {
      const detail = data?.detail;
      throw new Error(Array.isArray(detail) ? detail.map(d => d.msg).join(", ") : detail || `Request failed (${resp.status})`);
    }
    return data;
  },
  get(path) { return this.request(path); },
  post(path, body) { return this.request(path, { method: "POST", body }); },
  put(path, body) { return this.request(path, { method: "PUT", body }); },

  // Picks the remembered farm, falling back to the first one; null if the farmer has none.
  async currentFarm() {
    const farms = await this.get("/farms");
    if (!farms.length) return null;
    const farm = farms.find(f => String(f.id) === this.farmId()) || farms[0];
    localStorage.setItem("agrisathiFarmId", farm.id);
    return farm;
  },
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
  "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu & Kashmir", "Ladakh", "Puducherry",
];
