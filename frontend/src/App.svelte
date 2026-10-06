<script>
  import LogsView from "./LogsView.svelte";
  import ThinningView from "./ThinningView.svelte";

  let session = null;
  let logs = [];
  let thinning = null;
  let rejections = [];
  let view = "logs";
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let error = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const opts = { headers: headers() };
    try {
      const [logsRes, stateRes, rejRes] = await Promise.all([
        fetch("/api/logs", opts),
        fetch("/api/thinning", opts),
        fetch("/api/thinning/rejections", opts),
      ]);
      if (logsRes.status === 401) {
        logout();
        return;
      }
      if (logsRes.ok) logs = await logsRes.json();
      if (stateRes.ok) thinning = await stateRes.json();
      if (rejRes.ok) rejections = await rejRes.json();
    } catch {
      /* 网络抖动时保留旧数据，下一轮再刷 */
    }
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

  function startPolling() {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, 2000);
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    thinning = null;
    rejections = [];
    localStorage.removeItem("tunnel_session");
  }

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
  main { max-width: 1080px; margin: 0 auto; padding: 1.5rem; }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
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
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }

  .topbar {
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    background: #0c0a09; border-bottom: 1px solid #44403c;
    padding: 0.7rem 1.5rem;
  }
  .topbar nav { display: flex; gap: 0.4rem; }
  .topbar nav button {
    background: transparent; color: #d6d3d1; border: 1px solid #44403c;
    padding: 0.35rem 0.9rem; border-radius: 999px; font-weight: 500;
  }
  .topbar nav button.active {
    background: #d97706; border-color: #d97706; color: #fff;
  }
  .topbar .spacer { flex: 1; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-size: 0.82rem; color: #d6d3d1; border: 1px solid #44403c;
    border-radius: 999px; padding: 0.25rem 0.7rem;
  }
  .lamp {
    width: 0.65rem; height: 0.65rem; border-radius: 50%;
    display: inline-block; background: #57534e;
  }
  .lamp.on { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
  .lamp.off { background: #57534e; }
  .who { color: #a8a29e; font-size: 0.85rem; }
</style>

{#if !session}
  <main>
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
  </main>
{:else}
  <header class="topbar">
    <h1>隧道收敛测缝台</h1>
    <nav>
      <button class:active={view === "logs"} on:click={() => (view = "logs")}>总表</button>
      <button class:active={view === "thinning"} on:click={() => (view = "thinning")}>抽稀专页</button>
    </nav>
    <span class="chip" title="抽稀台实时状态（来自接口）">
      {#if thinning}
        <span class="lamp {thinning.enabled ? 'on' : 'off'}"></span>
        {thinning.enabled ? "抽稀中" : "抽稀已停"}
      {:else}
        <span class="lamp off"></span>状态读取中
      {/if}
    </span>
    <span class="spacer"></span>
    <span class="who">{session.username}（{isWriter ? "测量员" : "巡检员·只读"}）</span>
    <button class="secondary" on:click={logout}>退出</button>
  </header>
  <main>
    {#if view === "logs"}
      <LogsView {logs} {isWriter} on:changed={refresh} />
    {:else}
      <ThinningView {thinning} {rejections} {isWriter} on:changed={refresh} />
    {/if}
  </main>
{/if}
