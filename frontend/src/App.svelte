<script>
  import { onMount, onDestroy } from "svelte";
  import ThinDesk from "./ThinDesk.svelte";

  let session = null;
  let logs = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let part = "拱顶";
  let deltaMm = "";
  let error = "";
  let loading = false;
  let timer;
  let view = location.hash === "#thin" ? "thin" : "home";

  $: isWriter = session?.role === "writer";

  function onHash() {
    view = location.hash === "#thin" ? "thin" : "home";
  }

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
  }

  function startPolling() {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, 2000);
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      startPolling();
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    timer = null;
    session = null;
    logs = [];
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, part, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 抽稀台整份退回：飞点没有进队，把退回原因原样交代
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function fmt(ts) {
    return ts ? new Date(ts).toLocaleString("zh-CN", { hour12: false }) : "—";
  }

  onMount(() => window.addEventListener("hashchange", onHash));
  onDestroy(() => window.removeEventListener("hashchange", onHash));

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      startPolling();
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1180px; margin: 0 auto; padding: 1.5rem; }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  .topbar {
    display: flex; align-items: center; gap: 1.25rem;
    border-bottom: 1px solid #44403c; padding-bottom: 0.75rem; margin-bottom: 1.25rem;
  }
  nav { display: flex; gap: 0.5rem; }
  nav a {
    color: #d6d3d1; text-decoration: none; padding: 0.35rem 0.85rem;
    border-radius: 6px; border: 1px solid #57534e; font-size: 0.9rem;
  }
  nav a.active { background: #d97706; color: #fff; border-color: #d97706; }
  .who { margin-left: auto; color: #a8a29e; font-size: 0.85rem; display: flex; gap: 0.75rem; align-items: center; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  select { width: auto; min-width: 8rem; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; white-space: pre-wrap; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <div class="topbar">
      <h1>隧道收敛测缝台</h1>
      <nav>
        <a href="#/" class:active={view !== "thin"}>总表</a>
        <a href="#thin" class:active={view === "thin"}>抽稀台</a>
      </nav>
      <div class="who">
        <span>{session.username}（{isWriter ? "测量员·可提交" : "巡检员·只读"}）</span>
        <button class="secondary" on:click={logout}>退出</button>
      </div>
    </div>

    {#if view === "thin"}
      <ThinDesk {session} />
    {:else}
      <section>
        <div style="display:flex;gap:0.5rem;align-items:center;">
          <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
          <a href="#thin" style="color:#fbbf24;font-size:0.85rem;">放炮飞点频发 → 去抽稀台</a>
        </div>
      </section>
      {#if isWriter}
        <section>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>测读部位</label>
          <select bind:value={part}>
            <option value="拱顶">拱顶</option>
            <option value="边墙">边墙（锤击）</option>
          </select>
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {/if}
      <section>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>部位</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th><th>提交人</th><th>时间</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td>{row.part}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
                <td>{row.created_by}</td>
                <td>{fmt(row.created_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</main>
