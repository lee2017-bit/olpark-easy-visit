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
  const KIND = { warn: ["alert", "주의"], tip: ["info", "도움말"], gap: ["question", "공개 자료 없음"], ok: ["check", "이상 표시 없음"] };
  const FIRST = 10;
  const LABEL_SIDE = { kspo_dome: "right", lawn88: "left", woori_art_hall: "left" };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 못 해도 화면엔 적용 */ } },
  };
  const state = { d: null, sel: 0, showAll: false, venue: "all", open: new Set(), map: null, venueMarkers: {} };
  // 실시간 확인 결과: null = 불러오는 중, { ok: false } = 실패
  const chk = { notices: null, status: null };

  const md = (date) => { const [, m, d] = date.split("-"); return { m: +m, d: +d }; };
  const km = (a, b) => {
    const r = Math.PI / 180, la1 = a.lat * r, la2 = b.lat * r;
    const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  };
  const forWho = (k) => (it) => !it.who || !it.who.length || it.who.includes(k);

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

  // 제목 한 줄만 보이고, 설명·출처는 눌러야 보인다 (처음 화면 글자 수를 줄이려고)
  function itemLi(it, showVenue, shortOf) {
    const [ic, label] = KIND[it.kind] || ["check", null];
    const vtag = showVenue && it.venue ? el("span", { class: "vtag" }, shortOf[it.venue] || it.venue) : null;
    const head = [el("span", { class: "bub" }, icon(ic)), el("b", {}, it.t), vtag];
    const li = el("li", { class: "item" + (it.kind ? " k-" + it.kind : "") });
    if (!it.s && !it.src) { li.append(el("div", { class: "item-row" }, ...head)); return li; }
    const meta = el("span", { class: "meta" });
    if (label) meta.append(el("span", { class: "kind" }, label));
    const b = srcBadge(it);
    if (b) meta.append(b);
    li.append(el("details", { class: "item-more" }, el("summary", { class: "item-row" }, ...head),
      el("div", { class: "item-body" }, it.s ? el("span", { class: "s" }, it.s) : null, meta)));
    return li;
  }

  // ---------- 실시간 확인 1: 올림픽공원 공지(공사·통제) ----------
  // 공원 홈페이지도 Access-Control-Allow-Origin: * 라서 브라우저에서 바로 읽는다.
  const NOTICE_VIEW = (no) => `https://www.ksponco.or.kr/olympicpark/board.es?mid=a20601000000&bid=0045&list_no=${no}&act=view`;
  const pad2 = (n) => String(n).padStart(2, "0");

  function ymd(s, baseY) {
    let m = s.match(/(\d{4})\s*[.\-년]\s*(\d{1,2})\s*[.\-월]?\s*(?:(\d{1,2})\s*[.일]?)?/);
    if (m) return { y: +m[1], mo: +m[2], d: m[3] ? +m[3] : null };
    if (!baseY) return null;
    m = s.match(/(\d{1,2})\s*[.\-월]\s*(\d{1,2})/);
    if (m) return { y: baseY, mo: +m[1], d: +m[2] };
    m = s.match(/(\d{1,2})\s*월/);
    return m ? { y: baseY, mo: +m[1], d: null } : null;
  }
  function period(txt) {
    const [a, b] = txt.split(/~|∼|부터/);
    const f = ymd(a || "");
    if (!f) return null;
    const t = b ? ymd(b, f.y) : null;
    if (t && !/\d{4}/.test(b) && t.mo < f.mo) t.y = f.y + 1;
    const iso = (x, end) => `${x.y}-${pad2(x.mo)}-${pad2(x.d || (end ? new Date(x.y, x.mo, 0).getDate() : 1))}`;
    return { from: iso(f, false), to: t ? iso(t, true) : null };
  }
  // 공지 본문 → 공사별 {이름, 위치, 기간, 통제구간}. 형식이 달라 못 읽으면 segs가 비고, 공지 제목·링크만 보여 준다.
  function parseNotice(text) {
    const t = text.replace(/\s+/g, " ")
      .replace(/(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?/g, "$1-$2-$3")
      .replace(/~\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?/g, "~ $1-$2");
    const segs = [];
    for (const part of t.split(/\s\d{1,2}\.\s+(?=[가-힣A-Za-z])/)) {
      const per = part.match(/공사\s*기간\s*[:：]?\s*(.+?)(?=ㅇ|○|※|공사\s*내용|통제|안내\s*사항|문의|\(|$)/);
      const pr = per && period(per[1]);
      if (!pr) continue;
      const grab = (re) => ((part.match(re) || [])[1] || "").trim();
      segs.push({
        name: grab(/공사명\s*[:：]\s*(.+?)(?=공사\s*기간|공사\s*내용|$)/) || grab(/^\s*(.+?)(?=ㅇ|○|공사\s*위치|$)/),
        where: grab(/공사\s*위치\s*[:：]\s*(.+?)(?=ㅇ|○|공사\s*내용|공사\s*기간|$)/),
        ctrl: grab(/통제\s*구간\s*[:：]\s*(.+?)(?=ㅇ|○|$)/),
        ...pr,
      });
    }
    const dates = [...t.matchAll(/(\d{4})-(\d{1,2})-(\d{1,2})/g)].map((m) => `${m[1]}-${pad2(m[2])}-${pad2(m[3])}`);
    return { segs, last: dates.sort().pop() || null, text: t };
  }

  async function loadNotices() {
    const cfg = state.d.live;
    try {
      const res = await fetch(cfg.notice_board, { cache: "no-store", credentials: "omit" });
      if (!res.ok) throw new Error(res.status);
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      const kw = new RegExp(cfg.notice_keywords);
      const list = [];
      for (const li of doc.querySelectorAll("li.list_li")) {
        const a = li.querySelector("a[href*='list_no=']");
        const ttl = li.querySelector("strong.title span") || li.querySelector("strong.title");
        const no = a && (a.getAttribute("href").match(/list_no=(\d+)/) || [])[1];
        const posted = (li.textContent.match(/\d{4}-\d\d-\d\d/) || [])[0];
        const title = ttl ? ttl.textContent.replace(/\s+/g, " ").replace(/^Notice\s*/, "").trim() : "";
        if (no && title && kw.test(title) && !list.some((x) => x.no === no)) list.push({ no, title, posted, url: NOTICE_VIEW(no) });
      }
      await Promise.all(list.slice(0, 6).map(async (n) => {
        try {
          const r = await fetch(n.url, { cache: "no-store", credentials: "omit" });
          const vd = new DOMParser().parseFromString(await r.text(), "text/html");
          const box = vd.querySelector(".view_cont");
          const alts = box ? [...box.querySelectorAll("img[alt]")].map((i) => i.getAttribute("alt")).join(" ") : "";
          Object.assign(n, parseNotice(alts + " " + (box ? box.textContent : "")));
        } catch (e) { n.segs = []; n.failed = true; }
      }));
      chk.notices = { ok: true, items: list.slice(0, 6), at: new Date() };
    } catch (e) {
      chk.notices = { ok: false };
    }
    rerender();
  }

  // 그날 해당하는 공사: 기간이 그날을 포함하면. 기간을 못 읽었으면 공지일 30일 안이거나 본문 마지막 날짜가 그날 뒤면 '확인 필요'로.
  function noticesFor(day) {
    if (!chk.notices || !chk.notices.ok) return [];
    const out = [];
    for (const n of chk.notices.items) {
      if (n.segs && n.segs.length) {
        const segs = n.segs.filter((g) => g.from <= day.date && (!g.to || day.date <= g.to));
        if (segs.length) out.push({ n, segs });
      } else if ((n.last && n.last >= day.date) || (n.posted && n.posted <= day.date && (Date.parse(day.date) - Date.parse(n.posted)) / 864e5 <= 30)) {
        out.push({ n, segs: [], unsure: true });
      }
    }
    return out;
  }
  // 공사 하나(seg) 또는 기간을 못 읽은 공지 전체 글에서, 그날 공연장 이름이 나오는지
  const segText = (g) => [g.name, g.where, g.ctrl].join(" ");
  function venueHit(txt, day) {
    const alias = state.d.live.venue_alias;
    const keys = [...new Set(day.shows.map((s) => s.venue_key))].filter((k) => state.venue === "all" || k === state.venue);
    return keys.filter((k) => (alias[k] || []).some((a) => txt.includes(a)));
  }
  const hitTexts = (h) => (h.segs.length ? h.segs.map(segText) : [h.n.title + " " + (h.n.text || "")]);

  // ---------- 실시간 확인 2: 지하철 엘리베이터 (GitHub Actions가 10분마다 확인해 둔 파일) ----------
  async function loadStatus() {
    try {
      const res = await fetch(state.d.live.status_url, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const data = await res.json();
      chk.status = { ok: !!data.ok, data, at: new Date(data.checked_at) };
    } catch (e) {
      chk.status = { ok: false };
    }
    rerender();
  }
  setInterval(() => { if (!document.hidden && state.d) loadStatus(); }, 10 * 60 * 1000);

  function rerender() {
    if (!state.d || !state.d.days.length) return;
    renderToday();
    renderDay(state.d.days[state.sel]);
  }


  // ---------- 이 날 꼭 알아야 할 것 ----------
  // 날짜별 후보(day.key, 빌드할 때 만듦)에 지금 확인한 것(공연장 근처 공사·엘리베이터 중지·만차)을 더해 순위가 높은 3개만.
  const KEY_N = 3;
  const bannerIndex = () => state.d.days.findIndex((x) => x.date >= kstDate());
  const mmdd = (iso) => iso ? `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}` : "";

  function liveKey(day) {
    const out = [];
    const cfg = state.d.live;
    const isToday = kstDate() === day.date;
    if (chk.notices && chk.notices.ok) {
      const shortOf = Object.fromEntries(state.d.map.venues.map((v) => [v.key, v.short]));
      for (const h of noticesFor(day)) {
        for (const g of (h.segs.length ? h.segs : [null])) {
          const vs = venueHit(g ? segText(g) : hitTexts(h)[0], day);
          if (!vs.length) continue;
          out.push({ rank: 90, group: "construction", kind: "warn", who: [], src: "공식", url: h.n.url, venue: vs[0],
            t: `${vs.map((v) => shortOf[v] || v).join("·")} 주변 공사${g && g.to ? ` (~${mmdd(g.to)})` : ""}`,
            do: "막히면 02-410-1114",
            more: [g ? g.name || h.n.title : h.n.title, g && g.ctrl].filter(Boolean).join(" · ") + ". 평소 다니던 경사로·보도가 막힐 수 있어요. 막혔으면 현장 안내 요원이나 공원 대표전화로 물어보세요" });
        }
      }
    }
    const st = chk.status;
    if (isToday && st && st.ok && (Date.now() - st.at.getTime()) / 60000 <= cfg.stale_min) {
      for (const e of st.data.elevators.filter((x) => x.state === "stop")) {
        const name = `${e.line} ${e.station}`;
        out.push({ rank: 95, group: `elev:${name}:${e.kind}`, kind: "warn", who: ["wheel", "stroller", "slow"], src: "공공데이터",
          url: st.data.source.url,
          t: `${e.line} ${e.station}역 ${e.kind === "exit" ? e.exit + "번 출구" : "역 안"} 엘리베이터 중지`,
          do: (cfg.fallback_short || {})[`${name} ${e.kind}`] || "역무실에 도움 요청",
          more: `${e.line} · ${hm(st.at)} 서울교통공사 자료. ` + (cfg.fallback[`${name} ${e.kind}`] || "") });
      }
    }
    if (isToday && live.last && live.last.r.parked / live.last.r.cap * 100 >= FULL_PCT) {
      const r = live.last.r;
      out.push({ rank: 85, group: "full", kind: "warn", who: [], src: "공식", url: PARKING_URL,
        t: "지금 주차장 만차",
        do: "지하철·콜택시로",
        more: `${fmt(r.parked)}대 / ${fmt(r.cap)}대 (${kstTime(live.last.at)}). 장애인 주차구역 빈자리는 따로 공개되지 않아요` });
    }
    return out;
  }

  function keyFoot(day) {
    const isToday = kstDate() === day.date;
    const n = chk.notices, st = chk.status;
    const bad = [];
    const parts = [];
    if (n === null) parts.push("공사 공지 확인 중");
    else if (!n.ok) bad.push("공사 공지를 못 불러왔어요");
    else parts.push(`공사 공지 ${hm(n.at)}`);
    if (isToday) {
      if (st === null) parts.push("엘리베이터 확인 중");
      else if (!st.ok) bad.push("엘리베이터 상태를 못 불러왔어요");
      else if ((Date.now() - st.at.getTime()) / 60000 > state.d.live.stale_min) bad.push(`엘리베이터 정보가 ${hm(st.at)} 뒤로 안 바뀜`);
      else parts.push(`엘리베이터 ${hm(st.at)}`);
    }
    const f = el("p", { class: "key-foot" + (bad.length ? " bad" : "") });
    if (bad.length) f.append(icon("alert", "ic sm"), el("span", {}, bad.join(" · ")));
    else if (parts.length) f.append(el("span", {}, parts.join(" · ") + " 확인"));
    return f;
  }

  function keyBox(day, venue) {
    const today = kstDate();
    const cands = [...(day.key || []), ...liveKey(day)]
      .filter((k) => !(k.when === "before" && day.date <= today))
      .filter((k) => !venue || venue === "all" || !k.venue || k.venue === venue)
      .sort((a, b) => b.rank - a.rank);
    const seen = new Set(), top = [];
    for (const k of cands) {
      if (seen.has(k.group)) continue;
      seen.add(k.group);
      top.push(k);
      if (top.length === KEY_N) break;
    }
    if (!top.length) return null;
    const ol = el("ol", { class: "key-list" });
    top.forEach((k, i) => {
      const who = k.who && k.who.length ? k.who.map((w) => state.d.who[w]).join("·") : "모두";
      ol.append(el("li", { class: "key-item k-" + (k.kind || "tip") },
        el("details", {},
          el("summary", {}, el("span", { class: "key-n", "aria-hidden": "true" }, String(i + 1)),
            el("span", { class: "key-txt" }, el("b", { class: "key-t" }, k.t), k.do ? el("span", { class: "key-do" }, k.do) : null)),
          el("div", { class: "key-more" }, k.more ? el("p", {}, k.more) : null,
            el("span", { class: "meta" }, el("span", { class: "key-who" }, who), srcBadge(k))))));
    });
    const head = (day.date === today ? "오늘" : "이 날") + ` 꼭 알 것 ${top.length}가지`;
    return el("div", { class: "key" }, el("h3", { class: "key-h" }, head), ol, keyFoot(day));
  }


  // 공연 카드: 포스터(기관 홈페이지 이미지를 줄인 것) + 공연장·시각. 누르면 기관 공연 페이지
  function showCard(s, big) {
    const when = s.start ? `${s.start}` : "시간 미정";
    const pic = s.poster
      ? el("img", { src: s.poster, alt: `${s.title} 포스터`, loading: big ? "eager" : "lazy", width: "120", height: "170" })
      : el("span", { class: "poster-none", "aria-hidden": "true" }, icon("stage"));
    return el("a", { class: "show" + (big ? " big" : ""), href: s.page || s.link || "#", rel: "noopener", target: "_blank" },
      pic, el("span", { class: "show-v" }, s.venue), el("span", { class: "show-w" }, when), el("span", { class: "show-t" }, s.title));
  }

  // ---------- 오늘 공연 ----------
  function renderToday() {
    const box = $("today");
    if (!box) return;
    box.textContent = "";
    const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date());
    const days = state.d.days;
    const i = days.findIndex((x) => x.date >= today);
    if (i < 0) { box.append(el("p", {}, "앞으로 60일 안에 공연이 없어요.")); return; }
    const day = days[i];
    const { m, d } = md(day.date);
    const isToday = day.date === today;
    box.append(el("p", { class: "today-when" }, isToday ? `오늘 ${m}/${d}(${day.weekday})` : `다음 공연 ${m}/${d}(${day.weekday})`));
    const row = el("div", { class: "shows-row" });
    for (const s of day.shows) row.append(showCard(s, true));
    box.append(row);
    const v0 = state.venue;
    state.venue = "all"; // 맨 위는 그날 모든 공연장 기준
    const kb = keyBox(day, "all");
    state.venue = v0;
    if (kb) box.append(kb);
    const go = el("button", { type: "button", class: "live-btn" }, "유형별 자세히 ↓");
    go.addEventListener("click", () => { if (i !== state.sel) select(i); $("day").scrollIntoView({ behavior: "smooth", block: "start" }); });
    box.append(go);
  }

  // ---------- 선택한 날 ----------
  const hm = (t) => kstTime(t);
  function elevSummary(day, k) {
    // 휠체어·유모차·천천히 걷는 분에게만: 역별 엘리베이터 상태 + 멈췄으면 대처
    const out = [];
    const st = chk.status;
    const today = kstDate() === day.date;
    const cfg = state.d.live;
    if (st === null) { out.push({ kind: "tip", t: "엘리베이터 확인 중…" }); return out; }
    if (!st.ok) {
      out.push({ kind: "warn", t: "엘리베이터 상태를 못 불러왔어요", s: "또타지하철 앱의 승강기 고장 알림이나 역에 직접 확인하세요.", src: "공식", url: "https://mediahub.seoul.go.kr/archives/2003952" });
      return out;
    }
    const ageMin = (Date.now() - st.at.getTime()) / 60000;
    const when = `서울교통공사 자료 ${hm(st.at)}에 불러옴` + (today ? "" : " · 가는 날 다시 확인하세요");
    const groups = {};
    for (const e of st.data.elevators) (groups[`${e.line} ${e.station}`] ||= []).push(e);
    for (const [name, es] of Object.entries(groups)) {
      const exits = es.filter((e) => e.kind === "exit"), inside = es.filter((e) => e.kind === "inside");
      const stop = es.filter((e) => e.state !== "ok");
      const parts = [
        ...exits.map((e) => `${e.exit}번 출구 지상 엘리베이터 ${e.state === "ok" ? "운행 중으로 표시" : e.state === "stop" ? "중지로 표시" : "상태 불명"}`),
        inside.length ? `역 안 엘리베이터 ${inside.length}대 중 ${inside.filter((e) => e.state === "ok").length}대 운행 중으로 표시` : null,
      ].filter(Boolean).join(" · ");
      const nm = name;
      if (!stop.length) {
        // 자료상 정상이어도 고장이 늦게 반영될 수 있으니, 가서 멈춰 있을 때 갈 길을 늘 함께 보여 준다
        const fb = exits.length ? cfg.fallback[`${name} exit`] : "";
        out.push({ kind: "ok", t: `${nm}역 엘리베이터 ${es.length}대 정상 표시`, s: [parts, when, fb].filter(Boolean).join(" · "), src: "공공데이터", url: st.data.source.url });
      } else {
        const fb = [...new Set(stop.map((e) => cfg.fallback[`${name} ${e.kind}`]).filter(Boolean))].join(" ");
        const where = stop.map((e) => (e.kind === "exit" ? `${e.exit}번 출구` : "역 안")).join("·");
        out.push({ kind: "warn", t: `${nm}역 ${where} 엘리베이터 중지 표시`, s: [parts, fb, when].filter(Boolean).join(" · "), src: "공공데이터", url: st.data.source.url });
      }
    }
    out.push({ kind: "gap", t: "고장 반영까지 걸리는 시간은 비공개", s: cfg.elev_lag });
    out.push({ kind: "gap", t: "9호선은 실시간 정보 없음", s: st.data.not_covered });
    if (ageMin > cfg.stale_min) out.unshift({ kind: "warn", t: `엘리베이터 정보가 ${hm(st.at)} 뒤로 안 바뀜`, s: "갱신이 늦어지고 있어요. 또타지하철 앱이나 역에 직접 확인하세요." });
    return out;
  }

  function constructionFor(day, k) {
    const out = [];
    const cfg = state.d.live;
    if (chk.notices === null) { out.push({ kind: "tip", t: "공사 공지 확인 중…" }); return out; }
    if (!chk.notices.ok) {
      out.push({ kind: "warn", t: "공사 공지를 못 불러왔어요", s: "올팍소식 공지를 직접 확인하세요.", src: "공식", url: cfg.notice_board });
      return out;
    }
    const hits = noticesFor(day);
    if (!hits.length) {
      out.push({ kind: "ok", t: "이 날 공사·통제 공지 없음", s: `올팍소식 ${hm(chk.notices.at)} 확인 · 공지에 없는 긴급 통제는 알 수 없어요`, src: "공식", url: cfg.notice_board });
      return out;
    }
    const shortOf = Object.fromEntries(state.d.map.venues.map((v) => [v.key, v.short]));
    const head = (txt) => {
      const vs = venueHit(txt, day);
      return vs.length ? `${vs.map((v) => shortOf[v] || v).join("·")} 주변 공사` : "공원 공사";
    };
    const rows = [];
    for (const h of hits) {
      if (h.segs.length) {
        for (const g of h.segs) {
          const near = venueHit(segText(g), day).length;
          rows.push({ near, it: { kind: near ? "warn" : "tip", t: head(segText(g)) + (g.to ? ` (~${mmdd(g.to)})` : ""),
            s: [g.name || h.n.title, g.where && `위치: ${g.where}`, `기간: ${g.from} ~ ${g.to || "공지 확인"}`, g.ctrl && `통제: ${g.ctrl}`].filter(Boolean).join(" · "),
            src: "공식", url: h.n.url } });
        }
      } else {
        const txt = hitTexts(h)[0];
        rows.push({ near: venueHit(txt, day).length, it: { kind: "warn", t: head(txt),
          s: h.n.title + " · 기간·위치는 공지에서 확인하세요" + (h.n.posted ? ` (공지 ${h.n.posted})` : ""), src: "공식", url: h.n.url } });
      }
    }
    // 공연장 근처는 하나씩, 나머지 공원 공사는 한 줄로 묶음
    rows.filter((r) => r.near).forEach((r) => out.push(r.it));
    const far = rows.filter((r) => !r.near);
    if (far.length === 1) out.push(far[0].it);
    else if (far.length) out.push({ kind: "tip", t: `공원 다른 곳 공사 ${far.length}건`, s: far.map((r) => r.it.s).join(" / "),
      src: "공식", url: cfg.notice_board });
    if (k && cfg.construction_by_who[k]) out.push({ kind: "tip", ...cfg.construction_by_who[k] });
    return out;
  }

  function liveItems(day, k) {
    const items = [...constructionFor(day, k)];
    if (["wheel", "stroller", "slow"].includes(k)) items.push(...elevSummary(day, k));
    if (["wheel", "stroller", "slow", "vision"].includes(k)) {
      const warn = items.some((it) => it.kind === "warn");
      for (const h of state.d.live.help) items.push({ ...h, kind: warn ? "tip" : null });
    }
    return items;
  }

  function renderDay(day) {
    const box = $("day");
    box.textContent = "";
    const { m, d } = md(day.date);
    const p = el("article", { class: "panel" });
    p.append(el("div", { class: "panel-head" + (day.offday ? " off" : "") },
      el("span", { class: "panel-date" }, `${m}월 ${d}일 (${day.weekday})${day.holiday ? " 공휴일" : ""}`),
      el("span", { class: "count" }, `공연 ${day.shows.length}개`)));

    if (state.sel !== bannerIndex()) {
      const row = el("div", { class: "shows-row in-panel", "aria-label": "이날 공연" });
      for (const s of day.shows) row.append(showCard(s, false));
      p.append(row);
    }

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

    // 맨 위 「오늘 공연」과 다른 날을 골랐으면 그날의 꼭 알 것을 여기에
    if (state.sel !== bannerIndex()) {
      const kb = keyBox(day, state.venue);
      if (kb) p.append(kb);
    }


    const showVenue = vkeys.length > 1 && state.venue === "all";
    const cases = el("div", { class: "cases" },
      el("h3", { class: "cases-h" }, "누구와 가세요?"));
    for (const [k, label] of Object.entries(state.d.who)) {
      const f = forWho(k);
      const live = liveItems(day, k);
      let warnN = live.filter((it) => it.kind === "warn").length;
      const body = el("div", { class: "case-body" });
      if (live.length) {
        const list = el("ul", { class: "items" });
        live.forEach((it) => list.append(itemLi(it, false, shortOf)));
        body.append(el("section", { class: "step live-step" }, el("h3", {}, el("span", { class: "num" }, "!"), icon("check"), "지금 상황"), list));
      }
      state.d.steps.forEach((st, n) => {
        const dyn = (day.items[st.key] || []).filter((it) => state.venue === "all" || !it.venue || it.venue === state.venue);
        const items = [...dyn, ...st.items].filter(f);
        if (!items.length) return;
        warnN += items.filter((it) => it.kind === "warn").length;
        const sec = el("section", { class: "step", "aria-labelledby": `st-${k}-${st.key}` },
          el("h3", { id: `st-${k}-${st.key}` }, el("span", { class: "num" }, String(n + 1)), icon(st.icon), st.title));
        const list = el("ul", { class: "items" });
        // 주의 → 그날 안내 → 늘 같은 안내 순서. 집에 갈 때는 시간 순서 그대로
        const order = (it) => (st.key === "home" ? 0 : it.kind === "warn" ? 0 : it.kind === "gap" ? 3 : 1);
        items.map((it, i) => [it, i]).sort((a, b) => order(a[0]) - order(b[0]) || a[1] - b[1])
          .forEach(([it]) => list.append(itemLi(it, showVenue, shortOf)));
        sec.append(list);
        body.append(sec);
      });
      const det = el("details", { class: "case", "data-who": k },
        el("summary", {}, el("span", { class: "case-ic" }, icon(WHO_ICON[k] || "info")),
          el("span", { class: "case-name" }, label),
          el("span", { class: "case-n" }, warnN ? `주의 ${warnN}` : ""),
          el("span", { class: "case-open", "aria-hidden": "true" })),
        body);
      if (state.open.has(k)) det.open = true;
      det.addEventListener("toggle", () => { if (det.open) state.open.add(k); else state.open.delete(k); });
      cases.append(det);
    }
    p.append(cases);
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

  // ---------- 지금 주차장: 기관 홈페이지를 브라우저에서 바로 읽음 ----------
  // 기관 페이지가 Access-Control-Allow-Origin: * 를 보내므로 서버 없이 읽을 수 있다.
  // 숫자는 고치지 않고 그대로 보여 준다. 만차 90%·혼잡 70%·다소혼잡 50%는 기관 범례.
  const PARKING_URL = "https://www.ksponco.or.kr/online/main/parking.do";
  const LIVE_EVERY = 5 * 60 * 1000;
  const FULL_PCT = 90;
  const live = { tried: 0, last: null, busy: false };
  const fmt = (n) => n.toLocaleString("ko-KR");
  const kstDate = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date());
  const kstTime = (t) => new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false }).format(t);
  const level = (p) => p >= 90 ? ["high", "만차"] : p >= 70 ? ["mid", "혼잡"] : p >= 50 ? ["mid", "다소 혼잡"] : ["low", "여유"];

  function parseParking(html) {
    const doc = new DOMParser().parseFromString(html, "text/html"); // 주석 속 견본 행은 요소가 아니라 자동으로 빠짐
    const h = [...doc.querySelectorAll("h4")].find((x) => x.textContent.includes("실시간 주차대수"));
    const m = h && h.textContent.replace(/\s+/g, " ").match(/실시간 주차대수\s*\(([^)]*)\)\s*:\s*([\d,]+)\s*대.*?([\d,]+)\s*대\s*가능/);
    if (!m) return null;
    const preds = [];
    for (const tr of doc.querySelectorAll("table.parking_prediction tbody tr")) {
      const th = tr.querySelector("th"), td = tr.querySelector("td");
      const a = th && th.textContent.replace(/\s+/g, " ").match(/(\d{4}-\d\d-\d\d) (\d\d:\d\d)/);
      const p = td && td.textContent.match(/(\d+)\s*%/);
      if (a && p) preds.push({ date: a[1], time: a[2], pct: +p[1] });
    }
    return { lots: m[1].trim(), parked: +m[2].replace(/,/g, ""), cap: +m[3].replace(/,/g, ""), preds };
  }

  // 같은 값이 이어지는 시간대는 묶어서 "16:00~20:00 89%"
  function predRuns(preds) {
    const out = [];
    for (const p of preds) {
      const last = out[out.length - 1];
      if (last && last.pct === p.pct) last.to = p.time; else out.push({ from: p.time, to: p.time, pct: p.pct });
    }
    return out.map((r) => (r.from === r.to ? r.from : r.from + "~" + r.to) + " " + r.pct + "%").join(", ");
  }

  function renderLive(r, at, stale) {
    const box = $("live-box");
    box.textContent = "";
    const agencyLink = el("a", { href: PARKING_URL, rel: "noopener" }, "기관 페이지");
    if (!r) {
      box.append(el("p", {}, "기관 홈페이지에서 실시간 주차대수를 불러오지 못했어요. ",
        el("a", { href: PARKING_URL, rel: "noopener" }, "기관 실시간 주차대수 보기")));
      return;
    }
    const pct = r.cap ? Math.round(r.parked / r.cap * 1000) / 10 : 0;
    const [cls, word] = level(pct);
    const full = Math.round(r.cap * FULL_PCT / 100);
    box.append(el("p", { class: "live-top" },
      el("span", { class: "live-num" }, el("b", {}, fmt(r.parked)), "대"),
      el("span", { class: "live-cap" }, " / " + fmt(r.cap) + "대"),
      el("span", { class: "live-lvl lvl-" + cls }, word + " " + pct + "%")));
    const bar = el("div", { class: "live-bar", role: "img",
      "aria-label": fmt(r.cap) + "대 중 " + fmt(r.parked) + "대, " + pct + "%. 만차 기준 " + FULL_PCT + "%" });
    const fill = el("span", { class: "fill lvl-" + cls });
    fill.style.width = Math.min(100, pct) + "%";
    const mark = el("span", { class: "mark", "aria-hidden": "true" });
    mark.style.left = FULL_PCT + "%";
    bar.append(fill, mark);
    box.append(bar);
    const left = full - r.parked;
    box.append(el("p", { class: "live-left" }, left > 0 ? `만차까지 ${fmt(left)}대` : "만차"));
    const today = r.preds.filter((p) => p.date === kstDate());
    if (today.length) box.append(el("p", { class: "live-pred" }, "기관 예상 " + predRuns(today)));
    const again = el("button", { type: "button", class: "live-btn sm", "aria-label": "주차대수 새로 고침" }, "새로 고침");
    again.addEventListener("click", () => loadLive(true));
    box.append(el("p", { class: "small live-meta" }, kstTime(at) + " · " + r.lots + " ", again));
    if (stale) box.append(el("p", { class: "live-stale" }, "새로 고치지 못했어요 (" + kstTime(at) + " 기준)"));
    box.append(el("details", { class: "live-about" }, el("summary", {}, "숫자 설명"),
      el("p", { class: "small" }, "기관 홈페이지 숫자 그대로예요. 만차 기준 " + FULL_PCT + "%(" + fmt(full) + "대)는 기관 범례. " +
        "새벽에도 약 1,000대로 나와 실제보다 많게 집계될 수 있어요. 장애인 주차구역 빈자리는 공개되지 않아요. 5분마다 새로 고쳐요. ", agencyLink)));
  }

  async function loadLive(force) {
    if (live.busy || (!force && Date.now() - live.tried < LIVE_EVERY - 5000)) return;
    live.busy = true;
    live.tried = Date.now();
    try {
      const res = await fetch(PARKING_URL, { cache: "no-store", credentials: "omit" });
      if (!res.ok) throw new Error(res.status);
      const r = parseParking(await res.text());
      if (!r) throw new Error("parse");
      live.last = { r, at: new Date() };
      renderLive(r, live.last.at);
      if (state.d) renderToday(); // 만차가 되면 맨 위 「꼭 알아야 할 것」에도 반영
    } catch (e) {
      if (live.last) renderLive(live.last.r, live.last.at, true); else renderLive(null);
    } finally {
      live.busy = false;
    }
  }
  loadLive(true);
  setInterval(() => { if (!document.hidden) loadLive(false); }, 30 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadLive(false); });

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
      renderToday();
      if (!d.days.length) { $("day").textContent = "앞으로 60일 안에 공연이 없습니다."; return; }
      renderChips();
      renderDay(d.days[0]);
      try { initMap(); } catch (e) { $("map").textContent = "지도를 불러오지 못했습니다."; }
      highlightVenues(d.days[0]);
      loadNotices();
      loadStatus();
    })
    .catch(() => { $("day").textContent = "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."; });
})();
