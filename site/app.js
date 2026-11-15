(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
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
  const SHORT = { kspo_dome: "KSPO DOME", olympic_hall: "올림픽홀", handball: "라이브 아레나", lawn88: "88잔디마당" };
  const FIRST = 8;
  const LABEL_SIDE = { kspo_dome: "right", lawn88: "left" };
  const state = { d: null, sel: 0, showAll: false, map: null, venueMarkers: {} };

  const km = (a, b) => {
    const r = Math.PI / 180, la1 = a.lat * r, la2 = b.lat * r;
    const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  };
  const md = (date) => { const [, m, d] = date.split("-"); return { m: +m, d: +d }; };

  // ---------- 날짜 칩 ----------
  function renderChips() {
    const box = $("chips");
    box.textContent = "";
    const days = state.d.days;
    days.forEach((day, i) => {
      if (!state.showAll && i >= FIRST && i !== state.sel) return;
      const { m, d } = md(day.date);
      const off = day.offday;
      const b = el("button", {
        type: "button", class: "chip", "aria-pressed": String(i === state.sel),
        "aria-label": `${m}월 ${d}일 ${day.weekday}요일${day.holiday ? " 공휴일" : ""}, 만차 위험 ${day.grade}`,
      },
        el("span", { class: "d" }, `${m}.${d}`),
        el("span", { class: "w" + (off ? " off" : "") }, day.holiday ? "공휴일" : day.weekday),
        el("span", { class: `g g-${day.grade}` }, day.grade));
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
    renderChips();
    renderDay(state.d.days[i]);
    highlightVenues(state.d.days[i]);
  }

  // ---------- 선택한 날 ----------
  function act(cls, ico, title, sub) {
    return el("li", { class: "act " + cls },
      el("span", { class: "bub" }, icon(ico)),
      el("div", {}, el("b", {}, title), sub ? el("span", { class: "s" }, sub) : null));
  }

  function renderDay(day) {
    const box = $("day");
    box.textContent = "";
    const { m, d } = md(day.date);
    const p = el("article", { class: "panel" });
    const head = el("div", { class: `panel-head g-${day.grade}` },
      el("span", { class: "panel-date" }, `${m}월 ${d}일 (${day.weekday})${day.holiday ? " 공휴일" : ""}`),
      el("span", { class: "grade" }, icon("car"), `만차 위험 ${day.grade}`));
    p.append(head);
    p.append(el("p", { class: "basis g-" + day.grade }, icon("chart", "ic sm"), el("span", {}, day.basis)));

    if (day.events.length) {
      const ul = el("ul", { class: "shows", "aria-label": "이날 공연" });
      for (const e of day.events) {
        ul.append(el("li", {}, icon("stage"),
          el("span", { class: "v" }, `${e.venue}${e.start ? " · " + e.start : ""}`),
          el("span", { class: "t" }, e.title)));
      }
      p.append(ul);
    } else {
      p.append(el("p", { class: "empty" }, "대형 공연장 공연 없음"));
    }

    const acts = el("ul", { class: "acts", "aria-label": "교통약자 안내" });
    if (day.car === "avoid") acts.append(act("bad", "car", "자가용 비권장", `비슷한 날엔 대개 ${day.arrive_by}시 전후부터 만차였어요`));
    else if (day.car === "early") acts.append(act("mid", "clock", `자가용이면 ${day.arrive_by}시 전 도착`, "늦으면 장애인 구역까지 들어가기 어려울 수 있어요"));
    else acts.append(act("good", "car", day.offday ? "주차 여유 예상" : "평일, 주차 여유 있는 편", day.offday ? "공연 없는 휴일 기록이 적어 참고만 하세요" : null));

    const mp = state.d.map;
    const seen = new Set();
    for (const e of day.events) {
      if (seen.has(e.venue_key)) continue;
      seen.add(e.venue_key);
      const v = mp && mp.venues.find((x) => x.key === e.venue_key);
      if (!v) continue;
      const lotShort = v.lot.split(" (")[0], gates = (v.lot.match(/\((.+)\)/) || [])[1];
      acts.append(act("venue", "park", `${SHORT[v.key]} → ${lotShort}`,
        (v.disabled_spaces ? `장애인 주차 ${v.disabled_spaces}면 · ${v.walk}` : "지정 장애인 주차 안내 없음") + (gates ? ` · ${gates}` : "")));
    }

    let near = null;
    if (mp && seen.size) {
      const v = mp.venues.find((x) => seen.has(x.key));
      near = v && v.nearest_elevator;
    }
    if (near) acts.append(act("elev", "elev", `엘리베이터: ${near.label} 출구`, `공연장까지 직선 약 ${near.km}km · 공원 안내 출구와 달라요`));
    else acts.append(act("elev", "elev", "엘리베이터 출구",
      state.d.access.subway_elevators.map((x) => `${x.line} ${x.station}역 ${x.exit}번`).join(" · ")));

    if (day.evening) {
      const w = act("warn", "wheel", "휠체어 대여는 19시 마감", "한 번에 3시간까지라 저녁 공연엔 개인 휠체어를 권해요");
      acts.append(w);
    }
    if (day.rain_pop != null) {
      acts.append(act(day.rain_pop >= 60 ? "mid" : "", "rain", `강수확률 ${day.rain_pop}%`,
        day.rain_pop >= 60 ? "비 예보를 등급에 반영했어요" : null));
    }
    p.append(acts);
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

  function initMap() {
    const mp = state.d.map;
    const box = $("map");
    if (!mp) { box.replaceWith(el("p", { class: "map-fallback" }, "지도 데이터가 없습니다.")); return; }
    renderMapList(mp);
    if (!window.L) { box.append(el("p", { class: "map-fallback" }, "지도를 불러오지 못했습니다. 아래 목록을 참고하세요.")); return; }
    const map = L.map(box, { scrollWheelZoom: false, tap: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 기여자',
    }).addTo(map);
    const pts = [];
    for (const v of mp.venues) {
      const n = v.nearest_elevator;
      const pop = `<b>${esc(v.name)}</b><br>가까운 주차장 ${esc(v.lot)}<br>` +
        (v.disabled_spaces ? `장애인 주차 ${v.disabled_spaces}면 · ${esc(v.walk)}` : "지정 장애인 주차 안내 없음") +
        (n ? `<br>엘리베이터 출구: ${esc(n.label)} (직선 약 ${n.km}km)` : "");
      const mk = L.marker([v.lat, v.lon], { icon: pinIcon("venue", SHORT[v.key], false, LABEL_SIDE[v.key]), title: v.name, alt: v.name, keyboard: true })
        .bindPopup(pop).addTo(map);
      state.venueMarkers[v.key] = mk;
      pts.push([v.lat, v.lon]);
    }
    const venueCenter = { lat: mp.venues.reduce((s, v) => s + v.lat, 0) / mp.venues.length, lon: mp.venues.reduce((s, v) => s + v.lon, 0) / mp.venues.length };
    for (const x of mp.elevator_exits) {
      const name = `${x.line} ${x.station}역 ${x.exit}번 출구`;
      L.marker([x.lat, x.lon], { icon: pinIcon("elev", `${x.station} ${x.exit}번`, false), title: name, alt: name, keyboard: true })
        .bindPopup(`<b>${esc(name)}</b><br>지상으로 나가는 엘리베이터 (서울교통공사 데이터)`).addTo(map);
      if (km(venueCenter, x) < 1) pts.push([x.lat, x.lon]);
    }
    map.fitBounds(pts, { padding: [36, 36] });
    state.map = map;
  }

  function highlightVenues(day) {
    if (!state.map) return;
    const on = new Set(day.events.map((e) => e.venue_key));
    for (const [k, mk] of Object.entries(state.venueMarkers)) mk.setIcon(pinIcon("venue", SHORT[k], on.has(k), LABEL_SIDE[k]));
  }

  function renderMapList(mp) {
    const ul = $("map-list");
    ul.textContent = "";
    const c = { lat: mp.venues.reduce((s, v) => s + v.lat, 0) / mp.venues.length, lon: mp.venues.reduce((s, v) => s + v.lon, 0) / mp.venues.length };
    for (const x of mp.elevator_exits) {
      const dkm = km(c, x);
      ul.append(el("li", {}, icon("elev"), el("span", {},
        el("b", {}, `${x.line} ${x.station}역 ${x.exit}번 출구`),
        ` · 공연장들에서 직선 약 ${dkm.toFixed(1)}km${dkm >= 1 ? " (지도를 축소하면 보여요)" : ""}`)));
    }
  }

  // ---------- 늘 같은 정보 ----------
  function tile(ico, title, ...rows) {
    return el("article", { class: "tile" }, el("span", { class: "bub" }, icon(ico)), el("h3", {}, title), ...rows);
  }

  function renderTiles(a, mp) {
    const box = $("tiles");
    const ex = a.subway_elevators.map((x) => `${x.line} ${x.station}역 ${x.exit}번`).join(" · ");
    box.append(tile("elev", "엘리베이터 출구", el("p", {}, ex),
      el("p", { class: "warnline" }, `공원 안내 출구와 달라요 — 공원 안내: ${a.park_exit_guidance}`),
      el("p", { class: "note" }, a.subway_note)));

    const sp = (mp ? mp.venues : []).filter((v) => v.disabled_spaces).map((v) => `${SHORT[v.key]} ${v.disabled_spaces}면`).join(" · ");
    box.append(tile("park", "장애인 주차", el("p", {}, sp),
      el("p", { class: "note" }, `출처마다 달라요: 기관 공지 합계 ${a.disabled_parking_total_agency}면 · 한국관광공사 ${((a.disabled_parking_knto || "").match(/\d+\s*칸/) || ["정보 없음"])[0]}`)));

    const r = a.wheelchair_rental;
    const places = Object.entries(r.places).map(([k, v]) => `${k} ${v}대`).join(", ");
    box.append(tile("wheel", "휠체어 대여", el("p", {}, places), el("p", { class: "note" }, `${r.hours} · ${r.rule}`),
      el("p", { class: "warnline" }, "19시 마감 · 3시간 한도 → 저녁 공연엔 개인 휠체어")));

    if (a.stroller_knto) box.append(tile("stroller", "유모차 대여", el("p", {}, a.stroller_knto.replace(/^대여가능\s*\(?/, "").replace(/\)\s*$/, "")), el("p", { class: "note" }, "한국관광공사 무장애 여행 정보")));
    box.append(tile("ramp", "휠체어 진입로", el("p", {}, a.wheelchair_entry_route), el("p", { class: "note" }, "올림픽공원 주차 안내")));
  }

  function renderFooter(d) {
    $("generated").textContent = d.generated_at + " (KST)";
    const ul = $("sources");
    for (const s of d.sources) ul.append(el("li", {}, el("a", { href: s.url, rel: "noopener" }, s.name)));
  }

  $("more").addEventListener("click", () => { state.showAll = !state.showAll; renderChips(); });

  fetch("data/site.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      state.d = d;
      renderFooter(d);
      renderTiles(d.access, d.map);
      if (!d.days.length) { $("day").textContent = "표시할 날이 없습니다."; return; }
      renderChips();
      renderDay(d.days[0]);
      try { initMap(); } catch (e) { $("map").textContent = "지도를 불러오지 못했습니다."; }
      highlightVenues(d.days[0]);
    })
    .catch(() => { $("day").textContent = "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."; });
})();
