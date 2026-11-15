(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs = {}, text) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };

  function renderDays(d) {
    const list = $("day-list");
    list.textContent = "";
    const s = d.stats;
    $("days-summary").textContent =
      `2025년 기록에서 공연 있는 주말·공휴일 만차는 대개 ${Math.round(s.first_full_h_median)}시 전후에 시작했고, ` +
      `${Math.round(s.share_full_before_show * 100)}%는 공연 시작 전에 찼습니다. 자가용보다 지하철을 권합니다.`;
    if (!d.days.length) { list.append(el("li", {}, "표시할 날이 없습니다.")); return; }
    for (const day of d.days) {
      const li = el("li", { class: "day" });
      const head = el("div", { class: "day-head" });
      const md = day.date.slice(5).replace("-", "월 ").replace(/^0/, "") + "일";
      head.append(el("span", { class: "date" }, `${md} (${day.weekday})${day.holiday ? " 공휴일" : ""}`));
      head.append(el("span", { class: `badge g-${day.grade}` }, `만차 위험 ${day.grade}`));
      if (day.rain_pop != null) head.append(el("span", { class: "small" }, `강수확률 ${day.rain_pop}%`));
      li.append(head);
      if (day.events.length) {
        const ul = el("ul", { class: "events" });
        for (const e of day.events) ul.append(el("li", {}, `${e.venue}${e.start ? " " + e.start : ""} · ${e.title}`));
        li.append(ul);
      } else {
        li.append(el("p", { class: "basis" }, "대형 공연장 공연 없음"));
      }
      li.append(el("p", { class: "basis" }, "근거: " + day.basis));
      if (day.tips && day.tips.length) {
        const det = el("details", { class: "tips" });
        det.append(el("summary", {}, "교통약자 안내 보기"));
        const tl = el("ul");
        for (const t of day.tips) tl.append(el("li", {}, t));
        det.append(tl);
        li.append(det);
      }
      list.append(li);
    }
  }

  function renderAccess(a) {
    const ul = $("elevators");
    for (const e of a.subway_elevators) {
      ul.append(el("li", {}, `${e.line} ${e.station}역: ${/^\d+$/.test(e.exit) ? e.exit + "번 출구" : e.where}`));
    }
    ul.append(el("li", { class: "small" }, a.subway_note));
    $("exit-warn").textContent =
      `공원 「오시는 길」은 "${a.park_exit_guidance}"로 안내합니다. 엘리베이터가 없는 출구일 수 있으니 휠체어·유모차 이용 시 위 엘리베이터 출구를 확인하세요.`;

    const tb = document.querySelector("#venues tbody");
    for (const [name, v] of Object.entries(a.venues)) {
      const tr = el("tr");
      tr.append(el("th", { scope: "row" }, name));
      tr.append(el("td", {}, `${v.lot} · ${v.walk}`));
      tr.append(el("td", {}, v.disabled_spaces == null ? "지정 구역 안내 없음" : `${v.disabled_spaces}면`));
      tb.append(tr);
    }
    $("parking-note").textContent =
      `장애인 주차면은 출처마다 다릅니다: 기관 공지 합계 ${a.disabled_parking_total_agency}면, 한국관광공사 무장애 정보 "${a.disabled_parking_knto}". ` +
      `공연일에는 일반 구역이 먼저 차면서 장애인 구역 진입도 어려워질 수 있습니다.`;

    const r = a.wheelchair_rental;
    const places = Object.entries(r.places).map(([k, v]) => `${k} ${v}대`).join(", ");
    $("rental").textContent = `휠체어: ${places} (${r.hours}, ${r.rule}). 유모차: ${a.stroller_knto || "안내센터 문의"}.`;
    $("rental-warn").textContent = "대여는 19시에 끝나고 한 번에 3시간까지라, 저녁 공연을 보는 동안에는 쓰기 어렵습니다. 공연 관람 시에는 개인 휠체어를 권합니다.";
    $("entry").textContent = a.wheelchair_entry_route;
  }

  function renderFooter(d) {
    $("generated").textContent = d.generated_at + " (KST)";
    const ul = $("sources");
    for (const s of d.sources) {
      const li = el("li");
      li.append(el("a", { href: s.url, rel: "noopener" }, s.name));
      ul.append(li);
    }
  }

  fetch("data/site.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { renderDays(d); renderAccess(d.access); renderFooter(d); })
    .catch(() => { $("day-list").textContent = "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."; });
})();
