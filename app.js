const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function link(url, text) {
  return url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text)}</a>` : esc(text);
}

async function getJSON(path) {
  try {
    const resp = await fetch(path);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

function emptyState(text) {
  return `<p class="empty">${esc(text)}</p>`;
}

function sectionHtml(title, items, emptyText) {
  const body = items.length
    ? `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`
    : `<p class="empty">${esc(emptyText)}</p>`;
  return `<h3>${esc(title)}</h3>${body}`;
}

function renderMeta(summary) {
  if (!summary || !summary.updated_at) {
    $("updated-at").textContent = "尚未生成";
    return;
  }
  $("updated-at").textContent = `${summary.updated_at.replace("T", " ").slice(0, 16)}（北京时间）`;
  const stats = summary.stats || {};
  $("stat-houses").textContent = stats.houses ?? 0;
  $("stat-performances").textContent = stats.performances ?? 0;
  $("stat-news").textContent = stats.news ?? 0;
  $("stat-artists").textContent = stats.artists ?? 0;
  $("stat-ncpa-artists").textContent = stats.ncpa_artists ?? 0;
  $("stat-ncpa-productions").textContent = stats.ncpa_productions ?? 0;
}

function renderDigest(digest) {
  const el = $("digest-body");
  if (!digest || !digest.date) {
    el.innerHTML = emptyState("日报尚未生成，等待首次定时运行。");
    return;
  }
  const news = (digest.news || []).map(
    (n) => `${link(n.url, n.title)} <span class="badge">${esc(n.source)}</span>`
  );
  const schedule = (digest.schedule_updates || []).map(
    (s) => `${esc(s.date)} ${esc(s.house)}：${link(s.url, s.title)}`
  );
  const artists = (digest.artists || []).map((a) => {
    const head = `<strong>${esc(a.name)}</strong>${a.category ? `（${esc(a.category)}）` : ""}`;
    const subs = (a.mentions || []).map((m) => `<div class="sub">· ${link(m.url, m.title)}</div>`).join("");
    return head + subs;
  });
  const upcoming = (digest.upcoming_7 || []).map(
    (u) => `${esc(u.date)} ${esc(u.house)}：${link(u.url, u.title)}`
  );
  const ncpa = (digest.ncpa || []).map((n) => {
    const head = `${link(n.url, n.title)} <span class="badge">${esc(n.source)}</span>`;
    const subs = (n.artists || []).map((a) => {
      const prods = (a.productions || []).map((p) => `${p.title}(${p.year})`);
      const shown = prods.length > 4 ? `${prods.slice(0, 4).join("、")} 等 ${prods.length} 部` : prods.join("、");
      const suffix = shown ? `：曾合作 ${shown}` : "：曾与国家大剧院合作";
      return `<div class="sub">· ${esc(a.name)}（${esc(a.category || "艺术家")}）${esc(suffix)}</div>`;
    }).join("");
    return head + subs;
  });
  el.innerHTML =
    sectionHtml("今日要闻", news, "今日暂无新报道") +
    sectionHtml("国家大剧院关联动态", ncpa, "今日暂无与大剧院合作艺术家相关的报道") +
    sectionHtml("排期更新", schedule, "今日暂无排期更新") +
    sectionHtml("艺术家动态", artists, "关注名单暂无新动态") +
    sectionHtml("未来 7 天值得关注", upcoming, "暂无排期数据");
}

function renderNcpaArtists(artists) {
  const el = $("ncpa-artist-list");
  if (!artists || !artists.length) {
    el.innerHTML = emptyState("艺术家库尚未生成，等待首次定时运行。");
    return;
  }
  const apply = () => {
    const q = $("ncpa-search").value.trim().toLowerCase();
    const list = artists.filter((a) =>
      `${a.name || ""} ${(a.name_en || []).join(" ")} ${a.category || ""}`.toLowerCase().includes(q)
    );
    if (!list.length) {
      el.innerHTML = emptyState("没有匹配的艺术家。");
      return;
    }
    el.innerHTML = `<ul class="feed">${list.map((a) => {
      const prods = a.productions || [];
      const shown = prods.slice(0, 6).map((p) => `${p.title}(${p.year})`).join("、");
      const more = prods.length > 6 ? ` 等 ${prods.length} 部` : "";
      return `
        <li>
          <strong>${esc(a.name)}</strong> <span class="badge">${esc(a.category || "艺术家")}</span>
          <div class="sub">合作制作：${esc(shown)}${esc(more)}</div>
        </li>`;
    }).join("")}</ul>`;
  };
  $("ncpa-search").addEventListener("input", apply);
  apply();
}

function renderNews(news) {
  const el = $("news-list");
  if (!news || !news.length) {
    el.innerHTML = emptyState("还没有新闻数据，等待首次定时运行。");
    return;
  }
  const items = news.slice(0, 40).map(
    (n) => `
      <li>
        <div>${link(n.url, n.title)}</div>
        <div class="sub">
          <span class="badge">${esc(n.source_name || n.source || "")}</span>
          <span class="date">${esc((n.published || n.fetched_at || "").slice(0, 10))}</span>
        </div>
      </li>`
  );
  el.innerHTML = `<ul class="feed">${items.join("")}</ul>`;
}

function renderArtists(artists) {
  const el = $("artist-list");
  if (!artists || !artists.length) {
    el.innerHTML = emptyState("关注名单暂无动态。");
    return;
  }
  el.innerHTML = artists.map((a) => {
    const mentions = a.mentions || [];
    const latest = mentions.slice(-3).map(
      (m) => `<div class="sub">${m.type} · ${link(m.url, m.title)}</div>`
    ).join("");
    return `
      <div class="card artist-card">
        <div class="artist-name">${esc(a.name)}</div>
        <div class="artist-cat">${esc(a.category || "")}</div>
        <div class="artist-count">近期动态 ${mentions.length} 条</div>
        ${latest || `<p class="empty">暂无动态</p>`}
      </div>`;
  }).join("");
}

function renderPerformances(performances) {
  const el = $("performance-list");
  const houseSelect = $("house-filter");
  if (!performances || !performances.length) {
    el.innerHTML = emptyState("还没有排期数据，请先接入歌剧院订阅源。");
    return;
  }
  const houses = [...new Set(performances.map((p) => p.house_name).filter(Boolean))].sort();
  houseSelect.innerHTML = `<option value="">全部剧院</option>` +
    houses.map((h) => `<option value="${esc(h)}">${esc(h)}</option>`).join("");

  const applyFilter = () => {
    const q = $("search").value.trim().toLowerCase();
    const house = houseSelect.value;
    const list = performances
      .filter((p) => !house || p.house_name === house)
      .filter((p) => {
        if (!q) return true;
        return `${p.composer || ""} ${p.title || ""} ${p.house_name || ""}`.toLowerCase().includes(q);
      })
      .slice(0, 80);
    if (!list.length) {
      el.innerHTML = emptyState("没有匹配的演出。");
      return;
    }
    el.innerHTML = `<ul class="feed">${list.map((p) => `
      <li>
        <div><span class="date">${esc(p.date)}</span> ${esc(p.house_name || "")}：${link(p.url, `${p.composer || ""} ${p.title || ""}`.trim())}</div>
      </li>`).join("")}</ul>`;
  };

  $("search").addEventListener("input", applyFilter);
  houseSelect.addEventListener("change", applyFilter);
  applyFilter();
}

async function init() {
  const [summary, digest, news, artists, performances, ncpaArtists] = await Promise.all([
    getJSON("data/summary.json"),
    getJSON("data/digest/latest.json"),
    getJSON("data/news.json"),
    getJSON("data/artists.json"),
    getJSON("data/performances.json"),
    getJSON("data/ncpa_artists.json"),
  ]);
  renderMeta(summary);
  renderDigest(digest);
  renderNews(news);
  renderArtists(artists);
  renderPerformances(performances);
  renderNcpaArtists(ncpaArtists);
}

init();
