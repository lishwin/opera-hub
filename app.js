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
  el.innerHTML =
    sectionHtml("今日要闻", news, "今日暂无新报道") +
    sectionHtml("排期更新", schedule, "今日暂无排期更新") +
    sectionHtml("艺术家动态", artists, "关注名单暂无新动态") +
    sectionHtml("未来 7 天值得关注", upcoming, "暂无排期数据");
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

function isTourEvent(p) {
  const t = (p?.title || "").toLowerCase();
  const u = (p?.url || "").toLowerCase();
  if (/(\/tickets-and-events\/.*tour|\/tickets-and-events\/.*behind-the-scene|stages-and-cells|exhibition|\/backstage-tour|[-_/]fuehrung|[-_/]visite|[-_/]visita)/i.test(u)) {
    return true;
  }
  if (/\b(tour|tours|guided\s+walk|walking\s+tour|backstage\s+tour|open\s+day)\b/i.test(t)) {
    return true;
  }
  if (/\b(behind the scenes|stages and cells of covent garden|exhibition tours?)\b/i.test(t)) {
    return true;
  }
  if (/(?<!auf)(?<!ent)f(ü|ue)hrung(en)?\b/i.test(t)) {
    return true;
  }
  if (/\b(rundgang|besichtigung|werksf(ü|ue)hrung)\b/i.test(t) || t.includes("pausenrestaurant") || t.includes("refektorium")) {
    return true;
  }
  if (/\bvisite(s)?\s+(guidée|guidées|du\s+théâtre|de\s+l['’]opéra|des\s+coulisses)\b/i.test(t)) {
    return true;
  }
  if (/\b(visita\s+guidata|visite\s+guidate|tour\s+guidato)\b/i.test(t)) {
    return true;
  }
  return false;
}

function renderPerformances(performances) {
  const el = $("performance-list");
  const houseSelect = $("house-filter");
  const validPerformances = (performances || []).filter((p) => !isTourEvent(p));
  if (!validPerformances.length) {
    el.innerHTML = emptyState("还没有排期数据，请先接入歌剧院订阅源。");
    return;
  }
  const houses = [...new Set(validPerformances.map((p) => p.house_name).filter(Boolean))].sort();
  houseSelect.innerHTML = `<option value="">全部剧院</option>` +
    houses.map((h) => `<option value="${esc(h)}">${esc(h)}</option>`).join("");

  const applyFilter = () => {
    const q = $("search").value.trim().toLowerCase();
    const house = houseSelect.value;
    const list = validPerformances
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
  const [summary, digest, news, artists, performances] = await Promise.all([
    getJSON("data/summary.json"),
    getJSON("data/digest/latest.json"),
    getJSON("data/news.json"),
    getJSON("data/artists.json"),
    getJSON("data/performances.json"),
  ]);
  renderMeta(summary);
  renderDigest(digest);
  renderNews(news);
  renderArtists(artists);
  renderPerformances(performances);
}

init();
