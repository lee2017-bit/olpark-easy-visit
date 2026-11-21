(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
    for (const k of kids) if (k != null) n.append(k);
    return n;
  };
  const icon = (name, cls = "ic") => {
    const s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("class", cls);
    s.setAttribute("aria-hidden", "true");
    const u = document.createElementNS(SVGNS, "use");
    u.setAttribute("href", "#i-" + name);
    s.append(u);
    return s;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const WHO_ICON = { wheel: "wheel", stroller: "stroller", slow: "cane", vision: "eye", hearing: "ear" };
  const KIND = { warn: ["alert", "주의"], tip: ["info", "도움말"], gap: ["question", "공개 자료 없음"] };
  const FIRST = 10;
  const LABEL_SIDE = { kspo_dome: "right", lawn88: "left", woori_art_hall: "left" };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 못 해도 화면엔 적용 */ } },
  };
  const state = { d: null, sel: 0, showAll: false, venue: "all", who: new Set(), map: null, venueMarkers: {} };
  try { (JSON.parse(store.get("olpark-who") || "[]") || []).forEach((w) => state.who.add(w)); } catch (e) { /* 무시 */ }

  const md = (date) => { const [, m, d] = date.split("-"); return { m: +m, d: +d }; };
  const km = (a, b) => {
    const r = Math.PI / 180, la1 = a.lat * r, la2 = b.lat * r;
    const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  };
  const forMe = (it) => !state.who.size || !it.who || !it.who.length || it.who.some((w) => state.who.has(w));

  // ---------- 누구와 ----------
  function renderWho() {
    const box = $("who");
    box.textContent = "";
    for (const [k, label] of Object.entries(state.d.who)) {
      const b = el("button", { type: "button", class: "who-btn", "aria-pressed": String(state.who.has(k)) },
        icon(WHO_ICON[k] || "info"), el("span", {}, label));
      b.addEventListener("click", () => {
        if (state.who.has(k)) state.who.delete(k); else state.who.add(k);
        store.set("olpark-who", JSON.stringify([...state.who]));
        renderWho();
        renderDay(state.d.days[state.sel]);
      });
      box.append(b);
    }
    $("who-hint").textContent = state.who.size
      ? `${[...state.who].map((k) => state.d.who[k]).join(", ")}에 해당하는 안내와 모두에게 필요한 안내만 보여요.`
      : "여러 개 고를 수 있어요. 고르지 않으면 모든 안내가 보여요.";
  }

  // ---------- 날짜 ----------
  function renderChips() {
    const box = $("chips");
    box.textContent = "";
    const days = state.d.days;
    days.forEach((day, i) => {
      if (!state.showAll && i >= FIRST && i !== state.sel) return;
      const { m, d } = md(day.date);
      const venues = [...new Set(day.shows.map((s) => s.venue))];
      const b = el("button", {
        type: "button", class: "chip", "aria-pressed": String(i === state.sel),
        "aria-label": `${m}월 ${d}일 ${day.weekday}요일${day.holiday ? " 공휴일" : ""}, 공연 ${day.shows.length}개: ${venues.join(", ")}`,
      },
        el("span", { class: "d" }, `${m}.${d}`),
        el("span", { class: "w" + (day.offday ? " off" : "") }, day.holiday ? "공휴일" : day.weekday),
        el("span", { class: "v" }, venues.length > 1 ? `${venues[0]} 외 ${venues.length - 1}` : venues[0]));
      b.addEventListener("click", () => select(i));
      box.append(b);
    });
    const more = $("more");
    const rest = days.length - FIRST;
    more.hidden = rest <= 0;
    more.textContent = state.showAll ? "날짜 접기" : `날짜 더 보기 (${rest}일)`;
  }

  function select(i) {
    state.sel = i;
    state.venue = "all";
    renderChips();
    renderDay(state.d.days[i]);
    highlightVenues(state.d.days[i]);
  }

  // ---------- 선택한 날 ----------
  function srcBadge(it) {
    if (!it.src) return null;
    return it.url ? el("a", { class: "src", href: it.url, rel: "noopener", target: "_blank" }, it.src)
      : el("span", { class: "src" }, it.src);
  }

  function itemLi(it, showVenue, shortOf) {
    const [ic, label] = KIND[it.kind] || ["check", null];
    const meta = el("span", { class: "meta" });
    if (label) meta.append(el("span", { class: "kind" }, label));
    if (showVenue && it.venue) meta.append(el("span", { class: "vtag" }, shortOf[it.venue] || it.venue));
    const b = srcBadge(it);
    if (b) meta.append(b);
    return el("li", { class: "item" + (it.kind ? " k-" + it.kind : "") },
      el("span", { class: "bub" }, icon(ic)),
      el("div", {}, el("b", {}, it.t), it.s ? el("span", { class: "s" }, it.s) : null, meta));
  }

  function renderDay(day) {
    const box = $("day");
    box.textContent = "";
    const { m, d } = md(day.date);
    const p = el("article", { class: "panel" });
    p.append(el("div", { class: "panel-head" + (day.offday ? " off" : "") },
      el("span", { class: "panel-date" }, `${m}월 ${d}일 (${day.weekday})${day.holiday ? " 공휴일" : ""}`),
      el("span", { class: "count" }, `공연 ${day.shows.length}개`)));

    const ul = el("ul", { class: "shows", "aria-label": "이날 공연" });
    for (const s of day.shows) {
      const when = s.start ? (s.end ? `${s.start}~${s.end} 무렵` : `${s.start} 시작`) : "시간은 공연 공지 확인";
      ul.append(el("li", {}, icon("stage"),
        el("span", { class: "v" }, `${s.venue} · ${when}`),
        el("span", { class: "t" }, s.title),
        el("span", { class: "x" }, [s.vendor && `예매 ${s.vendor}`, s.age && `관람 ${s.age}`, s.inquiry && `문의 ${s.inquiry}`].filter(Boolean).join(" · ")),
        s.link ? el("a", { class: "x", href: s.link, rel: "noopener", target: "_blank" }, "공연 정보 보기") : null));
    }
    p.append(ul);

    const shortOf = Object.fromEntries(day.shows.map((s) => [s.venue_key, s.venue]));
    const vkeys = [...new Set(day.shows.map((s) => s.venue_key))];
    if (vkeys.length > 1) {
      const g = el("div", { class: "vpick", role: "group", "aria-label": "어느 공연장에 가세요?" },
        el("span", { class: "vpick-label" }, "어느 공연장?"));
      for (const k of ["all", ...vkeys]) {
        const b = el("button", { type: "button", class: "vp-btn", "aria-pressed": String(state.venue === k) }, k === "all" ? "모두" : shortOf[k]);
        b.addEventListener("click", () => { state.venue = k; renderDay(day); });
        g.append(b);
      }
      p.append(g);
    }

    const showVenue = vkeys.length > 1 && state.venue === "all";
    const steps = el("div", { class: "steps" });
    state.d.steps.forEach((st, n) => {
      const dyn = (day.items[st.key] || []).filter((it) => state.venue === "all" || !it.venue || it.venue === state.venue);
      const items = [...dyn, ...st.items].filter(forMe);
      if (!items.length) return;
      const sec = el("section", { class: "step", "aria-labelledby": `st-${st.key}` },
        el("h3", { id: `st-${st.key}` }, el("span", { class: "num" }, String(n + 1)), icon(st.icon), st.title));
      const list = el("ul", { class: "items" });
      // 주의 → 그날 안내 → 늘 같은 안내 순서
      // 집에 갈 때는 시간 순서(끝나는 시각 → 출차 → 콜택시) 그대로
      const order = (it) => (st.key === "home" ? 0 : it.kind === "warn" ? 0 : it.kind === "gap" ? 3 : 1);
      items.map((it, i) => [it, i]).sort((a, b) => order(a[0]) - order(b[0]) || a[1] - b[1])
        .forEach(([it]) => list.append(itemLi(it, showVenue, shortOf)));
      sec.append(list);
      steps.append(sec);
    });
    p.append(steps);
    box.append(p);
  }

  // ---------- 지도 ----------
  function pinIcon(kind, label, on, side) {
    const cls = kind === "elev" ? "mk mk-elev" : "mk mk-venue" + (on ? " on" : "");
    const sym = kind === "elev" ? "elev" : "stage";
    const size = on ? 36 : 30;
    return L.divIcon({
      className: "pin",
      html: `<span class="${cls}"><svg aria-hidden="true"><use href="#i-${sym}"/></svg></span><span class="pin-label${side ? " " + side : ""}">${esc(label)}</span>`,
      iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2],
    });
  }

  function exitName(x) { return `${x.line} ${x.station}역 ${x.exit}번 출구`; }

  function initMap() {
    const mp = state.d.map;
    const exits = state.d.subway.exits.filter((x) => x.lat);
    renderMapList(exits);
    const box = $("map");
    if (!window.L) { box.append(el("p", { class: "map-fallback" }, "지도를 불러오지 못했습니다. 아래 목록을 참고하세요.")); return; }
    const map = L.map(box, { scrollWheelZoom: false, tap: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 기여자',
    }).addTo(map);
    const pts = [];
    for (const v of mp.venues) {
      const mk = L.marker([v.lat, v.lon], { icon: pinIcon("venue", v.short, false, LABEL_SIDE[v.key]), title: v.name, alt: v.name, keyboard: true })
        .bindPopup(`<b>${esc(v.name)}</b>`).addTo(map);
      state.venueMarkers[v.key] = { mk, v };
      pts.push([v.lat, v.lon]);
    }
    const c = { lat: mp.venues.reduce((s, v) => s + v.lat, 0) / mp.venues.length, lon: mp.venues.reduce((s, v) => s + v.lon, 0) / mp.venues.length };
    for (const x of exits) {
      L.marker([x.lat, x.lon], { icon: pinIcon("elev", `${x.line.replace("호선", "")} ${x.station} ${x.exit}번`, false), title: exitName(x), alt: exitName(x), keyboard: true })
        .bindPopup(`<b>${esc(exitName(x))}</b><br>지상으로 나가는 엘리베이터<br><span class="small">${esc(x.src)}</span>`).addTo(map);
      if (km(c, x) < 1) pts.push([x.lat, x.lon]);
    }
    map.fitBounds(pts, { padding: [36, 36] });
    state.map = map;
  }

  function highlightVenues(day) {
    if (!state.map) return;
    const on = new Set(day.shows.map((s) => s.venue_key));
    for (const [k, { mk, v }] of Object.entries(state.venueMarkers)) mk.setIcon(pinIcon("venue", v.short, on.has(k), LABEL_SIDE[k]));
  }

  function renderMapList(exits) {
    const ul = $("map-list");
    ul.textContent = "";
    for (const x of exits) {
      ul.append(el("li", {}, icon("elev"), el("span", {}, el("b", {}, exitName(x)), ` · ${x.src}`)));
    }
    ul.append(el("li", { class: "warnline" }, icon("alert"), el("span", {}, `${state.d.subway.park_guidance} — 5호선·8호선을 타면 이 출구에 엘리베이터가 없을 수 있어요.`)));
  }

  function renderFooter(d) {
    $("generated").textContent = d.generated_at + " (KST)";
    const ul = $("sources");
    for (const s of d.sources) ul.append(el("li", {}, el("a", { href: s.url, rel: "noopener" }, s.name)));
    const g = $("gaps");
    for (const t of d.gaps) g.append(el("li", {}, t));
  }

  // 글자 크기: 누른 단계를 <html data-fs>에 반영하고 저장 (다음 방문에도 유지)
  function setFontSize(level) {
    const root = document.documentElement;
    if (level === "0") delete root.dataset.fs; else root.dataset.fs = level;
    document.querySelectorAll(".fs-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.fs === level)));
    store.set("olpark-fs", level);
    if (state.map) setTimeout(() => state.map.invalidateSize(), 50);
  }
  document.querySelectorAll(".fs-btn").forEach((b) => b.addEventListener("click", () => setFontSize(b.dataset.fs)));
  setFontSize(document.documentElement.dataset.fs || "0");
  $("more").addEventListener("click", () => { state.showAll = !state.showAll; renderChips(); });

  fetch("data/site.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      state.d = d;
      renderFooter(d);
      renderWho();
      if (!d.days.length) { $("day").textContent = "앞으로 60일 안에 공연이 없습니다."; return; }
      renderChips();
      renderDay(d.days[0]);
      try { initMap(); } catch (e) { $("map").textContent = "지도를 불러오지 못했습니다."; }
      highlightVenues(d.days[0]);
    })
    .catch(() => { $("day").textContent = "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."; });
})();
