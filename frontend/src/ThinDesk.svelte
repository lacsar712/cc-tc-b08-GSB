<script>
  import { onDestroy } from "svelte";

  export let session;

  let cfg = null;
  let rejects = [];
  let winInput = "5";
  let thrInput = "2.0";
  let error = "";
  let saving = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: latest = rejects[0] ?? null;

  function authHeaders(extra = {}) {
    return { Authorization: "Bearer " + session.token, ...extra };
  }

  async function refresh() {
    try {
      const [cRes, rRes] = await Promise.all([
        fetch("/api/thin/config", { headers: authHeaders() }),
        fetch("/api/thin/rejects", { headers: authHeaders() }),
      ]);
      if (cRes.ok) {
        const next = await cRes.json();
        const firstLoad = cfg === null;
        cfg = next;
        // 不在用户正在编辑时用轮询值覆盖输入框
        if (firstLoad || document.activeElement?.dataset.field !== "win") {
          winInput = String(next.window_size);
        }
        if (firstLoad || document.activeElement?.dataset.field !== "thr") {
          thrInput = String(next.threshold_mm);
        }
      }
      if (rRes.ok) rejects = await rRes.json();
    } catch {
      /* 轮询失败下一轮自然恢复 */
    }
  }

  async function saveConfig(patch, msg) {
    error = "";
    saving = true;
    try {
      const res = await fetch("/api/thin/config", {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || msg + "失败";
        return;
      }
      cfg = data;
      winInput = String(data.window_size);
      thrInput = String(data.threshold_mm);
      await refresh();
    } catch {
      error = msg + "时网络异常";
    } finally {
      saving = false;
    }
  }

  function toggle() {
    if (!cfg) return;
    saveConfig({ enabled: !cfg.enabled }, cfg.enabled ? "停用" : "启用");
  }

  function saveWindow() {
    saveConfig({ window_size: Number(winInput), threshold_mm: Number(thrInput) }, "保存取样窗");
  }

  function fmt(ts) {
    return ts ? new Date(ts).toLocaleString("zh-CN", { hour12: false }) : "—";
  }

  refresh();
  timer = setInterval(refresh, 2000);
  onDestroy(() => clearInterval(timer));
</script>

<style>
  .grid {
    display: grid;
    grid-template-columns: 300px 1fr 1.2fr;
    gap: 1rem;
    align-items: start;
  }
  @media (max-width: 980px) {
    .grid { grid-template-columns: 1fr; }
  }
  .panel {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.1rem;
  }
  .panel h2 { margin: 0 0 0.75rem; font-size: 1rem; color: #fbbf24; }
  .lamp-row { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; }
  .lamp { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
  .lamp.on { background: #f87171; box-shadow: 0 0 10px #f87171; }
  .lamp.off { background: #57534e; }
  .lamp-text { font-weight: 600; }
  .lamp-text.on { color: #fca5a5; }
  .lamp-text.off { color: #a8a29e; }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin: 0.6rem 0 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9;
  }
  input:disabled { opacity: 0.55; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    font-weight: 600; width: 100%; margin-top: 0.8rem;
  }
  button.go { background: #b91c1c; color: #fff; }
  button.stop { background: #15803d; color: #fff; }
  button.save { background: #d97706; color: #fff; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .hint { color: #a8a29e; font-size: 0.78rem; line-height: 1.5; margin-top: 0.6rem; }
  .meta { color: #78716c; font-size: 0.75rem; margin-top: 0.8rem; }
  .err { color: #fb7185; font-size: 0.85rem; margin-top: 0.6rem; }
  .card {
    border: 1px solid #7f1d1d; background: #450a0a; border-radius: 8px; padding: 0.9rem 1rem;
  }
  .card .chain { font-size: 1.15rem; font-weight: 700; color: #fca5a5; }
  .kv { display: grid; grid-template-columns: auto 1fr; gap: 0.3rem 0.8rem; font-size: 0.85rem; margin-top: 0.6rem; }
  .kv .k { color: #a8a29e; }
  .empty { color: #78716c; font-size: 0.85rem; padding: 1.5rem 0; text-align: center; }
  .ledger { max-height: 520px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th, td { text-align: left; padding: 0.4rem 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  th { color: #a8a29e; font-weight: 600; position: sticky; top: 0; background: #292524; }
  .tag { padding: 0.05rem 0.35rem; border-radius: 4px; font-size: 0.75rem; background: #7f1d1d; color: #fca5a5; }
</style>

<div class="grid">
  <!-- 左列：开关与取样窗 -->
  <div class="panel">
    <h2>抽稀台开关</h2>
    {#if cfg}
      <div class="lamp-row">
        <span class="lamp {cfg.enabled ? 'on' : 'off'}"></span>
        <span class="lamp-text {cfg.enabled ? 'on' : 'off'}">
          {cfg.enabled ? "运行中 · 飞点整份退回" : "已停用 · 不再拦新点"}
        </span>
      </div>
      {#if isWriter}
        <button class={cfg.enabled ? "stop" : "go"}
                disabled={saving} on:click={toggle}>
          {cfg.enabled ? "关停抽稀" : "开启抽稀"}
        </button>
      {:else}
        <div class="hint">巡检员账号只能查看灯号与履历，不能扳开关。</div>
      {/if}

      <label for="thin-win">取样窗长（同部位最近已准入笔数）</label>
      <input id="thin-win" type="number" min="2" max="50" step="1" data-field="win"
             bind:value={winInput} disabled={!isWriter || saving} />
      <label for="thin-thr">中位跳变阈值（mm，达到即退单）</label>
      <input id="thin-thr" type="number" min="0.1" max="100" step="0.1" data-field="thr"
             bind:value={thrInput} disabled={!isWriter || saving} />
      {#if isWriter}
        <button class="save" disabled={saving} on:click={saveWindow}>保存取样窗</button>
      {/if}
      <p class="hint">
        窗内取所有已准入读数的中位值；新读数相对中位偏离达到阈值即判飞点整份退回，
        交单口串行判定保证贴着门槛同时到的两笔至多进队一笔。窗内不足 2 笔时不拦。
        拱顶与边墙各自取窗。
      </p>
      <p class="meta">
        最近操作：{cfg.updated_by ?? "—"} · {fmt(cfg.updated_at)}
      </p>
      {#if error}<p class="err">{error}</p>{/if}
    {/if}
  </div>

  <!-- 中列：最新拒收样例 -->
  <div class="panel">
    <h2>最新拒收样例</h2>
    {#if latest}
      <div class="card">
        <div class="chain">{latest.chainage} · {latest.part}</div>
        <div class="kv">
          <span class="k">读数</span><span>{latest.delta_mm} mm</span>
          <span class="k">窗内中位</span>
          <span>{latest.median_mm !== null ? latest.median_mm.toFixed(2) + " mm" : "样本不足"}</span>
          <span class="k">跳变量</span>
          <span>{latest.deviation_mm !== null ? latest.deviation_mm.toFixed(2) + " mm" : "—"}</span>
          <span class="k">阈值</span><span>{latest.threshold_mm} mm（窗长 {latest.window_size}，实采 {latest.sample_count} 笔）</span>
          <span class="k">退回原因</span><span>{latest.reason}</span>
          <span class="k">提交人</span><span>{latest.created_by}</span>
          <span class="k">时间</span><span>{fmt(latest.created_at)}</span>
        </div>
      </div>
    {:else}
      <div class="empty">暂无拒收样例<br />（抽稀关闭期间或尚无飞点）</div>
    {/if}
    <p class="hint" style="margin-top:0.9rem;">
      飞点只落到拒收履历，不会进入待认领队列，也不会用任何补填值冒充合格读数。
    </p>
  </div>

  <!-- 右列：已拦住的履历（关停后仍可翻） -->
  <div class="panel">
    <h2>拦截履历（{rejects.length} 笔）</h2>
    <div class="ledger">
      {#if rejects.length}
        <table>
          <thead>
            <tr><th>时间</th><th>桩号</th><th>部位</th><th>读数</th><th>中位</th><th>跳变</th><th>阈值</th></tr>
          </thead>
          <tbody>
            {#each rejects as r}
              <tr>
                <td>{fmt(r.created_at)}</td>
                <td>{r.chainage}<div class="meta" style="margin:0;">{r.created_by}</div></td>
                <td><span class="tag">{r.part}</span></td>
                <td>{r.delta_mm}</td>
                <td>{r.median_mm !== null ? r.median_mm.toFixed(2) : "—"}</td>
                <td>{r.deviation_mm !== null ? r.deviation_mm.toFixed(2) : "—"}</td>
                <td>{r.threshold_mm}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <div class="empty">还没有拦住过飞点</div>
      {/if}
    </div>
  </div>
</div>
