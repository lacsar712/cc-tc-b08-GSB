<script>
  import { createEventDispatcher } from "svelte";
  import { authHeaders, fmtTime, RULE_LABELS } from "./api.js";

  export let thinning = null;
  export let rejections = [];
  export let isWriter = false;

  const dispatch = createEventDispatcher();

  let windowSeconds = "";
  let jumpThreshold = "";
  let syncedKey = null;
  let error = "";
  let notice = "";
  let busy = false;

  // 接口每 2 秒刷新一次 thinning；只在服务端状态变化时回填输入框，避免打断正在打字的人
  $: if (thinning && thinning.updated_at + "/" + thinning.enabled !== syncedKey) {
    syncedKey = thinning.updated_at + "/" + thinning.enabled;
    windowSeconds = thinning.window_seconds;
    jumpThreshold = thinning.jump_threshold_mm;
  }

  // 中列：最新一批被整份退回的样例（同一 batch_id）
  $: latestBatch = rejections.length
    ? rejections.filter((r) => r.batch_id === rejections[0].batch_id)
    : [];

  async function put(body) {
    error = "";
    notice = "";
    busy = true;
    try {
      const res = await fetch("/api/thinning", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "操作失败";
        return;
      }
      notice = thinning && !data.enabled ? "抽稀已停：新单不再拦截，旧履历保留" : "已保存";
      dispatch("changed");
    } catch {
      error = "网络异常";
    } finally {
      busy = false;
    }
  }

  const toggle = () => put({ enabled: !(thinning && thinning.enabled) });
  const saveParams = () =>
    put({ window_seconds: Number(windowSeconds), jump_threshold_mm: Number(jumpThreshold) });
</script>

<style>
  .grid {
    display: grid;
    grid-template-columns: 300px 1fr 1.3fr;
    gap: 1rem;
    align-items: start;
  }
  @media (max-width: 960px) {
    .grid { grid-template-columns: 1fr; }
  }
  .col {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem;
  }
  .col h2 { margin: 0 0 0.75rem; font-size: 1rem; color: #fbbf24; }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }
  .ok-msg { color: #86efac; }
  .hint { color: #a8a29e; font-size: 0.85rem; }
  .lamp-big {
    width: 1rem; height: 1rem; border-radius: 50%; display: inline-block;
    background: #57534e; margin-right: 0.5rem; vertical-align: -0.15rem;
  }
  .lamp-big.on { background: #4ade80; box-shadow: 0 0 10px #4ade80; }
  .state-line { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.75rem; }
  .median-box {
    margin-top: 0.9rem; padding: 0.6rem 0.75rem; border-radius: 6px;
    background: #0c0a09; border: 1px solid #44403c; font-size: 0.88rem;
    color: #d6d3d1; line-height: 1.7;
  }
  .median-box strong { color: #fbbf24; }
  .reject-card {
    background: #0c0a09; border: 1px solid #7f1d1d; border-radius: 6px;
    padding: 0.7rem 0.85rem; margin-bottom: 0.7rem;
  }
  .rc-head { display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
  .rc-head strong { color: #fca5a5; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.78rem; background: #7f1d1d; color: #fca5a5; }
  .meta { color: #a8a29e; font-size: 0.8rem; margin: 0.35rem 0 0; }
  .detail { margin: 0.4rem 0 0; font-size: 0.9rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.4rem; border-bottom: 1px solid #44403c; }
  .scroll { max-height: 560px; overflow-y: auto; }
</style>

{#if !thinning}
  <div class="col">抽稀台状态读取中…</div>
{:else}
  <div class="grid">
    <div class="col">
      <h2>抽稀开关</h2>
      <div class="state-line">
        <span class="lamp-big {thinning.enabled ? 'on' : ''}"></span>
        {thinning.enabled ? "抽稀中：飞点整份退回" : "已停：新单不再拦截"}
      </div>
      <button disabled={!isWriter || busy} on:click={toggle}>
        {thinning.enabled ? "停止抽稀" : "开启抽稀"}
      </button>
      {#if !isWriter}<p class="hint">巡检员只能看履历，不能扳开关。</p>{/if}

      <div style="margin-top: 1rem;">
        <label>取样窗（秒）</label>
        <input type="number" min="1" max="86400" bind:value={windowSeconds} disabled={!isWriter} />
        <label>跳变门槛（mm，相对窗内中位）</label>
        <input type="number" step="0.1" min="0" bind:value={jumpThreshold} disabled={!isWriter} />
        <button class="secondary" disabled={!isWriter || busy} on:click={saveParams}>保存参数</button>
      </div>

      <div class="median-box">
        <div>窗内中位：<strong>{thinning.window_median ?? "—"}</strong> mm</div>
        <div>窗内样本：{thinning.window_samples} 笔 / {thinning.window_seconds} 秒</div>
        <div>最近变更：{thinning.updated_by ?? "—"} · {fmtTime(thinning.updated_at)}</div>
      </div>
      {#if error}<p class="err">{error}</p>{/if}
      {#if notice}<p class="ok-msg">{notice}</p>{/if}
    </div>

    <div class="col">
      <h2>拒收样例（最新一批）</h2>
      {#if latestBatch.length}
        {#each latestBatch as r}
          <div class="reject-card">
            <div class="rc-head">
              <span class="tag">{RULE_LABELS[r.rule] ?? r.rule}</span>
              <strong>{r.chainage}（{r.section}）</strong>
              <span>{r.delta_mm} mm</span>
            </div>
            <p class="detail">{r.detail}</p>
            <p class="meta">
              当时中位 {r.window_median ?? "—"} mm · 门槛 {r.jump_threshold_mm ?? "—"} mm ·
              窗 {r.window_seconds ?? "—"} 秒 · {r.created_by} · {fmtTime(r.created_at)}
            </p>
          </div>
        {/each}
      {:else}
        <p class="hint">暂无拒收样例。抽稀开着时，飞点与窗内重复交单会整份退回并列在这里。</p>
      {/if}
    </div>

    <div class="col">
      <h2>已拦住的履历（{rejections.length} 笔）</h2>
      <div class="scroll">
        <table>
          <thead>
            <tr><th>时间</th><th>桩号</th><th>部位</th><th>收敛mm</th><th>规则</th><th>提交人</th></tr>
          </thead>
          <tbody>
            {#each rejections.slice(0, 50) as r}
              <tr>
                <td>{fmtTime(r.created_at)}</td>
                <td>{r.chainage}</td>
                <td>{r.section}</td>
                <td>{r.delta_mm}</td>
                <td><span class="tag">{RULE_LABELS[r.rule] ?? r.rule}</span></td>
                <td>{r.created_by}</td>
              </tr>
            {/each}
            {#if !rejections.length}
              <tr><td colspan="6" class="hint">还没有拦过任何交单。</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
{/if}
