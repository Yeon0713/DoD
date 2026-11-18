// 도나 개발자 대시보드 화면 동작.
// 탭마다 render 함수 하나가 서버 /api/dev_tools/... 를 불러 그린다. 라이브러리 없이 HTML 글자로 그린다.
// 서버 글(리뷰, 가게 이름 등)은 모두 esc() 로 감싸서 HTML 로 해석되지 않게 한다.

const API = "/api/dev_tools";
const state = { tab: "status", storeId: null, usageDays: 30 };
// 예전 탭 주소(#overview, #system, #usage, #quality)도 합친 탭으로 연다
const TAB_ALIAS = { overview: "status", system: "status", usage: "ai", quality: "ai" };
const content = document.getElementById("content");

// ── 도우미 ──

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const won = (n) => `₩${Math.round(n ?? 0).toLocaleString("ko-KR")}`;
const num = (n) => (n ?? 0).toLocaleString("ko-KR");
const time = (iso) => (iso ? iso.replace("T", " ").slice(5, 16) : "-");
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "content-type": "application/json" }, ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body?.error?.message ?? `요청 실패 (${res.status})`);
  return body;
}

function toast(text) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

function stat(label, value, hint = "", brand = false) {
  return `<div class="stat"><div class="label">${esc(label)}</div><div class="value ${brand ? "brand" : ""}">${value}</div><div class="hint">${esc(hint)}</div></div>`;
}

function bars(rows, { valueText, color = "" } = {}) {
  if (!rows.length) return `<div class="empty">아직 없어요</div>`;
  const max = Math.max(...rows.map((r) => r.value), 1);
  return `<div class="bars">${rows
    .map(
      (r) => `<div class="bar-row"><span>${esc(r.label)}</span>
        <div class="bar-track"><div class="bar-fill ${color}" style="width:${(r.value / max) * 100}%"></div></div>
        <span class="bar-value">${esc(valueText ? valueText(r) : num(r.value))}</span></div>`,
    )
    .join("")}</div>`;
}

function columns(rows, { valueOf, labelOf, titleOf }) {
  if (!rows.length) return `<div class="empty">아직 없어요</div>`;
  const max = Math.max(...rows.map(valueOf), 1);
  const weekend = (r) => [0, 6].includes(new Date(`${r.date ?? r.day}T12:00:00+09:00`).getDay());
  return `<div class="columns">${rows
    .map((r) => `<div class="column ${weekend(r) ? "weekend" : ""}" style="height:${(valueOf(r) / max) * 100}%" title="${esc(titleOf(r))}"></div>`)
    .join("")}</div>
    <div class="column-labels">${rows.map((r) => `<span>${esc(labelOf(r))}</span>`).join("")}</div>`;
}

function table(headers, rows) {
  if (!rows.length) return `<div class="empty">아직 없어요</div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((cells) => `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

// ── 탭: 상태 (예전 개요 + 시스템) ──

async function renderStatus() {
  const [o, s] = await Promise.all([api(`${API}/overview`), api(`${API}/system`)]);
  const onOff = (v) => `<span class="dot ${v ? "on" : "off"}"></span>${v ? "켜짐" : "꺼짐"}`;
  const has = (v) => `<span class="dot ${v ? "on" : "off"}"></span>${v ? "있음" : "없음"}`;
  // 시연 단계는 시계를 과거로도 옮긴다 (예: -37시간). 부호를 그대로 보여 준다
  const hours = Math.round(s.clock_shift_minutes / 60);
  const shift = s.clock_shift_minutes ? ` (시계 ${hours > 0 ? "+" : ""}${hours}시간)` : "";
  return `
    <div class="stats">
      ${stat("총 매장", num(o.stores_total), `목업 ${o.stores_mock} · 등록 ${o.registered_stores}`, true)}
      ${stat("연결된 사장님 계정", num(o.owners), "네이버 로그인으로 가게를 등록한 계정")}
      ${stat("오늘 CLOVA 호출", num(o.clova_today.calls), `토큰 ${num(o.clova_today.input_tokens + o.clova_today.output_tokens)}`)}
      ${stat("이번 달 CLOVA 비용", o.price_set ? won(o.clova_month.cost_won) : "단가 미설정", o.price_set ? `이번 달 예상 ${won(o.clova_month.projected_cost_won)}` : ".env 에 CLOVA_PRICE_*_PER_1K 를 넣어 주세요")}
    </div>
    <div class="grid-2">
      <div class="card"><h2>서버</h2>
        ${table(["항목", "값"], [
          ["지금 서버 시각", `<span class="mono">${esc(time(s.now))}</span>${esc(shift)}`],
          ["계산해 둔 가게", `${o.computed_stores} / ${o.stores_total}곳`],
          ["boot_id (서버가 켜질 때마다 바뀜)", `<span class="mono small">${esc(s.boot_id)}</span>`],
        ])}
        <div class="control-actions" style="margin-top:12px"><button class="btn-outline small" id="health">헬스체크 실행</button><span id="health-result" class="muted small"></span></div>
      </div>
      <div class="card"><h2>업종 분포</h2>${bars(o.categories.map((c) => ({ label: c.name, value: c.count })), { valueText: (r) => `${r.value}곳` })}</div>
    </div>
    <div class="grid-2">
      <div class="card"><h2>설정 스위치 <span class="muted">server/.env</span></h2>
        ${table(["이름", "상태"], [
          ...Object.entries(s.switches).map(([k, v]) => [`<span class="mono small">${esc(k)}</span>`, onOff(v)]),
          ...Object.entries(s.values).map(([k, v]) => [`<span class="mono small">${esc(k)}</span>`, `<span class="mono">${esc(v)}</span>`]),
        ])}
      </div>
      <div class="card"><h2>API 키 <span class="muted">값은 보이지 않고 들어 있는지만</span></h2>
        ${table(["이름", "상태"], Object.entries(s.keys).map(([k, v]) => [`<span class="mono small">${esc(k)}</span>`, has(v)]))}
      </div>
    </div>
    <div class="grid-2">
      <div class="card"><h2>저장소</h2>${table(["무엇", "어디"], Object.entries(s.storage).map(([k, v]) => [esc(k), `<span class="small">${esc(v)}</span>`]))}</div>
      <div class="card"><h2>가게별 계산 <span class="muted">분석 + 계획 + 답글 초안</span></h2>
        ${table(["가게", "마지막 계산", "걸린 시간"], s.compute.map((c) => [
          `<span class="mono">${esc(c.store_id)}</span>`,
          c.computed_at ? `<span class="mono small">${esc(time(c.computed_at))}</span>` : '<span class="muted small">아직</span>',
          c.seconds != null ? `<span class="num">${c.seconds}초</span>` : "-",
        ]))}
      </div>
    </div>
    <div class="card"><h2>테스트 네이버 계정 <span class="muted">임시 네이버 로그인 화면에서 씀 (시험용 값)</span></h2>
      ${table(["아이디", "비밀번호", "가게", "로그인하면"], s.test_accounts.map((a) => [
        `<span class="mono">${esc(a.login_id)}</span>`, `<span class="mono">${esc(a.password)}</span>`,
        a.store ? `<span class="tag blue">${esc(a.store)}</span>` : '<span class="muted small">없음</span>', esc(a.scenario),
      ]))}
    </div>`;
}

// ── 탭: 매장 ──

async function renderStores() {
  const rows = await api(`${API}/stores`);
  return `<div class="card"><h2>매장 <span class="muted">${rows.length}곳 · 숫자는 지금 시각까지</span></h2>
    ${table(
      ["가게", "업종", "장사 시간", "주문", "리뷰", "메뉴", "알바", "마지막 계산", ""],
      rows.map((s) => [
        `<b>${esc(s.name)}</b><div class="muted small mono">${esc(s.store_id)}</div>`,
        `${esc(s.category)} ${s.kind === "registered" ? '<span class="tag blue">등록</span>' : '<span class="tag">목업</span>'}`,
        `${esc(s.hours)}${s.closed_weekdays.length ? `<div class="muted small">휴무 ${esc(s.closed_weekdays.join(", "))}</div>` : ""}${s.overnight ? '<div><span class="tag warn">자정 넘김 · 알림 계획 안 됨</span></div>' : ""}`,
        `<span class="num">${num(s.orders)}</span>`,
        `<span class="num">${num(s.reviews)}</span>`,
        `<span class="num">${num(s.menus)}</span>`,
        `<span class="num">${num(s.staff)}</span>`,
        s.computed_at ? `<span class="mono small">${esc(time(s.computed_at))}</span><div class="muted small">${s.compute_seconds ?? "-"}초</div>` : '<span class="muted small">아직</span>',
        `<button class="btn-outline small" data-pick="${esc(s.store_id)}">보기</button>`,
      ]),
    )}</div>`;
}

// ── 탭: 분석 ──

const DAYPART_KO = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤", MORNING: "아침" };

function heatColor(cell) {
  if (cell.signal === "HIGH") return `rgba(30, 158, 90, ${Math.min(0.25 + (cell.ratio - 1.15) * 1.5, 0.9)})`;
  if (cell.signal === "LOW") return `rgba(58, 111, 216, ${Math.min(0.25 + (0.85 - cell.ratio) * 1.5, 0.9)})`;
  return cell.reasons.length ? "#eaf4ee" : "#f3f3f5";
}

function heatmap(cells) {
  if (!cells.length) return `<div class="empty">달력이 없어요</div>`;
  const dates = [...new Set(cells.map((c) => c.date))];
  const parts = ["LUNCH", "DINNER", "NIGHT", "MORNING"].filter((p) => cells.some((c) => c.daypart === p));
  const byKey = new Map(cells.map((c) => [`${c.date}|${c.daypart}`, c]));
  const head = dates
    .map((d) => {
      const c = cells.find((x) => x.date === d);
      const weekend = ["토", "일"].includes(c.weekday);
      return `<div class="heat-head ${weekend ? "weekend" : ""}">${c.weekday}<br>${Number(d.slice(8))}</div>`;
    })
    .join("");
  const rows = parts
    .map(
      (p) =>
        `<div class="heat-label">${DAYPART_KO[p] ?? p}</div>` +
        dates
          .map((d) => {
            const c = byKey.get(`${d}|${p}`);
            if (!c) return `<div class="heat-cell" style="background:#fff"></div>`;
            const tip = `${d} ${DAYPART_KO[p]} · ${c.signal} ×${c.ratio} · 평소 ${won(c.baseline)} → 예상 ${won(c.expected)}\n${c.reason_text}`;
            return `<div class="heat-cell" style="background:${heatColor(c)}" title="${esc(tip)}">${c.signal === "HIGH" ? "▲" : c.signal === "LOW" ? "▼" : ""}</div>`;
          })
          .join(""),
    )
    .join("");
  return `<div class="table-wrap"><div class="heatmap" style="grid-template-columns: 44px repeat(${dates.length}, minmax(22px, 1fr)); min-width:${dates.length * 25 + 44}px">
    <div></div>${head}${rows}</div></div>
    <div class="legend"><span><i style="background:rgba(30,158,90,.6)"></i>바쁨 (평소보다 15%↑)</span><span><i style="background:rgba(58,111,216,.5)"></i>한산 (15%↓)</span><span><i style="background:#eaf4ee"></i>이유는 있지만 보통</span><span>칸에 마우스를 올리면 이유가 보여요</span></div>`;
}

/** 분석·알림 타임라인은 보관해 둔 계산을 보여 준다 (탭을 열 때 다시 계산하거나 CLOVA 를 부르지 않는다) */
function keptNote(computedAt) {
  return `<div class="card kept"><span class="muted">${esc(state.storeId)} · <span class="mono">${esc(time(computedAt))}</span> 에 계산해 둔 결과예요</span>
    <button class="btn-outline small" data-action="recompute">다시 계산</button></div>`;
}

async function renderAnalysis() {
  const a = await api(`${API}/analysis?store_id=${state.storeId}`);
  const rs = a.review_summary;
  const busy = a.calendar.filter((c) => c.signal === "HIGH");
  return `
    ${keptNote(a.computed_at)}
    <div class="card"><h2>35일 달력 <span class="muted">${esc(a.store.name)} · ${esc(time(a.computed_at))} 계산 · 바쁜 칸 ${busy.length}개</span></h2>${heatmap(a.calendar)}</div>
    <div class="card"><h2>지난 4주 하루 매출 <span class="muted">마감이 지난 날만 (태성 sales_daily)</span></h2>
      ${columns(a.daily_sales, {
        valueOf: (r) => r.sales,
        labelOf: (r) => Number(r.date.slice(8)),
        titleOf: (r) => `${r.date} 매출 ${won(r.sales)} · 인건비 ${won(r.labor)} · 남은 돈 ${won(r.profit)}`,
      })}
    </div>
    <div class="grid-2">
      <div class="card"><h2>리뷰 분류 <span class="muted">전체 ${num(rs.total)} · 불만 ${num(rs.quick)} · ${esc(Object.entries(rs.labeler).map(([k, v]) => `${k} ${v}`).join(", "))}</span></h2>
        ${bars(rs.complaints.map((c) => ({ label: c.name, value: c.count })), { valueText: (r) => `${r.value}건` })}
      </div>
      <div class="card"><h2>반복 불만 신호</h2>
        ${table(["신호", "불만", "리뷰 수", "발견"], a.risk_signals.map((s) => [esc(s.risk_id), `<span class="tag bad">${esc(s.complaint)}</span>`, `<span class="num">${s.reviews}</span>`, `<span class="mono small">${esc(time(s.detected_at))}</span>`]))}
      </div>
    </div>
    <div class="grid-2">
      <div class="card"><h2>단골 손님 <span class="muted">${a.regulars.length}명 (태성 customer_cycle)</span></h2>
        ${table(["손님 키", "주기", "다음 예상", "방문 간격(일)"], a.regulars.slice(0, 30).map((r) => [
          `<span class="mono small">${esc(r.customer_key)}</span>`,
          `<span class="tag ${r.cycle === "WEEKLY" ? "brand" : "blue"}">${r.cycle === "WEEKLY" ? "매주" : "매달"}</span>`,
          `<span class="mono small">${esc(time(r.next_expected_at))}</span>`,
          `<span class="mono small">${esc(r.intervals_days.join(", "))}</span>`,
        ]))}
      </div>
      <div class="card"><h2>최근 리뷰 20개 <span class="muted">전화번호·닉네임은 가림</span></h2>
        ${a.recent_reviews.map((r) => `<div class="call"><div class="call-head">
          <span class="mono">${esc(time(r.written_at))}</span><span class="tag">${esc(r.platform)}</span><span>★${r.rating}</span>
          ${r.quick ? '<span class="tag bad">불만</span>' : ""}${r.complaints.map((c) => `<span class="tag warn">${esc(c)}</span>`).join("")}
        </div><div class="call-body">${esc(r.text)}</div></div>`).join("") || '<div class="empty">리뷰가 없어요</div>'}
      </div>
    </div>`;
}

// ── 탭: 알림 타임라인 ──

async function renderTimeline() {
  const t = await api(`${API}/timeline?store_id=${state.storeId}&days_before=1&days_after=7`);
  const rules = `<div class="card"><h2>알림 규칙 ${t.slots ? `<span class="muted">알림 시각: 출근 후 ${esc(t.slots.OPENING)} · 오후 ${esc(t.slots.AFTERNOON)} · 마감 전 ${esc(t.slots.CLOSING)}</span>` : ""}</h2>
    <ul class="rules">${t.rules?.map((r) => `<li>${esc(r)}</li>`).join("") ?? ""}</ul></div>`;
  if (t.unavailable) return `${rules}<div class="note">${esc(t.unavailable)}</div>`;
  const kept = keptNote(t.computed_at);
  const now = t.now;
  const days = t.days
    .map((d) => {
      let nowShown = false;
      const batches = d.batches
        .map((b) => {
          let marker = "";
          if (!nowShown && b.slot_at > now && d.date === now.slice(0, 10)) {
            marker = `<div class="now-line">지금 ${esc(now.slice(11, 16))}</div>`;
            nowShown = true;
          }
          return `${marker}<div class="batch ${b.passed ? "passed" : ""}">
            <div class="batch-time">${esc(b.slot_at.slice(11, 16))}<span class="slot">${esc(b.slot)}${b.passed ? " · 지남" : ""}</span></div>
            <div>${b.entries
              .map(
                (e) => `<div class="entry"><div class="entry-head">
                  <span class="tag ${e.priority === 1 ? "bad" : e.priority === 2 ? "warn" : e.priority === 3 ? "blue" : ""}">우선 ${e.priority}</span>
                  <b>${esc(e.task)}</b>${e.class ? `<span class="tag">${esc(e.class)}</span>` : ""}<span class="tag brand">${esc(e.notify)}</span>
                  ${e.execute_at ? `<span class="muted small mono">실행 ${esc(time(e.execute_at))}</span>` : ""}
                </div><div>${esc(e.text)}</div>
                ${e.draft ? `<div class="draft">CLOVA 초안: ${esc(e.draft)}</div>` : ""}
                <div class="muted small mono">${esc(e.id)}</div></div>`,
              )
              .join("")}</div></div>`;
        })
        .join("");
      return `<div class="card day"><div class="day-title">${esc(d.date.slice(5).replace("-", "/"))} ${esc(d.weekday)}
        ${d.date === now.slice(0, 10) ? '<span class="tag brand">오늘</span>' : ""}</div>${batches}</div>`;
    })
    .join("");
  return `${kept}${rules}${days || '<div class="card"><div class="empty">이 기간에는 알림이 없어요</div></div>'}`;
}

// ── 탭: AI (예전 AI 비용 + AI 품질) ──

async function renderAi() {
  const [usage, quality] = await Promise.all([renderUsage(), renderQuality()]);
  return `${usage}<h3 class="section-title">품질</h3>${quality}`;
}

async function renderUsage() {
  const u = await api(`${API}/ai_usage?days=${state.usageDays}`);
  const tot = u.total;
  const chips = [1, 7, 30, 90]
    .map((d) => `<button class="${d === state.usageDays ? "btn" : "btn-outline"} small" data-days="${d}">${d === 1 ? "오늘" : `${d}일`}</button>`)
    .join(" ");
  const priceNote = u.price_set
    ? `<div class="note info">단가: 입력 1,000토큰당 ${won(u.price_input_per_1k)} · 출력 1,000토큰당 ${won(u.price_output_per_1k)} (모델 ${esc(u.model)})</div>`
    : `<div class="note">토큰 단가가 아직 없어서 비용이 0원으로 보여요. 네이버 클라우드 CLOVA Studio 요금표를 보고 server/.env 에 CLOVA_PRICE_INPUT_PER_1K, CLOVA_PRICE_OUTPUT_PER_1K 를 넣어 주세요.</div>`;
  const perStore = tot.calls ? u.by_store.length : 0;
  return `
    <div class="card"><div class="control-actions">${chips}</div></div>
    <div class="stats">
      ${stat("CLOVA 호출", num(tot.calls), `실패 ${num(tot.failed)}`, true)}
      ${stat("입력 토큰", num(tot.input_tokens), "프롬프트 + 리뷰 글")}
      ${stat("출력 토큰", num(tot.output_tokens), "CLOVA 가 쓴 답")}
      ${stat("비용", won(tot.cost_won), perStore ? `가게 하나 평균 ${won(tot.cost_won / perStore)}` : "")}
    </div>
    ${priceNote}
    ${u.calls_without_token_info ? `<div class="note">토큰 수가 없는 응답이 ${u.calls_without_token_info}번 있어요. 비용이 실제보다 적게 보일 수 있어요.</div>` : ""}
    <div class="card"><h2>날짜별 토큰</h2>
      ${columns(u.by_day, {
        valueOf: (r) => r.input_tokens + r.output_tokens,
        labelOf: (r) => Number(r.day.slice(8)),
        titleOf: (r) => `${r.day} 호출 ${r.calls} · 토큰 ${num(r.input_tokens + r.output_tokens)} · ${won(r.cost_won)}`,
      })}
    </div>
    <div class="grid-2">
      <div class="card"><h2>기능별 토큰</h2>
        ${bars(u.by_feature.map((f) => ({ label: f.name, value: f.input_tokens + f.output_tokens, f })), {
          valueText: (r) => `${num(r.value)} · ${r.f.calls}번`,
        })}
      </div>
      <div class="card"><h2>가게별</h2>
        ${table(["가게", "호출", "토큰", "비용"], u.by_store.map((s) => [
          `${esc(u.stores[s.store_id] ?? s.store_id)} <span class="muted small mono">${esc(s.store_id)}</span>`,
          `<span class="num">${num(s.calls)}</span>`,
          `<span class="num">${num(s.input_tokens + s.output_tokens)}</span>`,
          `<span class="num">${won(s.cost_won)}</span>`,
        ]))}
      </div>
    </div>`;
}

async function renderQuality() {
  const q = await api(`${API}/ai_quality?limit=60`);
  return `
    <div class="card"><h2>기능별 결과 <span class="muted">통과 = 안전 검사를 통과해 화면에 쓰임, 버림 = 검사에 걸려 다시 쓰거나 원래 문장 사용</span></h2>
      ${table(["기능", "호출", "통과", "버림", "실패", "통과율", "평균 응답"], q.by_feature.map((f) => [
        esc(f.name),
        `<span class="num">${f.calls}</span>`,
        `<span class="num">${f.accepted}</span>`,
        `<span class="num">${f.rejected}</span>`,
        `<span class="num">${f.failed}</span>`,
        `<div class="bar-track" style="width:120px"><div class="bar-fill ok" style="width:${pct(f.accepted, f.accepted + f.rejected)}%"></div></div><span class="muted small">${pct(f.accepted, f.accepted + f.rejected)}%</span>`,
        `<span class="num">${(f.avg_latency_ms / 1000).toFixed(1)}초</span>`,
      ]))}
    </div>
    <div class="card"><h2>버린 이유</h2>${bars(q.reject_reasons.map((r) => ({ label: r.reason, value: r.count })), { valueText: (r) => `${r.value}번` })}</div>
    <div class="card"><h2>최근 호출 <span class="muted">보낸 글과 받은 답은 앞부분 200자</span></h2>
      ${q.recent.map((c) => `<div class="call"><div class="call-head">
          <span class="mono">${esc(time(c.at))}</span><b>${esc(c.feature_name)}</b>
          ${c.store_id ? `<span class="tag">${esc(c.store_id)}</span>` : ""}
          ${c.status !== "ok" ? `<span class="tag bad">실패 ${esc(c.http_status ?? c.status)}</span>` : c.verdict === "accepted" ? '<span class="tag ok">통과</span>' : c.verdict === "rejected" ? `<span class="tag warn">버림 · ${esc(c.reason)}</span>` : '<span class="tag">검사 없음</span>'}
          <span class="muted small">토큰 ${num(c.input_tokens)} → ${num(c.output_tokens)} · ${(c.latency_ms / 1000).toFixed(1)}초</span>
        </div>
        <div class="call-body"><b>보냄</b>${esc(c.request_excerpt)}</div>
        <div class="call-body"><b>받음</b>${esc(c.answer_excerpt ?? "-")}</div></div>`).join("") || '<div class="empty">아직 CLOVA 를 부른 기록이 없어요</div>'}
    </div>`;
}

// ── 탭: 조작 ──

async function renderControls() {
  const s = await api(`${API}/system`);
  const clockOn = s.switches.DEV_CLOCK_ENABLED;
  const clockHint = clockOn ? "" : `<div class="note">시계 앞당기기와 초기화는 server/.env 에 DEV_CLOCK_ENABLED=true 를 넣고 서버를 다시 켜야 돼요.</div>`;
  return `
    ${clockHint}
    <div class="card"><h2>가게 계산</h2>
      <div class="control-row"><div><b>지금 가게 다시 계산</b><div class="desc">보관해 둔 분석·계획을 버리고 바로 다시 계산해요 (10분을 기다리지 않음)</div></div>
        <div class="control-actions"><button class="btn" data-action="recompute">${esc(state.storeId)} 다시 계산</button></div></div>
    </div>
    <div class="card"><h2>서버 시계 <span class="muted">지금 앞당김 ${Math.round(s.clock_shift_minutes / 60)}시간 · 서버 시각 ${esc(time(s.now))}</span></h2>
      <div class="control-row"><div><b>실제 시각으로</b><div class="desc">시연 탭이 단계마다 시계를 옮겨요. 시연을 마치면 여기서 실제 시각으로 돌려요</div></div>
        <div class="control-actions"><button class="btn" data-clock="reset" ${clockOn ? "" : "disabled"}>실제 시각으로</button></div></div>
    </div>
    <div class="card"><h2>AI</h2>
      <div class="control-row"><div><b>카드 문장 다듬기 (CLOVA)</b><div class="desc">지금 ${s.switches.SENTENCE_POLISH_ENABLED ? "켜짐" : "꺼짐"}. 서버를 다시 켜면 .env 값으로 돌아가요</div></div>
        <div class="control-actions"><button class="btn-outline" data-polish="${s.switches.SENTENCE_POLISH_ENABLED ? "off" : "on"}">${s.switches.SENTENCE_POLISH_ENABLED ? "끄기" : "켜기"}</button></div></div>
    </div>
    <div class="card"><h2>처음 상태로</h2>
      <div class="control-row"><div><b>데모 초기화</b><div class="desc">등록한 가게, 불러온 리뷰, 로그인 기록, 고친 설정, 계산 결과를 지우고 시계를 실제 시각으로 돌려요. 목업 가게(s001~s003)는 그대로예요</div></div>
        <div class="control-actions"><button class="btn-danger" data-action="reset" ${clockOn ? "" : "disabled"}>초기화</button></div></div>
      <div class="control-row"><div><b>앱 열기</b><div class="desc">mobile/ 앱을 웹으로 켠 주소</div></div>
        <div class="control-actions"><a class="btn-outline" href="http://localhost:8082" target="_blank" rel="noopener">http://localhost:8082 열기</a></div></div>
    </div>`;
}

async function moveClock(kind) {
  if (kind !== "reset") return;
  const r = await api("/dev/clock?hours=0", { method: "POST" });
  toast(`서버 시각 ${time(r.now)}`);
}

// ── 탭: 시연 (Figma UC01~UC16) ──
// 가게는 위 "가게" 고르기로 고른다. 서버가 그 가게 시연 기간(2주)을 훑어 UC01~UC16 단계를 만든다 (/api/dev_tools/demo_steps).
// 서버는 켜질 때 모든 가게를 미리 훑어 두고 결과를 파일에도 남긴다. 아직이면 "n / 42" 진행을 보여 준다 (/demo_progress).
// 단계를 누르면 서버 시계를 그 단계 시각으로 옮기고(demo_go), 오른쪽 휴대폰 틀에 앱 입구(/demo-jump)를 연다.
// [앱 홈]은 시계를 옮기지 않고 지금 서버 시각의 앱 홈을 연다. 휴대폰 틀은 처음에도 앱 홈을 띄워 둔다.
// 휴대폰 틀이 다시 그려지지 않도록, 이 탭의 버튼은 화면 전체를 다시 그리지 않고 필요한 곳만 바꾼다.

const DEMO_APP_KEY = "dona-dev-app-url";
// 휴대폰 틀은 앱을 127.0.0.1 로 띄운다. 평소 쓰는 앱(localhost:8082)과 브라우저 저장 공간이 따로라서,
// 시연 단계가 휴대폰 틀에 넣는 로그인·가게·카드 상태가 평소 앱에 남지 않는다 (주소가 다르면 저장 공간도 다르다).
const DEMO_APP_DEFAULT = "http://127.0.0.1:8082";
/** 예전에 기억한 localhost 주소는 127.0.0.1 로 바꿔 쓴다 (같은 저장 공간을 쓰지 않게) */
const demoAppUrlOf = (url) => url.replace(/^(https?:\/\/)localhost(?=[:/]|$)/, "$1127.0.0.1");
const DEMO_POLISH_KEY = "dona-dev-demo-polish";
const saved = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
const demo = {
  steps: {},
  index: -1,
  appUrl: demoAppUrlOf(saved(DEMO_APP_KEY, DEMO_APP_DEFAULT)),
  polish: saved(DEMO_POLISH_KEY, "off") === "on", // 시연 중 카드 문장 다듬기(CLOVA). 기본은 끔
};

function demoJumpUrl(open) {
  const q = new URLSearchParams({ store: state.storeId, t: String(Date.now()) });
  // 대시보드에 시연용 마우스 표시를 켰으면(?cursor=1, cursor.js) 휴대폰 틀 속 앱에도 켠다 (앱 DemoCursor)
  if (saved("dona-dev-cursor", "") === "1") q.set("cursor", "1");
  for (const [k, v] of Object.entries(open)) {
    if (v === true) q.set(k, "1");
    else if (v !== null && v !== undefined && v !== false && k !== "note") q.set(k, String(v));
  }
  return `${demo.appUrl.replace(/\/+$/, "")}/demo-jump?${q}`;
}

const demoHomeUrl = () => demoJumpUrl({ to: "/" });

function demoStepRow(step, i) {
  const at = step.at_label ? `<span class="mono small">${esc(step.at_label)}</span>` : "";
  const note = step.open?.note ? ` <span class="tag">${esc(step.open.note)}</span>` : "";
  if (!step.available) {
    return `<div class="demo-step off" title="${esc(step.reason)}"><span class="demo-figma mono">${esc(step.figma)}</span>
      <div><div>${esc(step.title)}</div><div class="muted small">${esc(step.reason)}</div></div></div>`;
  }
  return `<button class="demo-step" data-demo-step="${i}" id="demo-step-${i}"><span class="demo-figma mono">${esc(step.figma)}</span>
    <div><div>${esc(step.title)}${note}</div><div class="muted small">${at}</div></div></button>`;
}

/** 가게마다 시연 준비 상태 한 줄 */
function demoReadyRows(p, names) {
  return Object.entries(p.ready)
    .map(([sid, ready]) => {
      const run = p.progress[sid];
      const label = ready ? '<span class="tag ok">준비됨</span>' : run ? `<span class="tag warn">훑는 중 ${run.done} / ${run.total}</span>` : '<span class="tag">아직</span>';
      return `<div class="demo-ready ${sid === state.storeId ? "on" : ""}"><span>${esc(names[sid] ?? sid)} <span class="muted small mono">${esc(sid)}</span></span>${label}</div>`;
    })
    .join("");
}

/** 시연 단계를 기다리는 동안 "n / 42" 를 보여 준다 */
async function demoSteps(storeId) {
  if (demo.steps[storeId]) return demo.steps[storeId];
  let waiting = true;
  const poll = async () => {
    while (waiting) {
      try {
        const p = await api(`${API}/demo_progress`);
        const run = p.progress[storeId];
        const el = document.getElementById("demo-loading");
        if (el) el.textContent = run ? `시연 기간을 훑는 중… ${run.done} / ${run.total}` : "시연 기간을 준비하는 중…";
      } catch {}
      await new Promise((r) => setTimeout(r, 500));
    }
  };
  poll();
  try {
    demo.steps[storeId] = await api(`${API}/demo_steps?store_id=${storeId}`);
  } finally {
    waiting = false;
  }
  return demo.steps[storeId];
}

async function renderDemo() {
  const d = await demoSteps(state.storeId);
  // 준비 상태는 없어도 시연은 된다 (예전 서버처럼 demo_progress 가 없으면 준비 줄만 빼고 그린다)
  const [stores, p] = await Promise.all([api(`${API}/stores`), api(`${API}/demo_progress`).catch(() => null)]);
  const names = Object.fromEntries(stores.map((s) => [s.store_id, s.name]));
  const available = d.steps.filter((s) => s.available).length;
  const groups = d.ucs
    .map((uc) => {
      const rows = d.steps.map((s, i) => [s, i]).filter(([s]) => s.uc === uc.uc);
      const on = rows.filter(([s]) => s.available).length;
      return `<div class="demo-uc"><div class="demo-uc-head"><b>${esc(uc.uc)} ${esc(uc.title)}</b><span class="muted small">${on} / ${rows.length}</span></div>
        <div class="muted small">${esc(uc.summary)}</div>
        ${rows.map(([s, i]) => demoStepRow(s, i)).join("")}</div>`;
    })
    .join("");
  return `
    <div class="demo-layout" data-demo>
      <div class="card demo-stores"><h2>시연 도구</h2>
        <div class="muted small">가게는 위 "가게"에서 골라요</div>
        <div class="demo-tools">
          <label class="muted small">앱 주소<input id="demo-app-url" value="${esc(demo.appUrl)}"></label>
          <label class="demo-check"><input type="checkbox" id="demo-polish" ${demo.polish ? "checked" : ""}> 단계마다 문장 다듬기 (CLOVA)</label>
          <button class="btn small" data-demo-action="clock-reset">시연 끝내기 (시계를 실제 시각으로)</button>
          <button class="btn-outline small" data-demo-action="rescan">이 가게 다시 훑기</button>
          <div class="muted small">휴대폰 틀은 앱을 127.0.0.1 로 띄워서, 평소 쓰는 앱(localhost:8082)의 로그인·가게 상태는 바뀌지 않아요. 서버 시계는 하나라서 시연을 마치면 [시연 끝내기]를 눌러 주세요.</div>
        </div>
        ${p ? `<div class="demo-tools"><div class="muted small">시연 준비</div>${demoReadyRows(p, names)}</div>` : ""}
      </div>
      <div class="demo-phone-col">
        <div class="demo-nav">
          <button class="btn-outline" data-demo-action="prev">◀ 이전</button>
          <button class="btn-outline" data-demo-action="home">앱 홈</button>
          <button class="btn" data-demo-action="next">다음 ▶</button>
        </div>
        <div id="demo-now" class="small muted demo-now">지금 서버 시각의 앱 홈이에요. 단계를 누르거나 다음을 눌러 시작해요</div>
        <div class="demo-phone"><iframe id="demo-frame" title="도나 앱" src="${esc(demoHomeUrl())}"></iframe></div>
        <div class="muted small">앱은 <span class="mono">cd mobile && npm run web</span> 로 켜 두세요. 서버는 DEV_CLOCK_ENABLED=true 여야 시계를 옮길 수 있어요.</div>
      </div>
      <div class="card demo-steps"><h2>${esc(d.store.name)} <span class="muted">시연 기간 ${esc(d.demo_week.first)} ~ ${esc(d.demo_week.last)} · 열 수 있는 화면 ${available} / ${d.steps.length}</span></h2>
        ${d.unavailable ? `<div class="note">${esc(d.unavailable)}</div>` : ""}
        ${groups}
      </div>
    </div>`;
}

async function openDemoStep(i) {
  const d = demo.steps[state.storeId];
  const step = d?.steps[i];
  if (!step || !step.available) return;
  demo.index = i;
  document.querySelectorAll(".demo-step.on").forEach((el) => el.classList.remove("on"));
  const row = document.getElementById(`demo-step-${i}`);
  row?.classList.add("on");
  // 단계 목록 칸 안에서만 굴린다 (페이지 전체를 굴리면 좁은 화면에서 휴대폰 틀이 화면 밖으로 밀린다)
  const box = row?.closest(".demo-steps");
  if (row && box) box.scrollTop += row.getBoundingClientRect().top - box.getBoundingClientRect().top - box.clientHeight / 3;
  const label = document.getElementById("demo-now");
  label.textContent = `${step.uc} · ${step.figma} 여는 중…`;
  if (step.at) await api(`${API}/demo_go`, { method: "POST", body: JSON.stringify({ store_id: state.storeId, at: step.at, polish: demo.polish }) });
  document.getElementById("demo-frame").src = demoJumpUrl(step.open);
  label.textContent = `${step.uc} · ${step.figma} ${step.title}${step.at_label ? ` · 서버 시각 ${step.at_label}` : ""}`;
  // 좁은 화면(한 줄로 쌓임)에서는 휴대폰 틀이 단계 목록 위에 있어서, 바뀐 화면이 보이게 휴대폰 틀로 올린다
  if (window.matchMedia("(max-width: 1200px)").matches) document.querySelector(".demo-phone-col")?.scrollIntoView({ block: "start", behavior: "smooth" });
  checkServer();
}

function nextDemoIndex(direction) {
  const steps = demo.steps[state.storeId]?.steps ?? [];
  for (let i = demo.index + direction; i >= 0 && i < steps.length; i += direction) if (steps[i].available) return i;
  return -1;
}

async function onDemoClick(button) {
  const { demoStep, demoAction } = button.dataset;
  if (demoStep !== undefined) return openDemoStep(Number(demoStep));
  if (demoAction === "home") {
    document.querySelectorAll(".demo-step.on").forEach((el) => el.classList.remove("on"));
    document.getElementById("demo-frame").src = demoHomeUrl();
    document.getElementById("demo-now").textContent = "지금 서버 시각의 앱 홈이에요";
    return;
  }
  if (demoAction === "next" || demoAction === "prev") {
    const i = nextDemoIndex(demoAction === "next" ? 1 : -1);
    return i >= 0 ? openDemoStep(i) : toast(demoAction === "next" ? "마지막 단계예요" : "첫 단계예요");
  }
  if (demoAction === "rescan") {
    button.disabled = true;
    toast("시연 기간을 다시 훑어요 (10초쯤)");
    demo.steps[state.storeId] = await api(`${API}/demo_rescan?store_id=${state.storeId}`, { method: "POST" });
    demo.index = -1;
    return show("demo");
  }
  if (demoAction === "clock-reset") {
    const r = await api(`${API}/demo_clock_reset?store_id=${state.storeId}`, { method: "POST" });
    toast(`시연을 끝냈어요 · 서버 시각 ${time(r.now)}`);
    document.querySelectorAll(".demo-step.on").forEach((el) => el.classList.remove("on"));
    demo.index = -1;
    document.getElementById("demo-frame").src = demoHomeUrl();
    document.getElementById("demo-now").textContent = "시연을 끝냈어요. 실제 시각의 앱 홈이에요";
    return checkServer();
  }
}

// ── 탭: 화면 글 (앱 화면의 글을 화면별로 보고 고쳐서 앱 코드에 넣기) ──
// 서버가 mobile/scripts/ui-text/cli.mjs 를 불러 글을 뽑고(GET ui_text), 저장하고(save), 코드에 넣는다(apply).
// [수정] 칸에 적으면 0.6초 뒤 mobile/scripts/ui-text/edits.json 에 저장된다. 넣은 수정은 edits.json 에서 빠지고 원본이 수정본으로 바뀐다.
// 밖에서 고치기: [JSON 내려받기] 로 모든 원본 + 빈 "수정" 칸 파일을 받고, 고친 파일을 [JSON 등록] 으로 올리면 수정에 더해진다(export, import).

const ut = { data: null, edits: {}, items: new Map(), current: null, q: "", saveTimer: null, result: null, imported: null };
const UT_SECTION = { screen: "화면", shared: "여러 화면이 같이 쓰는 글", unused: "쓰는 곳을 못 찾은 글" };

function utPlaceholders(text) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "$" && text[i + 1] === "{") {
      let depth = 0;
      let j = i + 1;
      for (; j < text.length; j++) {
        if (text[j] === "{") depth++;
        else if (text[j] === "}" && --depth === 0) break;
      }
      out.push(text.slice(i, j + 1));
      i = j;
    }
  }
  return out;
}

/** ${…} 자리는 보라색, 찾는 글은 노란색으로 */
function utShow(text, q = "") {
  const parts = [];
  let last = 0;
  for (const ph of utPlaceholders(text)) {
    const at = text.indexOf(ph, last);
    parts.push({ t: text.slice(last, at) }, { t: ph, ph: true });
    last = at + ph.length;
  }
  parts.push({ t: text.slice(last) });
  return parts
    .map((p) => {
      let h = esc(p.t);
      if (q && !p.ph) h = h.split(esc(q)).join(`<mark>${esc(q)}</mark>`);
      return p.ph ? `<span class="ut-ph" title="코드가 채우는 자리예요. 그대로 두세요">${h}</span>` : h;
    })
    .join("");
}

async function utLoad() {
  if (ut.saveTimer) await utSave();
  ut.data = await api(`${API}/ui_text`);
  ut.edits = ut.data.edits || {};
  ut.items.clear();
  for (const g of ut.data.groups) for (const it of g.items) ut.items.set(it.id, it);
  if (!ut.data.groups.some((g) => g.id === ut.current)) ut.current = (ut.data.groups.find((g) => g.type === "screen") || ut.data.groups[0])?.id;
}

function utStat() {
  const n = Object.keys(ut.edits).length;
  const stat = document.getElementById("ut-stat");
  if (stat) stat.textContent = `글 ${num(ut.data.total)}개 · 고친 글 ${n}개`;
  const apply = document.querySelector('[data-ut="apply"]');
  if (apply) apply.disabled = n === 0;
}

function utNavHtml() {
  let html = "";
  let lastType = null;
  for (const g of ut.data.groups) {
    if (g.type !== lastType) {
      html += `<div class="ut-nav-head">${esc(UT_SECTION[g.type] ?? g.type)}</div>`;
      lastType = g.type;
    }
    const n = g.items.filter((i) => ut.edits[i.id]).length;
    const route = g.route && !g.route.startsWith("(") ? `<span class="ut-route mono">${esc(g.route)}</span>` : "";
    html += `<button class="ut-nav-item ${g.id === ut.current && !ut.q ? "on" : ""}" data-ut-group="${esc(g.id)}"><span class="ut-name">${esc(g.name)}</span>${route}${n ? `<span class="ut-count">${n}</span>` : ""}</button>`;
  }
  return html;
}

function utRowHtml(it, q = "", groupName = "") {
  const e = ut.edits[it.id];
  const title = it.label === "제목" || it.label === "시트 제목";
  const phs = it.placeholders || [];
  return `<div class="ut-row ${e ? "changed" : ""}" data-ut-id="${esc(it.id)}">
    <div class="ut-meta">
      <span class="tag ${title ? "brand" : ""}">${esc(it.label)}</span>
      ${groupName ? `<div class="muted small">${esc(groupName)}</div>` : ""}
      <div class="ut-where mono">${esc(it.file.replace(/^src\//, ""))}:${it.line}<br>${esc(it.func)}</div>
    </div>
    <div><div class="ut-col">원본</div><div class="ut-orig">${utShow(it.text, q)}</div></div>
    <div><div class="ut-col">[수정]</div>
      <textarea rows="${Math.max(1, it.text.split("\n").length)}" placeholder="바꿀 글 (비워 두면 그대로)">${esc(e ? e.edited : "")}</textarea>
      ${phs.length ? `<div class="muted small">그대로 둘 자리: ${phs.map((p) => `<span class="ut-ph">${esc(p)}</span>`).join(" ")}</div>` : ""}
      <div class="ut-warn"></div>
      ${e ? `<button class="btn-outline small" data-ut="undo">원본으로</button>` : ""}
    </div>
  </div>`;
}

function utResultHtml(r) {
  const ok = r.failed.length === 0 && r.check.ok;
  const typeLine = r.applied.length
    ? `<div class="small ${r.check.ok ? "ut-ok" : "ut-fail"}">${r.check.ok ? "타입 검사 통과 (tsc). 앱을 다시 불러오면 바뀐 글이 보여요." : "타입 검사에서 오류가 났어요. 아래를 확인해 주세요."}</div>`
    : "";
  const failed = r.failed.length
    ? `<ul>${r.failed.map((f) => `<li><span class="mono small">${esc(f.file || "")}:${f.line || ""}</span> <span class="ut-from">${esc(f.original || "")}</span> → <span class="ut-to">${esc(f.edited || "")}</span><div class="small ut-fail">${esc(f.reason)}</div></li>`).join("")}</ul>`
    : "";
  return `<div class="card ut-panel ${ok ? "" : "bad"}"><h2>코드에 넣었어요: 바꾼 글 ${r.applied.length}개${r.failed.length ? `, 못 바꾼 글 ${r.failed.length}개` : ""}</h2>
    ${typeLine}${r.check.ok ? "" : `<pre class="ut-pre">${esc(r.check.output)}</pre>`}${failed}
    <button class="btn-outline small" data-ut="close-result">닫기</button></div>`;
}

function utImportHtml(r) {
  const skipped = r.skipped.length
    ? `<div class="small ut-fail">못 담은 글 ${r.skipped.length}개: 고쳐서 다시 올려 주세요</div>
      <ul>${r.skipped.map((s) => `<li><span class="muted small">${esc(s.screen || "")}</span> <span class="mono small">${esc(s.where)}</span> <span class="ut-from">${esc(s.original)}</span> → <span class="ut-to">${esc(s.edited)}</span><div class="small ut-fail">${esc(s.reason)}</div></li>`).join("")}</ul>`
    : "";
  return `<div class="card ut-panel ${r.skipped.length ? "bad" : ""}"><h2>${esc(r.name)} 등록: 고친 글 ${r.asked}개 중 ${r.loaded.length}개를 담았어요</h2>
    <div class="muted small">담은 글은 아래 화면들에 노란색으로 보여요. 확인한 뒤 [코드에 넣기]를 누르면 앱에 반영돼요.</div>
    ${skipped}<button class="btn-outline small" data-ut="close-import">닫기</button></div>`;
}

function utMainHtml() {
  let html = ut.result ? utResultHtml(ut.result) : "";
  if (ut.imported) html += utImportHtml(ut.imported);
  const stale = ut.data.stale || [];
  if (stale.length) {
    html += `<div class="card ut-panel bad"><h2>원본을 못 찾은 수정 ${stale.length}개</h2>
      <div class="muted small">코드가 바뀌어 원래 글이 없어졌어요. 새 원본을 찾아 다시 적어 주세요.</div>
      <ul>${stale.map((s) => `<li><span class="mono small">${esc(s.file || "")}:${s.line || ""}</span> <span class="ut-from">${esc(s.original || "")}</span> → <span class="ut-to">${esc(s.edited || "")}</span> <button class="btn-outline small" data-ut-drop="${esc(s.id)}">지우기</button></li>`).join("")}</ul></div>`;
  }
  if (ut.q) {
    const hits = [];
    for (const g of ut.data.groups) for (const it of g.items) if (it.text.includes(ut.q) || (ut.edits[it.id]?.edited || "").includes(ut.q)) hits.push([it, g.name]);
    html += `<div class="ut-head"><h3>"${esc(ut.q)}" 찾은 글 ${hits.length}개</h3></div>`;
    return html + (hits.map(([it, name]) => utRowHtml(it, ut.q, name)).join("") || `<div class="empty">찾은 글이 없어요</div>`);
  }
  const g = ut.data.groups.find((x) => x.id === ut.current);
  if (!g) return html + `<div class="empty">화면이 없어요</div>`;
  const shared = g.type === "screen" ? ut.data.groups.filter((x) => x.type === "shared" && x.routes?.includes(g.route)) : [];
  html += `<div class="ut-head"><h3>${esc(g.name)}</h3>${g.route && !g.route.startsWith("(") ? `<div class="muted small mono">${esc(g.route)}</div>` : ""}
    ${g.desc ? `<div class="note info">${esc(g.desc)}</div>` : ""}
    ${shared.length ? `<div class="small muted">이 화면이 같이 쓰는 글: ${shared.map((s) => `<button class="tag" data-ut-group="${esc(s.id)}">${esc(s.name)} (${s.items.length})</button>`).join(" ")}</div>` : ""}
    <div class="muted small">왼쪽이 지금 코드의 글이에요. [수정] 칸에 바꿀 글을 적으면 바로 저장돼요. 줄 바꿈은 그대로 화면의 줄 바꿈이 돼요.</div></div>`;
  return html + (g.items.map((it) => utRowHtml(it)).join("") || `<div class="empty">이 화면에만 있는 글은 없어요. 위 "같이 쓰는 글"을 봐 주세요.</div>`);
}

function utCheck(row, it, value) {
  const phs = it.placeholders || [];
  const bad = value && phs.length && utPlaceholders(value).join("\0") !== phs.join("\0");
  row.querySelector(".ut-warn").textContent = bad ? "보라색 자리(${…})를 원본과 같은 순서로 모두 남겨 주세요. 그대로가 아니면 코드에 넣지 않아요." : "";
}

function utRedraw({ nav = true, main = true } = {}) {
  if (nav) document.getElementById("ut-nav").innerHTML = utNavHtml();
  if (main) {
    const el = document.getElementById("ut-main");
    el.innerHTML = utMainHtml();
    el.querySelectorAll(".ut-row").forEach((row) => utCheck(row, ut.items.get(row.dataset.utId), row.querySelector("textarea").value));
  }
  utStat();
}

function utSaved(text) {
  const el = document.getElementById("ut-saved");
  if (el) el.textContent = text;
}

function utScheduleSave() {
  utSaved("저장 기다리는 중…");
  clearTimeout(ut.saveTimer);
  ut.saveTimer = setTimeout(utSave, 600);
}

async function utSave() {
  clearTimeout(ut.saveTimer);
  ut.saveTimer = null;
  const r = await api(`${API}/ui_text/save`, { method: "POST", body: JSON.stringify({ edits: ut.edits }) });
  utSaved(`${ut.data.editsFile} 에 저장했어요 ${new Date(r.at).toLocaleTimeString("ko-KR")}`);
  utStat();
}

async function renderUiText() {
  await utLoad();
  return `<div class="ut" data-uitext>
    <div class="card ut-bar">
      <span id="ut-stat" class="muted small"></span>
      <input id="ut-q" type="search" placeholder="글 찾기 (모든 화면에서)" value="${esc(ut.q)}">
      <span id="ut-saved" class="muted small"></span>
      <button class="btn-outline" data-ut="export" title="모든 화면의 원본 글과 빈 '수정' 칸이 든 파일. 밖에서 '수정'만 채워 다시 올리면 돼요">JSON 내려받기</button>
      <button class="btn-outline" data-ut="import" title="밖에서 '수정'을 채운 JSON 파일 올리기">JSON 등록</button>
      <input id="ut-file" type="file" accept=".json,application/json" hidden>
      <button class="btn-outline" data-ut="save">저장</button>
      <button class="btn" data-ut="apply">코드에 넣기</button>
    </div>
    <div class="ut-layout">
      <div class="card ut-nav" id="ut-nav"></div>
      <div class="ut-main" id="ut-main"></div>
    </div>
    <dialog id="ut-dialog" class="ut-dialog"></dialog>
  </div>`;
}

function utConfirmApply() {
  const list = Object.values(ut.edits);
  const dialog = document.getElementById("ut-dialog");
  dialog.innerHTML = `<h3>앱 코드의 글 ${list.length}개를 바꿀게요</h3>
    <ol>${list.map((e) => `<li><div class="mono small muted">${esc(e.file)}:${e.line}</div><div class="ut-from">${esc(e.original)}</div><div class="ut-to">${esc(e.edited)}</div></li>`).join("")}</ol>
    <div class="muted small">바꾼 뒤 타입 검사(tsc)를 돌려요. 잘못 바꾸면 git 으로 되돌릴 수 있어요.</div>
    <div class="ut-actions"><button class="btn-outline" data-ut="cancel">그만두기</button><button class="btn" data-ut="apply-yes">바꾸기</button></div>`;
  dialog.showModal();
}

async function onUiTextClick(button) {
  const { ut: action, utGroup, utDrop } = button.dataset;
  if (utGroup) {
    ut.current = utGroup;
    ut.q = "";
    document.getElementById("ut-q").value = "";
    utRedraw();
    return window.scrollTo({ top: 0 });
  }
  if (utDrop) {
    delete ut.edits[utDrop];
    ut.data.stale = ut.data.stale.filter((s) => s.id !== utDrop);
    utScheduleSave();
    return utRedraw({ nav: false });
  }
  if (action === "undo") {
    const row = button.closest(".ut-row");
    const textarea = row.querySelector("textarea");
    textarea.value = "";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    return button.remove();
  }
  if (action === "save") return utSave();
  if (action === "apply") return utConfirmApply();
  if (action === "cancel") return document.getElementById("ut-dialog").close();
  if (action === "export") {
    const a = document.createElement("a");
    a.href = `${API}/ui_text/export`;
    a.download = "";
    a.click();
    return toast("JSON 을 내려받는 중… '수정' 칸만 채워서 [JSON 등록]으로 올려 주세요");
  }
  if (action === "import") return document.getElementById("ut-file").click();
  if (action === "close-import") {
    ut.imported = null;
    return utRedraw({ nav: false });
  }
  if (action === "close-result") {
    ut.result = null;
    return utRedraw({ nav: false });
  }
  if (action === "apply-yes") {
    button.disabled = true;
    button.textContent = "바꾸고 검사하는 중…";
    clearTimeout(ut.saveTimer);
    ut.saveTimer = null;
    ut.result = await api(`${API}/ui_text/apply`, { method: "POST", body: JSON.stringify({ edits: ut.edits }) });
    ut.imported = null;
    document.getElementById("ut-dialog").close();
    await utLoad();
    utRedraw();
    return window.scrollTo({ top: 0 });
  }
}

async function utImportFile(input) {
  const file = input.files[0];
  input.value = "";
  if (!file) return;
  let doc;
  try {
    doc = JSON.parse(await file.text());
  } catch {
    return toast(`${file.name} 을 읽지 못했어요. JSON 모양이 깨졌는지 봐 주세요 (쉼표, 따옴표)`);
  }
  if (ut.saveTimer) await utSave();
  const r = await api(`${API}/ui_text/import`, { method: "POST", body: JSON.stringify(doc) });
  ut.imported = { ...r, name: file.name };
  ut.result = null;
  await utLoad();
  utRedraw();
  window.scrollTo({ top: 0 });
  if (r.loaded.length) utConfirmApply();
  else toast("담은 글이 없어요. '수정' 칸을 채웠는지 봐 주세요");
}

function onUiTextInput(target) {
  if (target.id === "ut-q") {
    ut.q = target.value.trim();
    return utRedraw();
  }
  const row = target.closest(".ut-row");
  if (!row || target.tagName !== "TEXTAREA") return;
  const it = ut.items.get(row.dataset.utId);
  const value = target.value;
  if (value === "" || value === it.text) delete ut.edits[it.id];
  else ut.edits[it.id] = { file: it.file, line: it.line, func: it.func, original: it.text, edited: value };
  row.classList.toggle("changed", Boolean(ut.edits[it.id]));
  utCheck(row, it, value);
  document.getElementById("ut-nav").innerHTML = utNavHtml();
  utScheduleSave();
}

// ── 탭 전환, 버튼 ──

// ── 탭: 에이전트 (server/Harness) ──
// 하네스 ↔ 기존 단일 호출 스위치, 지금 도는 실행, 에이전트별 통계, 최근 실행(단계 펼치기).
// 기록은 기존 서버와 음성 백엔드가 같이 쓰는 harness_trace.db 에서 읽어 두 서버의 실행이 모두 보인다. 이 탭을 보는 동안 5초마다 새로 그린다.

const agentView = { open: new Set(), steps: {} };
const OUTCOME_TAG = {
  accepted: '<span class="tag ok">통과</span>',
  cache: '<span class="tag">캐시</span>',
  fallback: '<span class="tag warn">단일 호출로 물러남</span>',
  failed: '<span class="tag bad">실패</span>',
  running: '<span class="tag run">도는 중</span>',
  stalled: '<span class="tag bad">멈춤</span>',
};
const KIND_KO = { start: "시작", llm: "CLOVA", tool: "도구", submit: "제출", end: "끝", fallback: "물러나기", cache: "캐시" };

function agentStepsHtml(runId) {
  const steps = agentView.steps[runId];
  if (!steps) return `<div class="run-steps"><span class="muted">불러오는 중…</span></div>`;
  if (!steps.length) return `<div class="run-steps"><span class="muted">기록이 없어요</span></div>`;
  return `<div class="run-steps">${steps.map((s) => `<div class="step ${s.run_id !== runId ? "child" : ""}">
      <span class="mono muted">${s.step}</span><span>${esc(KIND_KO[s.kind] ?? s.kind)}</span>
      <span class="mono">${esc(s.run_id !== runId ? `↳ ${s.agent}` : s.name ?? "")}${s.run_id !== runId && s.name ? ` · ${esc(s.name)}` : ""}</span>
      <span class="detail">${esc(s.detail ?? "")}</span></div>`).join("")}</div>`;
}

function agentRunRow(r) {
  const open = agentView.open.has(r.run_id);
  const seconds = Math.max(0, (new Date(r.last_at) - new Date(r.started_at)) / 1000);
  return `<div class="call"><div class="call-head">
      <span class="mono">${esc(time(r.started_at))}</span><b>${esc(r.agent_name)}</b>
      <span class="tag ${r.server === "음성 백엔드" ? "blue" : "brand"}">${esc(r.server)}</span>
      ${r.store_id ? `<span class="tag">${esc(r.store_id)}</span>` : ""}
      ${OUTCOME_TAG[r.outcome] ?? esc(r.outcome)}
      <span class="muted small mono">${esc(r.task ?? "")}</span>
      <span class="muted small">CLOVA ${r.llm_calls}번 · 도구 ${r.tools}번 · 거절 ${r.rejections}번 · ${seconds.toFixed(1)}초${r.outcome === "running" ? ` · 지금 ${esc(r.last_step)}` : ""}</span>
      <button class="btn-outline small" data-run="${esc(r.run_id)}">${open ? "단계 접기" : "단계 보기"}</button>
    </div>${open ? agentStepsHtml(r.run_id) : ""}</div>`;
}

async function renderAgents() {
  const a = await api(`${API}/agents?limit=60`);
  await Promise.all([...agentView.open].map(async (id) => {
    agentView.steps[id] = (await api(`${API}/agents/run?run_id=${encodeURIComponent(id)}`)).steps;
  }));
  const jobs = a.bridge.stores.filter((s) => s.job && s.job.state);
  const keyNote = a.clova_key ? "" : `<div class="note">CLOVA 키가 없어서 어느 쪽이든 CLOVA 를 부르지 않고 기본 문장을 써요 (server/.env 의 CLOVA_STUDIO_API_KEY).</div>`;
  return `
    ${keyNote}
    <div class="card"><h2>LLM 방식</h2>
      <div class="control-row"><div><b>${a.enabled ? "에이전트 하네스" : "기존 단일 호출"} 사용 중</b>
        <div class="desc">하네스: 가게 계산이 끝나면 뒤에서 답글 초안(reply_agent), 반복 불만(complaint_agent), 7일 안 메뉴판·포스터(campaign_agent),
        충돌 있는 알림 묶음(supervisor)을 돌려요. 에이전트가 실패하면 기존 단일 호출로 물러나요.<br>
        단일 호출: 예전처럼 답글 초안(write_drafts), 메뉴 후보(menu_candidates), 포스터 멘트(ment.suggest)를 한 번씩 물어요.<br>
        바꾸면 보관한 계산을 지우고 다음 요청부터 바뀐 방식으로 계산해요. 서버를 다시 켜면 .env 의 AGENT_HARNESS_ENABLED 로 돌아가요.
        음성 백엔드(:8100)는 따로 VOICE_AGENT_* 로 켜고 꺼요.</div></div>
        <div class="control-actions"><div class="mode-switch">
          <button data-agent-mode="on" class="${a.enabled ? "on" : ""}">에이전트 하네스</button>
          <button data-agent-mode="off" class="${a.enabled ? "" : "on"}">기존 단일 호출</button>
        </div></div></div>
    </div>
    <div class="stats">
      ${stat("지금 도는 실행", num(a.running.length), "끝난 줄 없이 5분 안에 움직인 실행", true)}
      ${stat("최근 실행", num(a.recent.length), "supervisor 아래 일꾼 실행은 단계 보기에")}
      ${stat("에이전트 통과", num(a.stats.reduce((n, s) => n + s.accepted, 0)), "검사를 통과한 제안")}
      ${stat("물러남·실패", num(a.stats.reduce((n, s) => n + s.fallback + s.failed, 0)), "기존 단일 호출 또는 기본 문장")}
    </div>
    <div class="card"><h2>지금 도는 에이전트</h2>
      ${a.running.length ? a.running.map(agentRunRow).join("") : '<div class="empty">지금 도는 에이전트가 없어요</div>'}
    </div>
    ${jobs.length ? `<div class="card"><h2>기존 서버 가게별 작업 <span class="muted">가게 계산이 끝날 때마다 뒤에서 한 번씩</span></h2>
      ${table(["가게", "상태", "진행", "지금", "제안 (에이전트 / 물러남)", "충돌 조율"], jobs.map((s) => [
        esc(s.store_id),
        esc({ queued: "기다림", running: "도는 중", done: "끝", failed: "실패" }[s.job.state] ?? s.job.state),
        `<span class="num">${s.job.done ?? 0} / ${s.job.total ?? 0}</span>`,
        `<span class="mono small">${esc(s.job.current ?? "-")}</span>`,
        `<span class="num">${s.proposals.filter((p) => p.source === "AGENT").length} / ${s.proposals.filter((p) => p.source !== "AGENT").length}</span>`,
        s.batches.length ? s.batches.map((b) => `${esc(b.slot_at.slice(5))} ${esc(b.headline ?? "")} <span class="muted small">${esc(b.conflicts.join("; "))}</span>`).join("<br>") : '<span class="muted">충돌 없음</span>',
      ]))}</div>` : ""}
    <div class="card"><h2>에이전트별 <span class="muted">최근 기록 기준</span></h2>
      ${table(["에이전트", "서버", "실행", "통과", "캐시", "물러남", "실패", "도는 중", "통과율", "실행당 CLOVA"], a.stats.map((s) => [
        `${esc(s.agent_name)} <span class="muted small mono">${esc(s.agent)}</span>`, esc(s.server),
        `<span class="num">${s.runs}</span>`, `<span class="num">${s.accepted}</span>`, `<span class="num">${s.cache}</span>`,
        `<span class="num">${s.fallback}</span>`, `<span class="num">${s.failed}</span>`, `<span class="num">${s.running}</span>`,
        `<div class="bar-track" style="width:100px"><div class="bar-fill ok" style="width:${pct(s.accepted + s.cache, s.runs)}%"></div></div><span class="muted small">${pct(s.accepted + s.cache, s.runs)}%</span>`,
        `<span class="num">${s.runs ? (s.llm_calls / s.runs).toFixed(1) : "-"}</span>`,
      ]))}
    </div>
    <div class="card"><h2>최근 실행</h2>
      ${a.recent.length ? a.recent.map(agentRunRow).join("") : '<div class="empty">아직 에이전트를 돌린 기록이 없어요</div>'}
    </div>`;
}

async function onAgentsClick(button) {
  const { agentMode, run } = button.dataset;
  if (agentMode) {
    button.disabled = true;
    await api(`${API}/agents/mode`, { method: "POST", body: JSON.stringify({ enabled: agentMode === "on" }) });
    toast(agentMode === "on" ? "에이전트 하네스로 바꿈" : "기존 단일 호출로 바꿈");
  }
  if (run) {
    if (agentView.open.has(run)) agentView.open.delete(run);
    else agentView.open.add(run);
  }
  content.innerHTML = await renderAgents();
}

// 에이전트 탭을 보는 동안 5초마다 조용히 새로 그린다 (지금 도는 실행이 바뀌는 것을 보려고)
setInterval(async () => {
  if (state.tab !== "agents" || document.hidden) return;
  try { content.innerHTML = await renderAgents(); } catch {}
}, 5000);

const RENDER = {
  demo: renderDemo,
  status: renderStatus,
  stores: renderStores,
  analysis: renderAnalysis,
  timeline: renderTimeline,
  ai: renderAi,
  agents: renderAgents,
  controls: renderControls,
  uitext: renderUiText,
  eval: renderEval,
};

/** 주소의 탭 이름 → 있는 탭 이름 (예전 이름도 받음). 모르면 null */
const tabOf = (name) => (RENDER[name] ? name : TAB_ALIAS[name] ?? null);

async function show(tab = state.tab) {
  tab = tabOf(tab) ?? "status";
  state.tab = tab;
  try { localStorage.setItem("dona-dev-tab", tab); } catch {}
  if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const loading = tab === "demo" && !demo.steps[state.storeId] ? "시연 기간을 준비하는 중…" : "불러오는 중… (가게를 처음 계산하면 몇 초 걸려요)";
  content.innerHTML = `<div class="card"><div class="empty" id="demo-loading">${loading}</div></div>`;
  try {
    content.innerHTML = await RENDER[tab]();
    if (tab === "uitext") utRedraw();
  } catch (error) {
    content.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

async function loadStores() {
  const select = document.getElementById("store-select");
  try {
    const stores = await api(`${API}/stores`);
    const saved = (() => { try { return localStorage.getItem("dona-dev-store"); } catch { return null; } })();
    state.storeId = stores.some((s) => s.store_id === saved) ? saved : stores[0]?.store_id;
    select.innerHTML = stores.map((s) => `<option value="${esc(s.store_id)}">${esc(s.store_id)} · ${esc(s.name)}</option>`).join("");
    select.value = state.storeId;
  } catch (error) {
    content.innerHTML = `<div class="error">${esc(error.message)}</div>`;
    throw error;
  }
}

async function checkServer() {
  const dot = document.getElementById("server-dot");
  try {
    const h = await api("/health");
    dot.className = "server-dot ok";
    const s = await api(`${API}/system`);
    document.getElementById("server-time").textContent = time(s.now);
    return h;
  } catch {
    dot.className = "server-dot bad";
    document.getElementById("server-time").textContent = "서버 연결 안 됨";
    return null;
  }
}

document.getElementById("tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("button")?.dataset.tab;
  if (tab) show(tab);
});
document.getElementById("refresh").addEventListener("click", () => { checkServer(); show(); });
document.getElementById("store-select").addEventListener("change", (e) => {
  state.storeId = e.target.value;
  demo.index = -1;
  try { localStorage.setItem("dona-dev-store", state.storeId); } catch {}
  show();
});

content.addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  // 시연 탭 버튼은 휴대폰 틀을 살려 두려고 화면 전체를 다시 그리지 않는다
  // 화면 글 탭도 적던 칸을 살려 두려고 화면 전체를 다시 그리지 않는다
  if (button.closest("[data-uitext]")) {
    try {
      await onUiTextClick(button);
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
    return;
  }
  if (button.dataset.agentMode || button.dataset.run) {
    try {
      await onAgentsClick(button);
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
    return;
  }
  if (button.closest("[data-demo]")) {
    try {
      await onDemoClick(button);
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
    return;
  }
  const { pick, days, clock, polish, action } = button.dataset;
  try {
    if (pick) {
      state.storeId = pick;
      document.getElementById("store-select").value = pick;
      return show("analysis");
    }
    if (days) {
      state.usageDays = Number(days);
      return show();
    }
    if (button.id === "health") {
      const started = performance.now();
      const h = await checkServer();
      document.getElementById("health-result").textContent = h ? `정상 · ${Math.round(performance.now() - started)}ms` : "서버가 응답하지 않아요";
      return;
    }
    button.disabled = true;
    if (clock) await moveClock(clock);
    if (polish) {
      await api(`${API}/polish`, { method: "POST", body: JSON.stringify({ enabled: polish === "on" }) });
      toast(`문장 다듬기 ${polish === "on" ? "켬" : "끔"}`);
    }
    if (action === "recompute") {
      const r = await api(`${API}/recompute?store_id=${state.storeId}`, { method: "POST" });
      toast(`${r.store_id} 다시 계산 · ${r.seconds}초`);
    }
    if (action === "reset" && confirm("등록한 가게, 로그인 기록, 고친 설정, 계산 결과를 지울까요?")) {
      const r = await api("/dev/reset", { method: "POST" });
      toast(`초기화 · 지운 가게 ${r.removed_stores?.length ?? 0}곳`);
      await loadStores();
    }
    await checkServer();
    show();
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
});

// 주소 끝 #탭이름 을 바꾸면 그 탭으로 (링크로 탭을 열 수 있게)
window.addEventListener("hashchange", () => {
  const tab = tabOf(location.hash.slice(1));
  if (tab && tab !== state.tab) show(tab);
});

content.addEventListener("input", (e) => {
  if (e.target.closest("[data-uitext]")) onUiTextInput(e.target);
});

content.addEventListener("change", (e) => {
  if (e.target.id === "ut-file") return utImportFile(e.target).catch((error) => toast(error.message));
  if (e.target.id === "demo-polish") {
    demo.polish = e.target.checked;
    try { localStorage.setItem(DEMO_POLISH_KEY, demo.polish ? "on" : "off"); } catch {}
    return toast(`단계마다 문장 다듬기 ${demo.polish ? "켬" : "끔"}`);
  }
  if (e.target.id !== "demo-app-url") return;
  demo.appUrl = demoAppUrlOf(e.target.value.trim() || DEMO_APP_DEFAULT);
  e.target.value = demo.appUrl;
  try { localStorage.setItem(DEMO_APP_KEY, demo.appUrl); } catch {}
  toast(`앱 주소 ${demo.appUrl}`);
});

(async function start() {
  // 주소 끝의 #analysis 같은 탭 이름이 있으면 그 탭부터 연다. 없으면 지난번에 본 탭
  const fromHash = tabOf(location.hash.slice(1));
  if (fromHash) state.tab = fromHash;
  else try { state.tab = tabOf(localStorage.getItem("dona-dev-tab")) || state.tab; } catch {}
  await checkServer();
  await loadStores();
  show();
  setInterval(checkServer, 30000);
})();

// ── 탭: 평가 (server/db/app_data/harness_eval 결과 폴더) ──
// 평가 스위트(python -m Harness.evals …)가 남긴 result.json 을 본다. 운영 기록(AI·에이전트 탭)과 섞지 않는다.
// 맨 위 질문 1~5 카드(scorecard) → 실행 목록 → 고른 실행의 질문별 그래프(+ "표로 보기") → 사례 격자·사례 → 짝 비교·심판 검증.
// 그래프는 라이브러리 없이 SVG·HTML 로 그린다. 집계는 서버(eval_reader.charts)가 하고 여기서는 그리기만 한다.
// 색: 시스템(정체) = --viz-1~4 를 이름에 고정, 상태 = --viz-good·warning·serious·critical(늘 글자와 함께), 크기 = 파랑 단계.
// 글자·축·격자는 대시보드 색 변수(--ink, --ink-2, --ink-3, --line, --surface, --bg)를 써서 테마를 따른다.

const evalView = { id: null, system: "", failedOnly: true, offset: 0, metric: null, open: new Set(), steps: {}, set: null, focus: null, picks: {} };
const EVAL_PAGE = 30;
const EVAL_QUESTIONS = {
  1: "질문 1. 리뷰를 바르게 가르는가",
  2: "질문 2. 글을 믿을 수 있는가",
  3: "질문 3. 안전장치가 제 역할을 하는가",
  4: "질문 4. 에이전트가 믿을 만하게 동작하는가",
  5: "질문 5. 비용과 시간",
};
const VIZ_SLOT = { A: 1, B: 2, S: 3, R: 3, rule: 1, hcx: 2, voice: 3, regex: 1, critic: 2, judge_tools: 3, judge_thinking: 4, "rule+judge": 2 };
const VIZ_STATUS_INK = { warning: "#0b0b0b", neutral: "#0b0b0b" }; // 밝은 칸 안 글자는 검정, 나머지 흰색 (두 모드 같음)
const VIZ_SEQ = ["--viz-seq-0", "--viz-seq-1", "--viz-seq-2", "--viz-seq-3", "--viz-seq-4", "--viz-seq-5", "--viz-seq-6", "--viz-seq-7"];
const SOURCE_NAMES = { AGENT: "에이전트", SINGLE_CALL: "단일 호출", FALLBACK: "물러나기", TEMPLATE: "템플릿", NONE: "출력 없음" };
// 결과 구성: 생성 성공이면 적합 여부, 아니면 실패 원인 (서버 Harness/evals/fail_cause)
const OUTCOME_NAMES = { success_fit: "생성 성공 · 적합", success_unfit: "생성 성공 · 부적합", transport: "전송 실패",
  rejected: "검사 거절 상한", budget: "시간·호출·단계 상한", no_submit: "제출 없음", other: "기타" };
// 화면에는 코드 이름 대신 뜻 이름을 쓴다 (코드 이름은 마우스를 올리면 보인다)
const SYSTEM_NAMES = { A: "A 단일 에이전트", B: "B 하네스", S: "S 지금 서비스(기준선)", R: "R 규칙 한 줄(기준선)", rule: "규칙", hcx: "HCX 분류기", voice: "음성 규칙", regex: "금지어 정규식",
  critic: "LLM 검토기", judge_tools: "심판(도구)", judge_thinking: "심판(추론)", "rule+judge": "규칙+판정 에이전트" };
const COND_NAMES = { fact: "사실", policy: "정책", core: "핵심 내용", response: "응대", format: "형식", consistency: "일관성" };
const KIND_NAMES = { normal: "정상 답글", compensation: "보상 약속", fabricated: "지어낸 가게 사정", blame: "손님·남 탓", memory: "기억하는 척",
  swap: "다른 리뷰 답", off_topic: "엉뚱한 답", no_fix: "고칠 점 없음" };
const SET_NAMES = { all: "전체", gold: "정답지 답글", critic_cases: "검토기 사례", balanced: "균형 세트", full: "전체 세트" };
const SUITE_NAMES = { label: "리뷰 분류", guards: "안전장치", reply: "답글", batch: "진단·묶음 조율", intent: "뜻 판정" };
const nm = (dict, key) => dict[key] ?? key;
const sysName = (s) => nm(SYSTEM_NAMES, s);
const UNIT_NAMES = { seconds: "초", calls: "번", tokens: "토큰", cases: "건" };
const unitName = (u) => nm(UNIT_NAMES, u ?? "");
// 지표 이름 속 괄호의 코드 이름(위반 종류·조건)도 뜻 이름으로: "놓침률 (compensation)" → "놓침률 (보상 약속)"
const metricName = (name) => String(name ?? "").replace(/\(([a-z_]+)\)/g, (all, k) => `(${KIND_NAMES[k] ?? COND_NAMES[k] ?? k})`);

const vizColor = (system, systems = []) => `var(--viz-${VIZ_SLOT[system] ?? ((Math.max(0, systems.indexOf(system)) % 4) + 1)})`;
const vizPct = (v) => (v == null ? "-" : `${Math.round(v * 1000) / 10}%`);
const vizSeqVar = (rate) => `var(${VIZ_SEQ[rate == null ? 0 : Math.min(VIZ_SEQ.length - 1, Math.round(rate * (VIZ_SEQ.length - 1)))]})`;
const vizSeqInk = (rate) => (rate != null && rate >= 0.5 ? "#ffffff" : "#0b0b0b");
const vizFrac = (m) => (m && m.denominator != null ? `${m.numerator}/${m.denominator}` : "");

function vizLegend(systems) {
  if (!systems.length) return "";
  return `<div class="viz-legend">${systems.map((s) => `<span><i style="background:${vizColor(s, systems)}"></i>${esc(sysName(s))}</span>`).join("")}</div>`;
}

function vizDetails(inner, label = "표로 보기") {
  return inner ? `<details class="viz-details"><summary>${esc(label)}</summary>${inner}</details>` : "";
}

function vizBlock(title, note, body) {
  return body ? `<div class="viz-block"><h3>${esc(title)}${note ? ` <span class="muted">${esc(note)}</span>` : ""}</h3>${body}</div>` : "";
}

// ── 값 글자 ──

function evalValue(m) {
  if (!m) return '<span class="muted">-</span>';
  if (m.value === null || m.value === undefined) return `<span class="muted">해당 없음</span>${m.note ? ` <span class="muted small">${esc(m.note)}</span>` : ""}`;
  const shown = m.unit === "ratio" ? vizPct(m.value) : `${Number.isInteger(m.value) ? m.value : Number(m.value).toFixed(2)}${m.unit && m.unit !== "f1" ? ` ${esc(unitName(m.unit))}` : ""}`;
  const frac = m.denominator !== null && m.denominator !== undefined ? ` <span class="muted small">${m.numerator}/${m.denominator}</span>` : "";
  return `<b class="num">${shown}</b>${frac}`;
}

function evalDiff(a, b) {
  if (!a || !b || a.value == null || b.value == null) return '<span class="muted">-</span>';
  const d = b.value - a.value;
  if (Math.abs(d) < 1e-9) return '<span class="tag">B−A 같음</span>';
  const good = (d > 0) === (a.higher_is_better !== false);
  const shown = a.unit === "ratio" ? `${d > 0 ? "+" : ""}${(d * 100).toFixed(1)}%p` : `${d > 0 ? "+" : ""}${d.toFixed(2)}`;
  return `<span class="tag ${good ? "ok" : "warn"}">${good ? "▲" : "▼"} B−A ${shown}</span>`;
}

// ── 맨 위: 질문 1~5 카드 (서버 Harness/evals/scorecard 와 summary 명령이 같은 계산) ──
// 지표마다 그 스위트의 가장 최근 실행이 기본, 드롭다운으로 바꾼다(evalView.picks). 값·분자/분모·95% 구간(사례 단위)·목표와 통과·
// 결과 폴더·커밋·시각·지표 id 를 보인다. 분모 10 미만은 "표본 부족", 결과가 없으면 "안 돌림"(회색), 통과 배지는 표본이 충분할 때만.

function scPct(v) { return v == null ? "-" : `${(Math.round(v * 1000) / 10).toFixed(1)}%`; }
function scSec(v) { return v == null ? "-" : `${Number(v) < 10 ? Number(v).toFixed(2) : Number(v).toFixed(1)}초`; }

function scBadge(item, cell) {
  if (cell.status === "not_run") return '<span class="viz-goal none sc-gray">안 돌림</span>';
  if (cell.status === "too_few") return `<span class="viz-goal none" title="분모(또는 잰 수)가 10 미만">표본 부족</span>`;
  if (cell.passed === true) return `<span class="viz-goal pass" title="목표 ${esc(item.target)}">✓ 목표 통과</span>`;
  if (cell.passed === false) return `<span class="viz-goal fail" title="목표 ${esc(item.target)}">✗ 목표 미달</span>`;
  return '<span class="viz-goal none">– 기준 없음</span>';
}

function scValue(item, cell) {
  if (cell.status === "not_run") return '<span class="sc-gray">안 돌림</span>';
  if (item.kind === "latency") {
    const shown = `p50 <b class="num">${scSec(cell.p50)}</b> · p95 <b class="num">${scSec(cell.p95)}</b>`;
    return `${cell.status === "too_few" ? '<span class="muted">표본 부족</span> ' : ""}<span class="${cell.status === "too_few" ? "muted" : ""}">${shown}</span> <span class="muted small">n=${num(cell.n)}</span>`;
  }
  if (item.kind === "f1") return `<b class="num">${Number(cell.value).toFixed(2)}</b> <span class="muted small">F1 (구간 없음)</span>`;
  const frac = `<span class="muted small">${cell.numerator}/${cell.denominator}${cell.run_fraction ? ` 사례 · 회차 합 ${esc(cell.run_fraction)}` : ""}</span>`;
  if (cell.status === "too_few") return `<span class="muted">표본 부족</span> ${frac}`;
  const ci = cell.interval ? ` <span class="muted small">95% ${scPct(cell.interval[0])}~${scPct(cell.interval[1])}</span>` : ' <span class="muted small">구간 없음</span>';
  return `<b class="num">${scPct(cell.value)}</b> ${frac}${ci}`;
}

function scDiff(item, cell) {
  if (cell.baseline_diff == null) return "";
  const d = cell.baseline_diff;
  const good = Math.abs(d) < 1e-9 || (d < 0) === item.lower_better;
  const shown = item.kind === "ratio" ? `${d > 0 ? "+" : ""}${(d * 100).toFixed(1)}%p` : item.kind === "latency" ? `${d > 0 ? "+" : ""}${d.toFixed(2)}초` : `${d > 0 ? "+" : ""}${d.toFixed(2)}`;
  return `<span class="tag ${good ? "ok" : "warn"}" title="기준점 ${esc(cell.baseline_folder ?? "")}">기준점 대비 ${shown}</span>`;
}

function scSource(cell) {
  if (cell.status === "not_run") return "";
  return `<span class="sc-src muted small"><span class="mono">${esc(cell.folder ?? "-")}</span> · 커밋 <span class="mono">${esc(cell.commit ?? "-")}${cell.dirty ? "+수정" : ""}</span> · ${esc(time(cell.started_at))}${cell.note ? ` · ${esc(cell.note)}` : ""}${cell.recomputed ? " · cases 에서 다시 셈" : ""}</span>`;
}

function scPick(item) {
  if (item.options.length < 2) return "";
  return `<select class="sc-pick" data-eval-scpick="${esc(item.key)}" title="이 지표에 쓸 실행">
    <option value="">가장 최근 실행</option>${item.options.map((o) => `<option value="${esc(o.folder)}" ${o.folder === item.picked ? "selected" : ""}>${esc(time(o.started_at))} · ${esc(o.commit ?? "-")}${o.baseline ? " · 기준점" : ""}</option>`).join("")}</select>`;
}

function scHead(item) {
  const dir = item.lower_better ? "↓ 낮을수록 좋음" : "↑ 높을수록 좋음";
  return `<div class="sc-item-head"><b>${esc(item.label)}</b> <span class="viz-dir">${dir}${item.target ? ` · 목표 ${esc(item.target)}` : ""}</span>
    <span class="sc-id mono">${esc(item.metric)}${Object.entries(item.keys).map(([k, v]) => ` ${esc(k)}=${esc(v)}`).join("")}</span>${scPick(item)}</div>`;
}

function scCellRow(item, cell, systems) {
  return `<div class="sc-row ${cell.status === "not_run" ? "sc-off" : ""}">
    <span class="viz-sys"><i style="background:${vizColor(cell.system, systems)}"></i>${esc(sysName(cell.system))}</span>
    <span>${scValue(item, cell)}</span>
    <span class="sc-badges">${scBadge(item, cell)}${scDiff(item, cell)}</span>
    ${scSource(cell)}</div>`;
}

function scItem(item) {
  const systems = item.cells.map((c) => c.system);
  if (item.optional && item.cells.every((c) => c.status === "not_run")) {
    return `<div class="sc-item"><div class="sc-item-head"><b>${esc(item.label)}</b> <span class="muted small">${esc(item.note || "결과 없음")} — 사람 표본 없음</span> <span class="sc-id mono">${esc(item.metric)}</span></div></div>`;
  }
  return `<div class="sc-item">${scHead(item)}${item.cells.map((c) => scCellRow(item, c, systems)).join("")}</div>`;
}

// 강도 0~3 별 뜻 정확도: 시스템마다 선 하나 (끝에 이름), 점마다 95% 구간 세로줄
function scNoiseLine(items) {
  const systems = [...new Set(items.flatMap((it) => it.cells.map((c) => c.system)))];
  const W = 640, H = 230, L = 46, R = 130, T = 14, B = 34;
  const x = (level) => L + (level / 3) * (W - L - R);
  const y = (v) => T + (1 - v) * (H - T - B);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" class="viz-gridline"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="viz-axis">${v * 100}%</text>`).join("");
  const xs = [0, 1, 2, 3].map((l) => `<text x="${x(l)}" y="${H - 12}" text-anchor="middle" class="viz-axis">강도 ${l}</text>`).join("");
  let drawn = 0;
  const lines = systems.map((s) => {
    const color = vizColor(s, systems);
    const pts = items.map((it) => [it.keys.noise, it.cells.find((c) => c.system === s)]).filter(([, c]) => c && c.status !== "not_run" && c.value != null);
    if (!pts.length) return "";
    drawn += 1;
    const path = pts.map(([l, c], k) => `${k ? "L" : "M"}${x(l).toFixed(1)},${y(c.value).toFixed(1)}`).join(" ");
    const marks = pts.map(([l, c]) => `${c.interval ? `<line x1="${x(l)}" y1="${y(c.interval[0])}" x2="${x(l)}" y2="${y(c.interval[1])}" style="stroke:${color}" stroke-width="1.5" opacity="0.6"/>` : ""}
      <circle cx="${x(l)}" cy="${y(c.value)}" r="4" style="fill:${c.status === "too_few" ? "var(--surface)" : color};stroke:${color}" stroke-width="2"><title>${esc(sysName(s))} 강도 ${l}: ${scPct(c.value)} (${c.numerator}/${c.denominator})${c.status === "too_few" ? " 표본 부족" : ""}</title></circle>`).join("");
    const [lastL, last] = pts[pts.length - 1];
    return `<path d="${path}" style="fill:none;stroke:${color}" stroke-width="2"/>${marks}<text x="${x(lastL) + 10}" y="${y(last.value) + 4}" class="viz-axis-ink" style="fill:${color}">${esc(sysName(s))} ${scPct(last.value)}</text>`;
  }).join("");
  if (!drawn) return '<div class="muted small sc-gray">안 돌림 — <span class="mono">python -m Harness.evals noise</span></div>';
  const missing = systems.filter((s) => !items.some((it) => it.cells.some((c) => c.system === s && c.status !== "not_run")));
  return `${missing.length ? `<div class="muted small sc-gray">안 돌림: ${missing.map((s) => esc(sysName(s))).join(", ")}</div>` : ""}<svg class="viz-svg sc-line" viewBox="0 0 ${W} ${H}" role="img" aria-label="모의 받아쓰기 오류 강도별 뜻 정확도">${grid}${xs}${lines}</svg>`;
}

// 시간 막대: 지표·시스템마다 p50(진한 막대)과 p95(옅은 막대), 목표선. 한 그림 안에서는 같은 축
function scLatencyBars(items) {
  const rows = items.flatMap((it) => it.cells.map((c) => ({ it, c, systems: it.cells.map((x) => x.system) })));
  const measured = rows.filter((r) => r.c.status !== "not_run");
  if (!measured.length) return "";
  const max = Math.max(...measured.map((r) => r.c.p95 ?? 0), ...items.map((it) => it.target_value ?? 0), 1e-6) * 1.12;
  const W = 760, L = 210, R = 150, barH = 9, rowH = 34, T = 6, H = T + rows.length * rowH + 22;
  const x = (v) => L + (v / max) * (W - L - R);
  const body = rows.map((r, i) => {
    const top = T + i * rowH;
    const color = vizColor(r.c.system, r.systems);
    const label = `<text x="${L - 8}" y="${top + 15}" text-anchor="end" class="viz-axis-ink">${esc(r.it.label)} · ${esc(sysName(r.c.system))}</text>`;
    if (r.c.status === "not_run") return `${label}<text x="${L + 4}" y="${top + 15}" class="viz-axis">안 돌림</text>`;
    const p50 = r.c.p50 ?? 0, p95 = r.c.p95 ?? 0;
    const target = r.it.target_value != null ? `<line x1="${x(r.it.target_value)}" y1="${top + 1}" x2="${x(r.it.target_value)}" y2="${top + rowH - 6}" class="viz-budget"/>
      <text x="${x(r.it.target_value) + 3}" y="${top + rowH - 7}" class="viz-axis">목표 ${r.it.target_value}초</text>` : "";
    return `${label}
      <rect x="${L}" y="${top + 3}" width="${Math.max(1, x(p50) - L)}" height="${barH}" style="fill:${color}"><title>p50 ${scSec(p50)}</title></rect>
      <rect x="${L}" y="${top + 3 + barH + 2}" width="${Math.max(1, x(p95) - L)}" height="${barH}" style="fill:${color}" opacity="0.4"><title>p95 ${scSec(p95)}</title></rect>
      <text x="${x(p50) + 4}" y="${top + 11}" class="viz-axis">p50 ${scSec(p50)}</text>
      <text x="${x(p95) + 4}" y="${top + 22}" class="viz-axis">p95 ${scSec(p95)}${r.c.status === "too_few" ? " · 표본 부족" : ""}</text>${target}`;
  }).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max * f).map((v) => `<line x1="${x(v)}" y1="${T}" x2="${x(v)}" y2="${H - 20}" class="viz-gridline"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle" class="viz-axis">${scSec(v)}</text>`).join("");
  return `<svg class="viz-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="응답 시간 p50·p95">${ticks}${body}</svg>`;
}

// 한 쌍 (질문 3·4): 시스템마다 두 지표를 나란히
function scPair(items) {
  const [a, b] = items;
  const systems = [...new Set([...a.cells, ...b.cells].map((c) => c.system))];
  const cellOf = (it, s) => it.cells.find((c) => c.system === s) ?? { system: s, status: "not_run" };
  const rows = systems.map((s) => {
    const ca = cellOf(a, s), cb = cellOf(b, s);
    const off = ca.status === "not_run" && cb.status === "not_run";
    const side = (it, c) => `<div class="sc-pair-cell"><div>${scValue(it, c)}</div><div class="sc-badges">${scBadge(it, c)}${scDiff(it, c)}</div>${scSource(c)}</div>`;
    return `<div class="sc-pair-row ${off ? "sc-off" : ""}"><span class="viz-sys"><i style="background:${vizColor(s, systems)}"></i>${esc(sysName(s))}</span>${side(a, ca)}${side(b, cb)}</div>`;
  }).join("");
  return `<div class="sc-pair"><div class="sc-pair-row sc-pair-head"><span></span><div>${scHead(a)}</div><div>${scHead(b)}</div></div>${rows}</div>`;
}

function scSmallLine(items) {
  if (!items.length) return "";
  const systems = [...new Set(items.flatMap((it) => it.cells.map((c) => c.system)))];
  return `<div class="sc-small muted small">${systems.map((s) => `<div>${esc(sysName(s))}: ${items.map((it) => {
    const c = it.cells.find((x) => x.system === s);
    const v = !c || c.status === "not_run" ? "안 돌림" : c.status === "too_few" ? `표본 부족 (${c.numerator}/${c.denominator})` : `${scPct(c.value)} (${c.numerator}/${c.denominator})`;
    return `${esc(it.label)} ${v} <span class="mono">${esc(it.metric)}</span>`;
  }).join(" · ")}</div>`).join("")}</div>`;
}

function scGroup(name, items, extra = "") {
  const big = items.filter((it) => !it.small);
  const small = items.filter((it) => it.small);
  let drawn;
  if (big.length && big.every((it) => it.chart === "line")) {
    drawn = `<div class="muted small">점 = 정확도, 세로줄 = 95% 구간 · 빈 점 = 표본 부족</div>${scNoiseLine(big)}${vizDetails(big.map(scItem).join(""), "강도별 값 보기")}`;
  } else if (big.length === 2 && big.every((it) => it.chart === "pair")) {
    drawn = scPair(big);
  } else {
    const lat = big.filter((it) => it.kind === "latency");
    const rest = big.filter((it) => it.kind !== "latency");
    drawn = (lat.length ? scLatencyBars(lat) + lat.map(scItem).join("") : "") + rest.map(scItem).join("");
  }
  const note = [...new Set(items.filter((it) => !it.optional).map((it) => it.note).filter(Boolean))].join(" · ");
  return `<div class="viz-block"><h3>${esc(name)}${note ? ` <span class="muted">${esc(note)}</span>` : ""}</h3>${drawn}${scSmallLine(small)}${extra}</div>`;
}

// 체감 시간: 브리핑 단계 서버 처리 p50 + TTS 첫 소리 p50 (둘 다 잰 시스템이 있을 때만)
function scPerceived(items) {
  const turn = items.find((it) => it.key === "q5.turn_briefing");
  const tts = items.find((it) => it.key === "q5.tts_first");
  const ttsCell = tts?.cells.find((c) => c.status !== "not_run");
  const turnCells = (turn?.cells ?? []).filter((c) => c.status !== "not_run");
  if (!ttsCell || !turnCells.length) return '<div class="muted small">체감 시간 = 서버 처리 시간 + TTS 첫 소리 (둘 다 잰 결과가 있을 때 더해 보여요)</div>';
  return `<div class="sc-small small">${turnCells.map((c) => `<div>체감 시간 p50 ≈ <b>${scSec(c.p50 + ttsCell.p50)}</b>
    <span class="muted">= 브리핑 단계 서버 처리 ${scSec(c.p50)} (${esc(sysName(c.system))}) + TTS 첫 소리 ${scSec(ttsCell.p50)} · 네트워크 제외</span></div>`).join("")}</div>`;
}

function evalScorecard(sc) {
  if (!sc?.questions) return "";
  return `<div class="sc-cards">${sc.questions.map((q) => {
    const groups = [];
    for (const it of q.items) {
      let g = groups.find((x) => x.name === it.group);
      if (!g) groups.push(g = { name: it.group, items: [] });
      g.items.push(it);
    }
    return `<div class="card sc-card"><h2>${esc(q.title)}</h2>${groups.map((g) => scGroup(g.name, g.items, g.items.some((it) => it.key === "q5.tts_first") ? scPerceived(q.items) : "")).join("")}</div>`;
  }).join("")}</div>`;
}

// ── 실행 목록 ──

function vizHeadline(r) {
  return r.headline.map((m) => {
    const bar = m.unit === "ratio" && m.value != null
      ? `<span class="viz-mini"><span style="width:${m.value * 100}%;background:${vizColor(m.system ?? "-", r.systems)}"></span></span>` : "";
    return `<span class="viz-head-item"><span class="muted small" title="${esc(m.id)}">${esc(m.system ? sysName(m.system) : "")} ${esc(metricName(m.name))}</span>${bar}${evalValue(m)}</span>`;
  }).join("");
}

function evalRunRow(r) {
  return `<div class="call eval-run ${r.id === evalView.id ? "picked" : ""}"><div class="call-head">
      <button class="btn-outline small" data-eval-pick="${esc(r.id)}">${r.id === evalView.id ? "보는 중" : "보기"}</button>
      <span class="mono">${esc(time(r.started_at))}</span><b>${esc(nm(SUITE_NAMES, r.suite))}</b>
      ${r.baseline ? '<span class="tag brand">기준점</span>' : ""}${r.legacy ? '<span class="tag">예전 형식</span>' : ""}
      <span class="tag">${esc(r.systems.map(sysName).join(", ") || "-")}</span>
      <span class="mono muted small">${esc(r.commit ?? "")}</span><span class="muted small">사례 ${num(r.cases)}</span>
    </div><div class="call-body">${vizHeadline(r) || '<span class="muted">지표 없음</span>'}</div></div>`;
}

// ── 지표: 한 줄 점 그림 + 표 ──

function vizMetricRows(rows, systems, ab) {
  const keys = [...new Set(rows.map((m) => m.key))];
  return keys.map((key) => {
    const group = rows.filter((m) => m.key === key);
    const first = group[0];
    const fixed = first.unit === "ratio" || first.unit === "f1";
    const max = fixed ? 1 : Math.max(...group.map((m) => m.value ?? 0), 1e-9);
    const present = systems.filter((s) => group.some((m) => (m.system ?? "-") === s));
    const cell = (s) => group.find((m) => (m.system ?? "-") === s);
    const pos = (m) => Math.max(0, Math.min(1, m.value / max)) * 100;
    const valued = present.map(cell).filter((m) => m.value != null);
    const span = valued.length > 1 ? [Math.min(...valued.map(pos)), Math.max(...valued.map(pos))] : null;
    const dots = present.map((s, i) => {
      const m = cell(s);
      if (m.value == null) return "";
      const offset = (i - (present.length - 1) / 2) * 5;
      return `<span class="viz-dot" style="left:${pos(m)}%;top:calc(50% + ${offset}px);background:${vizColor(s, systems)}"
        title="${esc(sysName(s))} · ${esc(metricName(first.name))}: ${esc(m.unit === "ratio" ? vizPct(m.value) : m.value)}${m.denominator != null ? ` (${vizFrac(m)})` : ""}${m.note ? ` · ${esc(m.note)}` : ""}"></span>`;
    }).join("");
    const values = present.map((s) => `<span class="viz-v"><i style="background:${vizColor(s, systems)}"></i>${present.length > 1 ? `${esc(sysName(s))} ` : ""}${evalValue(cell(s))}</span>`).join("");
    const scale = fixed ? "" : `<span class="viz-scale-max muted small">${esc(Number.isInteger(max) ? max : max.toFixed(1))} ${esc(unitName(first.unit))}</span>`;
    return `<div class="viz-dotrow">
      <div class="viz-dot-name"><b title="${esc(key)}">${esc(metricName(first.name))}</b>
        <span class="viz-dir">${first.higher_is_better === false ? "↓ 낮을수록 좋음" : "↑ 높을수록 좋음"}</span></div>
      <div class="viz-dot-track">${span ? `<span class="viz-span" style="left:${span[0]}%;width:${span[1] - span[0]}%"></span>` : ""}${dots}${scale}</div>
      <div class="viz-dot-values">${values}${ab ? evalDiff(cell("A"), cell("B")) : ""}</div>
      <button class="btn-outline small" data-eval-metric="${esc(key)}">추세</button></div>`;
  }).join("");
}

function evalMetricTable(rows, ab) {
  const systems = [...new Set(rows.map((m) => m.system ?? "-"))];
  const keys = [...new Set(rows.map((m) => m.key))];
  const cell = (key, s) => rows.find((m) => m.key === key && (m.system ?? "-") === s);
  const headers = ["지표", ...systems.map(esc), ...(ab ? ["차이 (B−A)"] : []), "좋은 방향"];
  return table(headers, keys.map((key) => {
    const first = rows.find((m) => m.key === key);
    return [`<span title="${esc(key)}">${esc(metricName(first.name))}</span>`, ...systems.map((s) => evalValue(cell(key, s))),
      ...(ab ? [evalDiff(cell(key, "A"), cell(key, "B"))] : []), first.higher_is_better === false ? "낮을수록 좋음" : "높을수록 좋음"];
  }));
}

// ── 질문 1: 재현율·정밀도 막대, 혼동 행렬 ──

function vizRecallPrecision(rp, systems) {
  if (!rp) return "";
  const set = rp.sets[evalView.set] ? evalView.set : rp.default;
  const rows = rp.sets[set];
  const names = Object.keys(rows);
  const bar = (s, label, m) => `<div class="viz-hbar" title="${esc(sysName(s))} ${esc(label)} ${m ? `${vizPct(m.value)} (${vizFrac(m)})` : "-"}">
      <span class="small muted">${esc(label)}</span>
      <span class="viz-track">${m?.value == null ? "" : `<span class="viz-fill" style="width:${m.value * 100}%;background:${vizColor(s, names)}"></span>`}</span>
      <span class="num small">${m?.value == null ? "-" : vizPct(m.value)} <span class="muted">${esc(vizFrac(m))}</span></span></div>`;
  const body = names.map((s) => `<div class="viz-group"><div class="viz-sys"><i style="background:${vizColor(s, names)}"></i><b>${esc(sysName(s))}</b></div>
      ${bar(s, "재현율", rows[s].recall)}${bar(s, "정밀도", rows[s].precision)}</div>`).join("");
  const tableHtml = table(["분류기", "재현율", "정밀도"], names.map((s) => [esc(sysName(s)), evalValue(rows[s].recall && { ...rows[s].recall }), evalValue(rows[s].precision && { ...rows[s].precision })]));
  return vizBlock(`아쉬운 리뷰 재현율·정밀도 · ${nm(SET_NAMES, set)}`, "0~100%, 막대 끝 글자가 값", vizLegend(names) + body + vizDetails(tableHtml));
}

function vizConfusion(confusion) {
  if (!confusion) return "";
  const set = confusion.sets[evalView.set] ? evalView.set : confusion.default;
  const tables = confusion.sets[set] ?? {};
  const names = Object.keys(tables);
  const panels = names.map((system) => {
    const rows = tables[system];
    const truths = Object.keys(rows);
    const order = (p) => { const i = truths.findIndex((t) => t.toLowerCase() === p.toLowerCase()); return i < 0 ? 99 : i; };
    const preds = [...new Set(truths.flatMap((t) => Object.keys(rows[t])))].sort((a, b) => order(a) - order(b));
    const grid = `<div class="viz-cm" style="grid-template-columns:96px repeat(${preds.length}, 1fr)">
      <span class="muted small">정답 \\ 예측</span>${preds.map((p) => `<span class="muted small viz-cm-col">${esc(p)}</span>`).join("")}
      ${truths.map((t) => {
        const total = Object.values(rows[t]).reduce((a, b) => a + b, 0);
        return `<span class="small">${esc(t)} <span class="muted">${total}</span></span>` + preds.map((p) => {
          const n = rows[t][p] ?? 0;
          const rate = total ? n / total : null;
          const hit = p.toLowerCase() === t.toLowerCase();
          return `<span class="viz-hm-cell${hit ? " mark" : ""}" style="background:${vizSeqVar(rate)};color:${vizSeqInk(rate)}" title="정답 ${esc(t)} → ${esc(p)}: ${n}/${total}"><b>${n}</b></span>`;
        }).join("");
      }).join("")}</div>`;
    return `<div class="viz-cm-panel"><div class="viz-sys"><i style="background:${vizColor(system, names)}"></i><b>${esc(sysName(system))}</b></div>${grid}</div>`;
  }).join("");
  const tableHtml = names.map((system) => {
    const rows = tables[system];
    const preds = [...new Set(Object.values(rows).flatMap((r) => Object.keys(r)))];
    return `<div class="small"><b>${esc(sysName(system))}</b></div>` + table(["정답 \\ 예측", ...preds.map(esc)], Object.keys(rows).map((t) => [esc(t), ...preds.map((p) => num(rows[t][p] ?? 0))]));
  }).join("");
  return vizBlock(`감정 혼동 행렬 · ${nm(SET_NAMES, set)}`, "칸 = 건수 · 진할수록 그 정답 중 많이 · 테두리 칸이 맞힌 것", `<div class="viz-cm-wrap">${panels}</div>` + vizDetails(tableHtml));
}

// ── 질문 2: 조건별 통과율 덤벨, 결과 구성 ──

function vizDumbbell(cond, systems) {
  if (!cond) return "";
  const names = systems.filter((s) => cond.systems[s]);
  if (!names.length) return "";
  const rows = cond.conditions.map((c, rowIndex) => {
    const cells = names.map((s) => ({ s, v: cond.systems[s]?.[c] })).filter((x) => x.v && x.v.rate != null);
    const rates = cells.map((x) => x.v.rate * 100);
    const line = rates.length > 1 ? `<span class="viz-span" style="left:${Math.min(...rates)}%;width:${Math.max(...rates) - Math.min(...rates)}%"></span>` : "";
    const dots = cells.map((x, i) => `<span class="viz-dot" style="left:${x.v.rate * 100}%;top:calc(50% + ${(i - (cells.length - 1) / 2) * 5}px);background:${vizColor(x.s, names)}"
        title="${esc(sysName(x.s))} ${esc(c)} 통과 ${x.v.pass}/${x.v.total}${x.v.unknown ? `, 판단 불가 ${x.v.unknown}` : ""}"></span>`).join("");
    const labels = cells.map((x) => `<span class="viz-v"><i style="background:${vizColor(x.s, names)}"></i>${esc(sysName(x.s))} <b class="num">${vizPct(x.v.rate)}</b> <span class="muted small">${x.v.pass}/${x.v.total}</span></span>`).join("");
    return `<div class="viz-dbrow"><span class="viz-db-name" title="${esc(c)}"><b>${esc(nm(COND_NAMES, c))}</b></span>
      <div class="viz-dot-track">${rowIndex === cond.conditions.length - 1 ? '<span class="viz-tick" style="left:0">0</span><span class="viz-tick" style="left:50%">50%</span><span class="viz-tick" style="left:100%">100%</span>' : ""}${line}${dots}</div>
      <div class="viz-dot-values">${labels}</div></div>`;
  }).join("");
  const tableHtml = table(["조건", ...names.map((s) => esc(sysName(s)))], cond.conditions.map((c) => [esc(nm(COND_NAMES, c)), ...names.map((s) => {
    const v = cond.systems[s]?.[c];
    return v ? `${vizPct(v.rate)} <span class="muted small">${v.pass}/${v.total}${v.unknown ? ` · 판단 불가 ${v.unknown}` : ""}</span>` : "-";
  })]));
  return vizBlock("조건별 통과율", "점 = 시스템, 회색 선 = A↔B 차이, 축 0~100%", vizLegend(names) + rows + vizDetails(tableHtml));
}

function vizStack(rows, order, { nameOf, colorOf, inkOf }) {
  // rows: [{label, swatch, counts:{key:n}, total}] → 시스템마다 한 줄 누적 막대 (칸 안 비율, 2px 틈)
  const legend = `<div class="viz-legend">${order.map((o) => `<span><i style="background:${colorOf(o)}"></i>${esc(nameOf(o))}</span>`).join("")}</div>`;
  const body = rows.map((r) => {
    const total = r.total || Object.values(r.counts).reduce((a, b) => a + b, 0) || 1;
    const blocks = order.filter((o) => r.counts[o.key]).map((o) => {
      const share = r.counts[o.key] / total;
      return `<span class="viz-seg" style="flex:${r.counts[o.key]};background:${colorOf(o)};color:${inkOf(o)}" title="${esc(r.label)} · ${esc(nameOf(o))} ${r.counts[o.key]}/${total} (${vizPct(share)})">${share >= 0.08 ? vizPct(share) : ""}</span>`;
    }).join("");
    return `<div class="viz-mix-row"><span class="viz-sys">${r.swatch ? `<i style="background:${r.swatch}"></i>` : ""}${esc(r.label)}</span>
      <div class="viz-segbar">${blocks || '<span class="muted small">없음</span>'}</div><span class="muted small num">${total}건</span></div>`;
  }).join("");
  return legend + body;
}

function vizOutcomeMix(mix, source, systems) {
  if (!mix) return vizSourceMix(source, systems);
  const names = systems.filter((s) => mix.systems[s]);
  const rows = names.map((s) => ({ label: sysName(s), swatch: vizColor(s, names), counts: mix.systems[s] }));
  const order = mix.order.filter((o) => names.some((s) => mix.systems[s][o.key]));
  const chart = vizStack(rows, order, { nameOf: (o) => OUTCOME_NAMES[o.key] ?? o.key, colorOf: (o) => `var(--viz-${o.status})`, inkOf: (o) => VIZ_STATUS_INK[o.status] ?? "#ffffff" });
  const tableHtml = table(["시스템", ...order.map((o) => esc(OUTCOME_NAMES[o.key] ?? o.key))], names.map((s) => [esc(sysName(s)), ...order.map((o) => num(mix.systems[s][o.key] ?? 0))]))
    + (source ? `<div class="small muted" style="margin-top:8px">누가 답을 냈나 (source)</div>` + table(["시스템", ...source.order.map((o) => esc(SOURCE_NAMES[o.key] ?? o.key)), "전체"],
      systems.filter((s) => source.systems[s]).map((s) => [esc(sysName(s)), ...source.order.map((o) => num(source.systems[s].counts[o.key] ?? 0)), num(source.systems[s].total)])) : "");
  return vizBlock("결과 구성", "생성 성공은 적합 여부로, 실패는 원인으로 나눔 · 시스템마다 전체 사례 100% · 검사 통과·거절 비율과는 따로 센다", chart + vizDetails(tableHtml));
}

function vizSourceMix(mix, systems) {
  if (!mix) return "";
  const names = systems.filter((s) => mix.systems[s]);
  const rows = names.map((s) => ({ label: sysName(s), swatch: vizColor(s, names), counts: mix.systems[s].counts, total: mix.systems[s].total }));
  const order = mix.order;
  const chart = vizStack(rows, order, { nameOf: (o) => SOURCE_NAMES[o.key] ?? o.key, colorOf: (o) => `var(--viz-${o.status})`, inkOf: (o) => VIZ_STATUS_INK[o.status] ?? "#ffffff" });
  const tableHtml = table(["시스템", ...order.map((o) => esc(SOURCE_NAMES[o.key] ?? o.key)), "전체"], names.map((s) => [esc(sysName(s)), ...order.map((o) => num(mix.systems[s].counts[o.key] ?? 0)), num(mix.systems[s].total)]));
  return vizBlock("누가 답을 냈나", "source_rate · 시스템마다 전체 사례 100%", chart + vizDetails(tableHtml));
}

// ── 질문 3: (오거절, 놓침) 산점도, 판정기×위반 종류 놓침 히트맵 ──

function vizScatter(sc, systems) {
  if (!sc) return "";
  const set = sc.sets[evalView.set] ? evalView.set : sc.default;
  const points = sc.sets[set] ?? [];
  if (!points.length) return "";
  const names = points.map((p) => p.system);
  const W = 540, H = 300, L = 72, R = 20, T = 16, B = 44;
  const nice = (v) => Math.min(1, Math.ceil(Math.max(0.2, v * 1.1) * 10) / 10); // 10% 단위로 올린 축 끝
  const maxX = nice(Math.max(...points.map((p) => p.false_reject.value)));
  const maxY = nice(Math.max(...points.map((p) => p.missed.value)));
  const x = (v) => L + (v / maxX) * (W - L - R);
  const y = (v) => T + (1 - v / maxY) * (H - T - B);
  const ticks = (max) => { const step = max <= 0.5 ? 0.1 : 0.2; return Array.from({ length: Math.round(max / step) + 1 }, (_, k) => k * step); };
  const grid = ticks(maxX).map((v) => `<line x1="${x(v)}" y1="${T}" x2="${x(v)}" y2="${H - B}" class="viz-gridline"/><text x="${x(v)}" y="${H - B + 14}" text-anchor="middle" class="viz-axis">${vizPct(v)}</text>`).join("")
    + ticks(maxY).map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" class="viz-gridline"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="viz-axis">${vizPct(v)}</text>`).join("");
  const zone = `<rect x="${x(0)}" y="${T}" width="${x(Math.min(sc.target.false_reject, maxX)) - x(0)}" height="${H - T - B}" class="viz-zone"/>
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(Math.min(sc.target.false_reject, maxX))}" y2="${y(0)}" class="viz-zone-line"/>
    <text x="${x(0) + 6}" y="${T + 12}" class="viz-axis-ink">목표 구역: 놓침 0 · 오거절 ≤ ${vizPct(sc.target.false_reject)}</text>`;
  const dots = points.map((p) => `<circle cx="${x(p.false_reject.value)}" cy="${y(p.missed.value)}" r="7" style="fill:${vizColor(p.system, names)};stroke:var(--surface)" stroke-width="2">
      <title>${esc(sysName(p.system))} · 오거절 ${vizPct(p.false_reject.value)} (${vizFrac(p.false_reject)}) · 놓침 ${vizPct(p.missed.value)} (${vizFrac(p.missed)})</title></circle>
      <text x="${x(p.false_reject.value) + 10}" y="${y(p.missed.value) + 4}" class="viz-axis-ink">${esc(sysName(p.system))}</text>`).join("");
  const axes = `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle" class="viz-axis-ink">오거절률 (정상 답글을 막은 비율) →</text>
    <text x="12" y="${(T + H - B) / 2}" text-anchor="middle" class="viz-axis-ink" transform="rotate(-90 12 ${(T + H - B) / 2})">놓침률 (위반을 통과시킨 비율) →</text>`;
  const svg = `<svg class="viz-svg viz-scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="판정기별 오거절률과 놓침률">${grid}${zone}${axes}${dots}</svg>`;
  const tableHtml = table(["판정기", "오거절률", "놓침률"], points.map((p) => [esc(sysName(p.system)), evalValue({ ...p.false_reject }), evalValue({ ...p.missed })]));
  const sets = Object.keys(sc.sets);
  const setBar = sets.length > 1 ? `<div class="eval-filters"><span class="muted small">세트</span>${sets.map((name) => `<button class="btn-outline small ${name === set ? "on" : ""}" data-eval-set="${esc(name)}">${esc(nm(SET_NAMES, name))}</button>`).join("")}</div>` : "";
  return vizBlock(`판정기별 오거절·놓침 · ${nm(SET_NAMES, set)}`, "왼쪽 아래(초록 구역)에 가까울수록 좋음", setBar + vizLegend(names) + svg + vizDetails(tableHtml));
}

function vizHeatmap({ rows, cols, cell }) {
  const head = `<div class="viz-hm-row viz-hm-head" style="grid-template-columns:120px repeat(${cols.length}, minmax(64px, 1fr))"><span></span>${cols.map((c) => `<span title="${esc(c)}">${esc(nm(KIND_NAMES, c))}</span>`).join("")}</div>`;
  const body = rows.map((r) => `<div class="viz-hm-row" style="grid-template-columns:120px repeat(${cols.length}, minmax(64px, 1fr))">
      <span class="viz-sys">${r.swatch ? `<i style="background:${r.swatch}"></i>` : ""}${esc(r.name)}</span>
      ${cols.map((c) => {
        const v = cell(r.key, c);
        if (!v) return '<span class="viz-hm-cell empty">-</span>';
        return `<span class="viz-hm-cell" style="background:${vizSeqVar(v.rate)};color:${vizSeqInk(v.rate)}" title="${esc(r.name)} · ${esc(nm(KIND_NAMES, c))}: ${esc(v.tip)}"><b>${esc(v.main)}</b><small>${esc(v.sub)}</small></span>`;
      }).join("")}</div>`).join("");
  const scale = `<div class="viz-scale"><span>0%</span>${VIZ_SEQ.map((c) => `<i style="background:var(${c})"></i>`).join("")}<span>100%</span></div>`;
  return `${scale}<div class="viz-hm">${head}${body}</div>`;
}

function vizByKind(byKind, systems) {
  if (!byKind) return "";
  const names = systems.filter((s) => byKind.systems[s]);
  const rows = names.map((s) => ({ key: s, name: sysName(s), swatch: vizColor(s, names) }));
  const chart = vizHeatmap({
    rows, cols: byKind.kinds,
    cell: (s, k) => {
      const v = byKind.systems[s]?.[k];
      return v ? { rate: v.rate, main: `${v.missed}건`, sub: `${vizPct(v.rate)} · ${v.missed}/${v.total}${v.unknown ? ` ?${v.unknown}` : ""}`, tip: `놓침 ${v.missed} / ${v.total}, 판단 불가 ${v.unknown}` } : null;
    },
  });
  const tableHtml = table(["판정기", ...byKind.kinds.map((k) => esc(nm(KIND_NAMES, k)))], names.map((s) => [esc(sysName(s)), ...byKind.kinds.map((k) => {
    const v = byKind.systems[s]?.[k];
    return v ? `${v.missed}/${v.total}` : "-";
  })]));
  return vizBlock("판정기 × 위반 종류 놓침", "칸 = 놓친 건수 · 진할수록 많이 놓침", chart + vizDetails(tableHtml));
}

// ── 질문 4: 3회 통과 분포, batch ✓✗ 격자, 거절 이유 순위 ──

function vizPassDistribution(dist, systems) {
  if (!dist) return "";
  const names = systems.filter((s) => dist.systems[s]);
  const order = Array.from({ length: dist.runs + 1 }, (_, k) => ({ key: k, rate: dist.runs ? k / dist.runs : 1 }));
  const rows = names.map((s) => ({ label: sysName(s), swatch: vizColor(s, names), counts: Object.fromEntries(dist.systems[s].map((n, k) => [k, n])) }));
  const chart = vizStack(rows, order, {
    nameOf: (o) => (dist.runs === 1 ? (o.key ? "맞음" : "틀림") : `${dist.runs}회 중 ${o.key}회 맞음`),
    colorOf: (o) => vizSeqVar(Math.max(0.15, o.rate)), inkOf: (o) => vizSeqInk(Math.max(0.15, o.rate)),
  });
  const tableHtml = table(["시스템", ...order.map((o) => `${o.key}회`)], names.map((s) => [esc(sysName(s)), ...dist.systems[s].map(num)]));
  return vizBlock(`${dist.runs}회 통과 분포`, `사례마다 ${dist.runs}회 중 몇 번 맞았나 · 진할수록 많이`, chart + vizDetails(tableHtml));
}

function vizBatchGrid(grid) {
  if (!grid) return "";
  const cols = grid.columns;
  const head = `<div class="viz-grid-row" style="grid-template-columns:160px repeat(${cols.length}, 56px)"><span></span>${cols.map((c) => {
    const [system, run] = c.split("#");
    return `<span class="small"><i class="viz-swatch" style="background:${vizColor(system)}"></i>${esc(sysName(system))} ${esc(run)}회</span>`;
  }).join("")}</div>`;
  const body = grid.rows.map((r) => `<div class="viz-grid-row" style="grid-template-columns:160px repeat(${cols.length}, 56px)"><span class="small mono">${esc(r.key)}</span>${cols.map((c) => {
    const v = r.cells[c];
    if (!v) return '<span class="viz-cell empty">-</span>';
    const cls = v.ok === true ? "ok" : v.ok === false ? "bad" : "unk";
    return `<button class="viz-cell ${cls}" data-eval-case="${v.index}" title="${esc(r.key)} · ${esc(c)}">${v.ok === true ? "✓" : v.ok === false ? "✗" : "?"}</button>`;
  }).join("")}</div>`).join("");
  return vizBlock("묶음 사례 × A/B", "✓ 맞음 · ✗ 틀림 (진단은 심은 원인을 찾았나, 묶음은 충돌이 남지 않았나) · 칸을 누르면 그 사례", `<div class="viz-grid">${head}${body}</div>`);
}

function vizReasons(reasons, systems) {
  if (!reasons) return "";
  const names = systems.filter((s) => reasons.systems[s]?.length);
  const panels = names.map((s) => {
    const rows = reasons.systems[s];
    const max = Math.max(...rows.map((r) => r.count), 1);
    return `<div class="viz-rank"><div class="viz-sys"><i style="background:${vizColor(s, names)}"></i><b>${esc(sysName(s))}</b></div>
      ${rows.map((r) => `<div class="viz-rank-row" title="${esc(r.label)}: ${r.count}건"><span class="viz-rank-label">${esc(r.label)}</span>
        <span class="viz-track"><span class="viz-fill" style="width:${(r.count / max) * 100}%;background:${vizColor(s, names)}"></span></span>
        <span class="num small">${r.count}</span></div>`).join("")}</div>`;
  }).join("");
  const tableHtml = names.map((s) => `<div class="small"><b>${esc(sysName(s))}</b></div>` + table(["거절 이유", "건수"], reasons.systems[s].map((r) => [esc(r.label), num(r.count)]))).join("");
  return panels ? vizBlock("거절 이유 순위", "검사·검토기가 돌려보낸 까닭 · 시스템마다 상위 8개", `<div class="viz-rank-wrap">${panels}</div>` + vizDetails(tableHtml)) : "";
}

// ── 질문 5: 준비 시간 점 분포, 적합 1건당 호출·토큰 ──

function vizLatency(latency, systems) {
  if (!latency) return "";
  const names = systems.filter((s) => latency.systems[s]?.length);
  if (!names.length) return "";
  const all = names.flatMap((s) => latency.systems[s]);
  const max = Math.max(...all, latency.budget ?? 0) * 1.05;
  const W = 760, L = 110, R = 190, rowH = 32, T = 8, H = T + names.length * rowH + 24;
  const x = (v) => L + (v / max) * (W - L - R);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const median = (a) => { const s = [...a].sort((p, q) => p - q); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const rows = names.map((s, i) => {
    const y = T + i * rowH + rowH / 2;
    const values = latency.systems[s];
    const med = median(values);
    const within = latency.budget != null ? values.filter((v) => v <= latency.budget).length : null;
    const jitter = (k) => ((k * 37) % 11 - 5) * 1.2;
    return `<text x="${L - 8}" y="${y + 4}" text-anchor="end" class="viz-axis-ink">${esc(sysName(s))}</text>
      ${values.map((v, k) => `<circle cx="${x(v).toFixed(1)}" cy="${(y + jitter(k)).toFixed(1)}" r="4" style="fill:${vizColor(s, names)};stroke:var(--surface)" fill-opacity="0.6" stroke-width="1"><title>${esc(sysName(s))} ${v}초</title></circle>`).join("")}
      <line x1="${x(med)}" y1="${y - 10}" x2="${x(med)}" y2="${y + 10}" class="viz-median"><title>${esc(sysName(s))} 중앙값 ${med.toFixed(1)}초</title></line>
      <text x="${W - R + 12}" y="${y + 4}" class="viz-axis-ink">중앙 ${med.toFixed(1)}초${within != null ? ` · ${latency.budget}초 안 ${within}/${values.length}` : ""}</text>`;
  }).join("");
  const grid = ticks.map((t) => `<line x1="${x(t)}" y1="${T}" x2="${x(t)}" y2="${H - 22}" class="viz-gridline"/><text x="${x(t)}" y="${H - 8}" text-anchor="middle" class="viz-axis">${t}초</text>`).join("");
  const budget = latency.budget != null ? `<line x1="${x(latency.budget)}" y1="${T}" x2="${x(latency.budget)}" y2="${H - 22}" class="viz-budget"/>
    <text x="${x(latency.budget) + 4}" y="${T + 10}" class="viz-axis-ink">기준 ${latency.budget}초</text>` : "";
  const svg = `<svg class="viz-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="사례마다 준비 시간">${grid}${budget}${rows}</svg>`;
  const tableHtml = table(["시스템", "사례", "중앙값(초)", "최댓값(초)", latency.budget != null ? `${latency.budget}초 안` : "-"], names.map((s) => {
    const v = latency.systems[s];
    return [esc(sysName(s)), num(v.length), median(v).toFixed(1), Math.max(...v).toFixed(1), latency.budget != null ? `${v.filter((t) => t <= latency.budget).length}/${v.length}` : "-"];
  }));
  return vizBlock("사례마다 준비 시간", `점 하나 = 사례 하나 · 세로 막대 = 중앙값${latency.budget != null ? ` · 빨간 선 = ${latency.budget}초 기준` : ""}`, vizLegend(names) + svg + vizDetails(tableHtml));
}

function vizCost(cost, systems) {
  if (!cost) return "";
  const labels = { calls_per_fit: ["적합 1건당 호출", "번"], tokens_per_fit: ["적합 1건당 토큰", "토큰"] };
  const groups = Object.entries(cost).map(([id, rows]) => {
    const names = systems.filter((s) => rows[s]);
    const max = Math.max(...names.map((s) => rows[s].value), 1e-9);
    return `<div class="viz-group"><div class="small"><b>${esc(labels[id][0])}</b> <span class="muted">↓ 낮을수록 좋음</span></div>
      ${names.map((s) => `<div class="viz-hbar" title="${esc(sysName(s))} ${esc(labels[id][0])} ${rows[s].value}">
        <span class="viz-sys"><i style="background:${vizColor(s, names)}"></i>${esc(sysName(s))}</span>
        <span class="viz-track"><span class="viz-fill" style="width:${(rows[s].value / max) * 100}%;background:${vizColor(s, names)}"></span></span>
        <span class="num small">${Number(rows[s].value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })} ${esc(labels[id][1])}</span></div>`).join("")}</div>`;
  }).join("");
  const names = systems.filter((s) => Object.values(cost).some((rows) => rows[s]));
  const tableHtml = table(["시스템", ...Object.keys(cost).map((id) => esc(labels[id][0]))], names.map((s) => [esc(sysName(s)), ...Object.keys(cost).map((id) => (cost[id][s] ? Number(cost[id][s].value).toFixed(2) : "-"))]));
  return vizBlock("적합 1건당 호출·토큰", "심판 호출은 빼고 셈 · 막대 길이는 그 지표의 가장 큰 값 기준", vizLegend(names) + `<div class="viz-cost">${groups}</div>` + vizDetails(tableHtml));
}

// ── 질문별 카드 ──

function evalQuestionCards(run) {
  const groups = {};
  const sets = [...new Set(run.metrics.map((m) => m.set).filter(Boolean))];
  const chosen = sets.includes(evalView.set) ? evalView.set : sets.includes("all") ? "all" : sets.includes("balanced") ? "balanced" : sets[0];
  for (const m of run.metrics.filter((m) => !m.set || m.set === chosen)) (groups[m.question ?? "etc"] ??= []).push(m);
  const systems = run.systems.length ? run.systems : [...new Set(run.metrics.map((m) => m.system ?? "-"))];
  const ab = run.systems.includes("A") && run.systems.includes("B");
  const c = run.charts ?? {};
  const charts = {
    1: [vizRecallPrecision(c.q1?.recall_precision, systems), vizConfusion(c.q1?.confusion)],
    2: [vizDumbbell(c.q2?.conditions, systems), vizOutcomeMix(c.q2?.outcome_mix, c.q2?.source_mix, systems)],
    3: [vizScatter(c.q3?.scatter, systems), vizByKind(c.q3?.by_kind, systems)],
    4: [vizPassDistribution(c.q4?.pass_distribution, systems), vizBatchGrid(c.q4?.batch_grid), vizReasons(c.q4?.reasons, systems)],
    5: [vizLatency(c.q5?.latency, systems), vizCost(c.q5?.cost, systems)],
  };
  const setBar = sets.length > 1 ? `<div class="eval-filters viz-sets"><span class="muted small">지표 세트</span>${sets.map((name) =>
    `<button class="btn-outline small ${name === chosen ? "on" : ""}" data-eval-set="${esc(name)}">${esc(nm(SET_NAMES, name))}</button>`).join("")}</div>` : "";
  const questions = [...new Set([...Object.keys(groups), ...Object.keys(charts).filter((q) => charts[q].some(Boolean))])].sort();
  return setBar + questions.map((q) => {
    const rows = groups[q] ?? [];
    const drawn = (charts[q] ?? []).filter(Boolean).join("");
    const metricPart = rows.length ? vizBlock("지표", "점 위치 = 값 · 비율·F1 은 0~100%, 시간·호출은 0~가장 큰 값", vizLegend(systems.filter((s) => rows.some((m) => (m.system ?? "-") === s))) + vizMetricRows(rows, systems, ab)) : "";
    return `<div class="card"><h2>${esc(EVAL_QUESTIONS[q] ?? "기타 지표")}</h2>${drawn}${metricPart}${rows.length ? vizDetails(evalMetricTable(rows, ab), "지표 표로 보기") : ""}</div>`;
  }).join("");
}

// ── 추세: 선 + 마우스를 올리면 그 실행의 값 ──

function evalTrendSvg(t) {
  const points = t.points.filter((p) => p.value !== null && p.value !== undefined);
  if (!points.length) return '<div class="empty">값이 있는 실행이 없어요</div>';
  const runs = [...new Map(t.points.map((p) => [p.id, p])).values()];
  const systems = [...new Set(points.map((p) => p.system ?? "-"))];
  const ratio = t.points[0]?.unit === "ratio";
  const W = 680, H = 210, L = 46, R = 90, T = 14, B = 38;
  const values = points.map((p) => p.value);
  const lo = ratio ? 0 : Math.min(0, ...values), hi = ratio ? 1 : Math.max(...values, lo + 1e-9) * 1.1;
  const x = (i) => L + (runs.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (runs.length - 1));
  const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const fmtV = (v) => (ratio ? vizPct(v) : Number(v).toFixed(1));
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + (hi - lo) * f).map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" class="viz-gridline"/>
    <text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="viz-axis">${esc(fmtV(v))}</text>`).join("");
  const lines = systems.map((s) => {
    const color = vizColor(s, systems);
    const pts = runs.map((r, i) => [i, points.find((p) => p.id === r.id && (p.system ?? "-") === s)]).filter(([, p]) => p);
    const path = pts.map(([i, p], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
    return `<path d="${path}" style="fill:none;stroke:${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` +
      pts.map(([i, p]) => `<circle cx="${x(i)}" cy="${y(p.value)}" r="${runs[i].baseline ? 6 : 4}" style="fill:${runs[i].baseline ? "var(--surface)" : color};stroke:${runs[i].baseline ? color : "var(--surface)"}" stroke-width="2"/>`).join("");
  }).join("");
  const ends = [];
  for (const s of systems) {
    const last = [...runs].reverse().map((r) => points.find((p) => p.id === r.id && (p.system ?? "-") === s)).find(Boolean);
    const runIndex = runs.findIndex((r) => r.id === last.id);
    const same = ends.find((e) => e.text === fmtV(last.value) && e.i === runIndex);
    if (same) same.names.push(s);
    else ends.push({ names: [s], text: fmtV(last.value), i: runIndex, y: y(last.value) + 4 });
  }
  ends.sort((a, b) => a.y - b.y);
  ends.forEach((e, k) => { if (k && e.y - ends[k - 1].y < 13) e.y = ends[k - 1].y + 13; });
  const endLabels = ends.map((e) => `<text x="${x(e.i) + 10}" y="${e.y}" class="viz-axis-ink">${esc(e.names.join("·"))} ${esc(e.text)}</text>`).join("");
  const axis = runs.map((r, i) => `<text x="${x(i)}" y="${H - 20}" text-anchor="middle" class="viz-axis mono">${esc(r.commit ?? "-")}</text>
      <text x="${x(i)}" y="${H - 6}" text-anchor="middle" class="viz-axis">${esc(time(r.started_at).slice(0, 11))}</text>`).join("");
  // 마우스용 자료: 실행마다 x 위치와 시스템별 값 (그림 위에 겹친 투명 막대가 받는다)
  const hover = runs.map((r, i) => ({
    x: x(i), id: r.id, commit: r.commit, at: time(r.started_at), baseline: r.baseline,
    values: systems.map((s) => { const p = points.find((q) => q.id === r.id && (q.system ?? "-") === s); return p ? { s, v: fmtV(p.value), f: p.denominator != null ? `${p.numerator}/${p.denominator}` : "" } : null; }).filter(Boolean),
  }));
  const colors = Object.fromEntries(systems.map((s) => [s, vizColor(s, systems)]));
  return `${vizLegend(systems)}<div class="viz-trend-wrap" data-trend='${esc(JSON.stringify({ hover, colors, W, T, B, H }))}'>
    <svg class="viz-svg viz-trend" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t.metric)} 추세">${grid}${axis}${lines}${endLabels}
      <line class="viz-cross" x1="0" y1="${T}" x2="0" y2="${H - B}" visibility="hidden"/>
      <rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" class="viz-hit"/></svg>
    <div class="viz-tip" hidden></div></div>
    <div class="muted small">아래는 커밋과 시각 · 빈 동그라미 = 기준점 · ${t.higher_is_better === false ? "낮을수록 좋음" : "높을수록 좋음"} · 그림 위에 마우스를 올리면 값</div>`;
}

function onTrendMove(e) {
  const wrap = e.target.closest(".viz-trend-wrap");
  if (!wrap) return;
  const data = JSON.parse(wrap.dataset.trend);
  const svg = wrap.querySelector("svg");
  const box = svg.getBoundingClientRect();
  const sx = ((e.clientX - box.left) / box.width) * data.W;
  const near = data.hover.reduce((best, h) => (Math.abs(h.x - sx) < Math.abs(best.x - sx) ? h : best), data.hover[0]);
  const cross = svg.querySelector(".viz-cross");
  cross.setAttribute("x1", near.x);
  cross.setAttribute("x2", near.x);
  cross.setAttribute("visibility", "visible");
  const tip = wrap.querySelector(".viz-tip");
  tip.innerHTML = `<div class="small"><b>${esc(near.at)}</b> <span class="mono muted">${esc(near.commit ?? "-")}</span>${near.baseline ? ' <span class="tag brand">기준점</span>' : ""}</div>` +
    near.values.map((v) => `<div class="small"><i class="viz-swatch" style="background:${data.colors[v.s]}"></i>${esc(sysName(v.s))} <b>${esc(v.v)}</b> <span class="muted">${esc(v.f)}</span></div>`).join("");
  tip.hidden = false;
  const left = (near.x / data.W) * box.width;
  tip.style.left = `${Math.min(Math.max(0, left + 12), box.width - 180)}px`;
  tip.style.top = `${(data.T / data.H) * box.height}px`;
}

function onTrendLeave(e) {
  const wrap = e.target.closest(".viz-trend-wrap");
  if (!wrap || wrap.contains(e.relatedTarget)) return;
  wrap.querySelector(".viz-cross")?.setAttribute("visibility", "hidden");
  const tip = wrap.querySelector(".viz-tip");
  if (tip) tip.hidden = true;
}

// ── 사례 격자 (사례 × 조건), 사례 카드 ──

function vizCasesGrid(grid) {
  if (!grid) return "";
  const cols = grid.conditions;
  const head = `<div class="viz-grid-row" style="grid-template-columns:200px repeat(${cols.length}, 68px)"><span class="muted small">사례 · 시스템 · 회차</span>${cols.map((c) => `<span class="small" title="${esc(c)}">${esc(nm(COND_NAMES, c))}</span>`).join("")}</div>`;
  const body = grid.rows.map((r) => `<div class="viz-grid-row" style="grid-template-columns:200px repeat(${cols.length}, 68px)">
      <button class="viz-row-label" data-eval-case="${r.index}"><i class="viz-swatch" style="background:${vizColor(r.system ?? "-")}"></i>${esc(r.case_id)} · ${esc(sysName(r.system ?? "-"))} · ${esc(r.run)}${r.ok === false ? ' <span class="bad-mark">✗</span>' : ""}</button>
      ${r.cells.map((v, k) => `<button class="viz-cell ${v === true ? "ok" : v === false ? "bad" : "unk"}" data-eval-case="${r.index}" title="${esc(r.case_id)} · ${esc(r.system)} · ${esc(nm(COND_NAMES, cols[k]))}: ${v === true ? "통과" : v === false ? "실패" : "판단 불가"}">${v === true ? "✓" : v === false ? "✗" : "?"}</button>`).join("")}</div>`).join("");
  const note = grid.total > grid.rows.length ? ` · 실패 먼저 ${grid.rows.length}줄만 (전체 ${grid.total})` : ` · ${grid.total}줄`;
  return `<div class="card"><h2>사례 × 조건 <span class="muted">✓ 통과 · ✗ 실패 · ? 판단 불가 · 칸을 누르면 그 사례 카드가 열림${esc(note)}</span></h2><div class="viz-grid viz-cases-grid">${head}${body}</div></div>`;
}

function evalVotes(verdicts) {
  const names = Object.keys(verdicts);
  if (!names.length) return "";
  const mark = (v) => (v === true ? '<span class="ok-mark">✓</span>' : v === false ? '<span class="bad-mark">✗</span>' : '<span class="muted">?</span>');
  return `<div class="eval-votes">${names.map((n) => `<span class="eval-vote"><b>${esc(n)}</b> ${verdicts[n].vote.map(mark).join("")}</span>`).join("")}</div>`;
}

function evalChecks(checks) {
  const entries = Object.entries(checks ?? {});
  if (!entries.length) return "";
  return `<div class="eval-checks">${entries.map(([k, v]) => {
    const bad = (k.endsWith("_bad") && v) || (k.endsWith("_ok") && v === false) || (Array.isArray(v) && v.length);
    return `<span class="tag ${bad ? "warn" : ""}">${esc(k)} ${esc(Array.isArray(v) ? v.join(", ") || "없음" : String(v))}</span>`;
  }).join("")}</div>`;
}

function evalStepsHtml(runId) {
  const steps = evalView.steps[runId];
  if (!steps) return `<div class="run-steps"><span class="muted">불러오는 중…</span></div>`;
  agentView.steps[runId] = steps; // 에이전트 탭의 단계 보기 모양을 그대로 쓴다
  return agentStepsHtml(runId);
}

function evalCaseCard(c) {
  const okTag = c.ok === true ? '<span class="tag ok">✓ 맞음</span>' : c.ok === false ? '<span class="tag bad">✗ 틀림</span>' : '<span class="tag">-</span>';
  const open = c.run_id && evalView.open.has(c.run_id);
  return `<div class="call" id="eval-case-${c.index}"><div class="call-head">
      <b class="mono">${esc(c.case_id)}</b><span class="tag"><i class="viz-swatch" style="background:${vizColor(c.system ?? "-")}"></i>${esc(sysName(c.system ?? "-"))}</span><span class="muted small">회차 ${esc(c.run)}</span>${okTag}
      ${c.source ? `<span class="tag ${c.source === "AGENT" ? "brand" : "warn"}">${esc(c.source)}</span>` : ""}
      ${c.expected != null ? `<span class="muted small">정답 ${esc(c.expected)}</span>` : ""}
      ${c.seconds != null ? `<span class="muted small">${esc(c.seconds)}초</span>` : ""}
      ${c.run_id ? `<button class="btn-outline small" data-eval-trace="${esc(c.run_id)}">${open ? "단계 접기" : "단계 보기"}</button>` : ""}
    </div>
    ${c.problems.length ? `<ul class="eval-problems">${c.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : ""}
    <div class="eval-io">
      <div><div class="muted small">입력</div><div class="eval-text">${esc(c.input ?? "-")}</div></div>
      <div><div class="muted small">출력</div><div class="eval-text">${esc(c.output ?? "(출력 없음)")}</div></div>
    </div>
    ${evalChecks(c.checks)}${evalVotes(c.verdicts)}
    ${open ? evalStepsHtml(c.run_id) : ""}</div>`;
}

function evalPairs(pairs) {
  if (!pairs.length) return "";
  const side = (name, p) => `<div><div class="muted small"><i class="viz-swatch" style="background:${vizColor(name)}"></i>${name} ${p.ok ? '<span class="tag ok">✓ 맞음</span>' : '<span class="tag bad">✗ 틀림</span>'} <span class="tag">${esc(p.source ?? "-")}</span></div>
    <div class="eval-text">${esc(p.output ?? "(출력 없음)")}</div>${p.problems.length ? `<div class="muted small">${p.problems.map(esc).join(" · ")}</div>` : ""}</div>`;
  return `<div class="card"><h2>짝 비교 <span class="muted">같은 사례·회차의 A 와 B. 한쪽만 맞은 쌍 먼저</span></h2>
    ${pairs.map((p) => `<div class="call"><div class="call-head"><b class="mono">${esc(p.case_id)}</b><span class="muted small">회차 ${esc(p.run)}</span>
      ${p.only ? `<span class="tag blue">${esc(p.only)} 만 맞음</span>` : ""}</div>
      <div class="eval-text muted">${esc(p.input ?? "")}</div>
      <div class="eval-io">${side("A", p.A)}${side("B", p.B)}</div></div>`).join("")}</div>`;
}

function evalJudgeCard(check) {
  if (!check) return "";
  const rows = check.metrics.map((m) => [esc(sysName(m.system ?? "-")), `<span title="${esc(m.key)}">${esc(metricName(m.name))}</span>`, evalValue(m)]);
  const target = check.validation?.critic_target ?? {};
  const badges = Object.entries(target).map(([set, t]) => `<span class="viz-goal ${t.pass ? "pass" : "fail"}">${t.pass ? "✓" : "✗"} critic ${esc(nm(SET_NAMES, set))}: 놓침 ${t.missed}, 오거절 ${vizPct(t.false_reject_rate)}</span>`).join("");
  return `<div class="card"><h2>심판 검증 <span class="muted">LLM 검토기 기준(놓침 0, 오거절 10% 이하) 통과 여부와 판정기별 지표</span></h2>
    <div class="viz-badges">${badges || '<span class="muted small">기준 판정 없음</span>'}</div>
    ${vizDetails(table(["판정기", "지표", "값"], rows) + (Object.keys(check.validation ?? {}).length ? `<pre class="eval-pre">${esc(JSON.stringify(check.validation, null, 1))}</pre>` : ""))}</div>`;
}

// ── 그리기 ──

async function renderEval() {
  const picks = Object.entries(evalView.picks).map(([k, v]) => `${k}:${v}`).join(",");
  const [listing, sc] = await Promise.all([api(`${API}/evals`), api(`${API}/evals/scorecard${picks ? `?picks=${encodeURIComponent(picks)}` : ""}`)]);
  const list = listing.runs;
  const summary = evalScorecard(sc);
  if (!list.length) return `${summary}<div class="card"><div class="empty">평가 결과가 없어요. server 에서 <span class="mono">python -m Harness.evals &lt;스위트&gt;</span> 를 돌리면 ${esc("db/app_data/harness_eval/")} 에 남아요.</div></div>`;
  if (!list.some((r) => r.id === evalView.id)) evalView.id = (list.find((r) => !r.legacy) ?? list[0]).id;
  const params = new URLSearchParams({ id: evalView.id, limit: EVAL_PAGE, offset: evalView.offset, failed_only: evalView.failedOnly });
  if (evalView.system) params.set("system", evalView.system);
  if (evalView.focus != null) params.set("case", evalView.focus);
  const run = await api(`${API}/evals/run?${params}`);
  await Promise.all([...evalView.open].filter((id) => !evalView.steps[id]).map(async (id) => {
    evalView.steps[id] = (await api(`${API}/evals/trace?id=${encodeURIComponent(run.id)}&run_id=${encodeURIComponent(id)}`)).steps;
  }));
  if (evalView.metric && !run.metrics.some((m) => m.key === evalView.metric)) evalView.metric = null;
  const trend = evalView.metric ? await api(`${API}/evals/trend?suite=${encodeURIComponent(run.suite)}&metric=${encodeURIComponent(evalView.metric)}`) : null;
  const body = run.legacy
    ? `<div class="card"><h2>요약 <span class="muted">예전 형식 결과 (숫자만)</span></h2>${table(["항목", "값"], Object.entries(run.summary ?? {}).map(([k, v]) => [esc(k), `<span class="mono">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`]))}</div>`
    : evalQuestionCards(run);
  const filters = evalView.focus != null
    ? `<div class="eval-filters"><span class="muted small">격자에서 고른 사례 하나</span><button class="btn-outline small" data-eval-unfocus="1">모든 사례 보기</button></div>`
    : `<div class="eval-filters">
      <button class="btn-outline small ${evalView.failedOnly ? "on" : ""}" data-eval-failed="${evalView.failedOnly ? "off" : "on"}">${evalView.failedOnly ? "실패만 보는 중" : "모두 보는 중"}</button>
      ${["", ...run.systems].map((s) => `<button class="btn-outline small ${evalView.system === s ? "on" : ""}" data-eval-system="${esc(s || "*")}">${esc(s ? sysName(s) : "모든 시스템")}</button>`).join("")}
      <span class="muted small">${num(run.cases_total)}건 중 ${num(run.offset + 1 > run.cases_total ? 0 : run.offset + 1)}~${num(Math.min(run.offset + EVAL_PAGE, run.cases_total))} (전체 사례 ${num(run.cases_all)})</span>
      ${run.offset > 0 ? '<button class="btn-outline small" data-eval-page="prev">◀ 앞</button>' : ""}
      ${run.offset + EVAL_PAGE < run.cases_total ? '<button class="btn-outline small" data-eval-page="next">뒤 ▶</button>' : ""}
    </div>`;
  return `
    ${summary}
    <div class="card"><h2>평가 실행 <span class="muted">최근 먼저 · ${esc(list.length)}개</span></h2><div class="eval-runs">${list.map(evalRunRow).join("")}</div></div>
    <div class="card"><h2>${esc(nm(SUITE_NAMES, run.suite))} · <span class="mono">${esc(run.id)}</span>
      <span class="muted">${esc(time(run.started_at))} · 커밋 ${esc(run.commit ?? "-")}${run.git?.dirty ? " (고친 파일 있음)" : ""}${run.baseline ? " · 기준점" : ""}</span></h2>
      ${vizLegend(run.systems)}
      <div class="muted small">시스템 ${esc(run.systems.map(sysName).join(", ") || "-")}${run.config?.judge_mode ? ` · 심판 ${esc(run.config.judge_mode)}` : ""}${run.config?.path ? ` · 경로 ${esc(run.config.path)}` : ""}${run.config?.check_kinds ? ` · 검사 종류 ${Object.entries(run.config.check_kinds).map(([k, v]) => `${esc(sysName(k))}: ${esc(v)}`).join(" / ")}` : ""}${run.config?.gold?.file ? ` · 정답지 ${esc(run.config.gold.file)} ${esc(String(run.config.gold.sha256 ?? "").slice(0, 12))}` : ""}</div>
    </div>
    ${trend ? `<div class="card" id="eval-trend-card"><h2>추세 · <span title="${esc(trend.metric)}">${esc(run.metrics.find((m) => m.key === trend.metric)?.name ? metricName(run.metrics.find((m) => m.key === trend.metric).name) : trend.metric)}</span> <span class="muted">${esc(nm(SUITE_NAMES, run.suite))} 실행별</span>
      <button class="btn-outline small" data-eval-metric="">닫기</button></h2>${evalTrendSvg(trend)}${vizDetails(table(["실행", "커밋", "시스템", "값"], trend.points.map((p) => [esc(p.id), esc(p.commit ?? "-"), esc(sysName(p.system ?? "-")), evalValue(p)])))}</div>` : ""}
    ${body}
    ${run.legacy ? "" : vizCasesGrid(run.charts?.cases_grid)}
    <div class="card" id="eval-cases"><h2>사례</h2>${filters}
      ${run.cases.length ? run.cases.map(evalCaseCard).join("") : `<div class="empty">${evalView.failedOnly ? "실패한 사례가 없어요" : "사례가 없어요"}</div>`}</div>
    ${evalPairs(run.pairs)}
    ${evalJudgeCard(run.judge_check)}`;
}

async function onEvalClick(button) {
  const { evalPick, evalMetric, evalFailed, evalSystem, evalPage, evalTrace, evalSet, evalCase, evalUnfocus } = button.dataset;
  if (evalPick !== undefined) Object.assign(evalView, { id: evalPick, offset: 0, system: "", metric: null, open: new Set(), steps: {}, focus: null });
  if (evalMetric !== undefined) evalView.metric = evalMetric || null;
  if (evalFailed !== undefined) Object.assign(evalView, { failedOnly: evalFailed === "on", offset: 0 });
  if (evalSystem !== undefined) Object.assign(evalView, { system: evalSystem === "*" ? "" : evalSystem, offset: 0 });
  if (evalSet !== undefined) evalView.set = evalSet;
  if (evalCase !== undefined) evalView.focus = Number(evalCase);
  if (evalUnfocus !== undefined) evalView.focus = null;
  if (evalPage) evalView.offset = Math.max(0, evalView.offset + (evalPage === "next" ? EVAL_PAGE : -EVAL_PAGE));
  if (evalTrace) {
    if (evalView.open.has(evalTrace)) evalView.open.delete(evalTrace);
    else evalView.open.add(evalTrace);
  }
  const keep = window.scrollY;
  content.innerHTML = await renderEval();
  if (evalMetric) document.getElementById("eval-trend-card")?.scrollIntoView({ block: "start" }); // 아래에서 누른 추세를 바로 보이게
  else if (evalCase !== undefined) document.getElementById(`eval-case-${evalCase}`)?.scrollIntoView({ block: "center" }); // 격자에서 누른 사례
  else if (evalPick !== undefined) window.scrollTo(0, 0);
  else window.scrollTo(0, keep);
}

// 평가 탭 버튼은 아래 공통 클릭 처리(화면 전체 새로 그리기)보다 먼저 잡는다
content.addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button || !Object.keys(button.dataset).some((k) => k.startsWith("eval"))) return;
  e.stopPropagation();
  try {
    await onEvalClick(button);
  } catch (error) {
    toast(error.message);
  }
}, true);
// 맨 위 카드의 실행 드롭다운
content.addEventListener("change", async (e) => {
  const select = e.target.closest("select[data-eval-scpick]");
  if (!select) return;
  e.stopPropagation();
  if (select.value) evalView.picks[select.dataset.evalScpick] = select.value;
  else delete evalView.picks[select.dataset.evalScpick];
  const keep = window.scrollY;
  try {
    content.innerHTML = await renderEval();
    window.scrollTo(0, keep);
  } catch (error) {
    toast(error.message);
  }
}, true);
content.addEventListener("mousemove", onTrendMove);
content.addEventListener("mouseout", onTrendLeave);
