<script>
  import { createEventDispatcher } from "svelte";
  import { authHeaders, fmtTime } from "./api.js";

  export let logs = [];
  export let isWriter = false;

  const dispatch = createEventDispatcher();

  let chainage = "";
  let section = "掌子面";
  let deltaMm = "";
  let error = "";
  let notice = "";
  let loading = false;

  async function submit() {
    error = "";
    notice = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ chainage, section, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 抽稀拦截会返回 422 与整份退回说明，原样亮出来
        error = data.detail || "提交失败";
        dispatch("changed");
        return;
      }
      notice = `已进队：${data.chainage}（${data.section}）${data.delta_mm} mm，等待认领`;
      chainage = "";
      deltaMm = "";
      dispatch("changed");
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }
</script>

<style>
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .err { color: #fb7185; white-space: pre-wrap; }
  .ok-msg { color: #86efac; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .muted { color: #a8a29e; font-size: 0.85rem; }
</style>

{#if isWriter}
  <section>
    <label>里程桩号</label>
    <input placeholder="例如 K20+050" bind:value={chainage} />
    <label>部位</label>
    <select bind:value={section}>
      <option value="掌子面">掌子面</option>
      <option value="边墙">边墙</option>
    </select>
    <label>收敛（毫米，可正可负）</label>
    <input type="number" step="0.1" bind:value={deltaMm} />
    <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
    {#if error}<p class="err">{error}</p>{/if}
    {#if notice}<p class="ok-msg">{notice}</p>{/if}
  </section>
{:else}
  <section>
    <p class="muted">巡检员只读：可查看总表与抽稀专页履历，不能交单也不能扳抽稀开关。</p>
  </section>
{/if}

<section>
  <table>
    <thead>
      <tr><th>编号</th><th>桩号</th><th>部位</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th><th>时间</th></tr>
    </thead>
    <tbody>
      {#each logs as row}
        <tr>
          <td>{row.id}</td>
          <td>{row.chainage}</td>
          <td>{row.section}</td>
          <td>{row.delta_mm}</td>
          <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
          <td>
            {#if row.verdict}
              <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
            {:else}—{/if}
          </td>
          <td>{row.reason ?? "—"}</td>
          <td>{fmtTime(row.created_at)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>
