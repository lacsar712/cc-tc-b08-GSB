export function authHeaders() {
  try {
    const s = JSON.parse(localStorage.getItem("tunnel_session"));
    return s ? { Authorization: "Bearer " + s.token } : {};
  } catch {
    return {};
  }
}

export function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { hour12: false });
}

export const RULE_LABELS = {
  median_jump: "飞点跳变",
  window_dup: "窗内重复",
};
