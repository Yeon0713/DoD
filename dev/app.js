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
// 실행 목록 → 고른 실행의 질문별 지표 표, 추세, 사례(실패만 기본), 짝 비교(A·B), 심판 검증.

const evalView = { id: null, system: "", failedOnly: true, offset: 0, metric: null, open: new Set(), steps: {}, table: false, set: null };
const EVAL_PAGE = 30;
const EVAL_QUESTIONS = {
  1: "질문 1. 리뷰를 바르게 가르는가",
  2: "질문 2. 글을 믿을 수 있는가",
  3: "질문 3. 안전장치가 제 역할을 하는가",
  4: "질문 4. 에이전트가 믿을 만하게 동작하는가",
  5: "질문 5. 비용과 시간",
};

function evalValue(m) {
  if (!m) return '<span class="muted">-</span>';
  if (m.value === null || m.value === undefined) return `<span class="muted">해당 없음</span>${m.note ? ` <span class="muted small">${esc(m.note)}</span>` : ""}`;
  const shown = m.unit === "ratio" ? `${(m.value * 100).toFixed(1)}%` : `${Number.isInteger(m.value) ? m.value : Number(m.value).toFixed(2)}${m.unit && m.unit !== "f1" ? ` ${esc(m.unit)}` : ""}`;
  const frac = m.denominator !== null && m.denominator !== undefined ? ` <span class="muted small">${m.numerator}/${m.denominator}</span>` : "";
  return `<b class="num">${shown}</b>${frac}`;
}

function evalDiff(a, b) {
  if (!a || !b || a.value == null || b.value == null) return '<span class="muted">-</span>';
  const d = b.value - a.value;
  if (Math.abs(d) < 1e-9) return '<span class="muted">같음</span>';
  const good = (d > 0) === (a.higher_is_better !== false);
  const shown = a.unit === "ratio" ? `${d > 0 ? "+" : ""}${(d * 100).toFixed(1)}%p` : `${d > 0 ? "+" : ""}${d.toFixed(2)}`;
  return `<span class="tag ${good ? "ok" : "warn"}">B ${shown}</span>`;
}

function evalRunRow(r) {
  const head = vizHeadline(r);
  return `<div class="call eval-run ${r.id === evalView.id ? "picked" : ""}"><div class="call-head">
      <button class="btn-outline small" data-eval-pick="${esc(r.id)}">${r.id === evalView.id ? "보는 중" : "보기"}</button>
      <span class="mono">${esc(time(r.started_at))}</span><b>${esc(r.suite)}</b>
      ${r.baseline ? '<span class="tag brand">기준점</span>' : ""}${r.legacy ? '<span class="tag">예전 형식</span>' : ""}
      <span class="tag">${esc(r.systems.join(", ") || "-")}</span>
      <span class="mono muted small">${esc(r.commit ?? "")}</span><span class="muted small">사례 ${num(r.cases)}</span>
    </div><div class="call-body">${head || '<span class="muted">지표 없음</span>'}</div></div>`;
}

function evalMetricTables(run) {
  const groups = {};
  for (const m of run.metrics) (groups[m.question ?? "etc"] ??= []).push(m);
  const ab = run.systems.includes("A") && run.systems.includes("B");
  return Object.keys(groups).sort().map((q) => {
    const rows = groups[q];
    const systems = [...new Set(rows.map((m) => m.system ?? "-"))];
    const keys = [...new Set(rows.map((m) => m.key))];
    const cell = (key, s) => rows.find((m) => m.key === key && (m.system ?? "-") === s);
    const headers = ["지표", ...systems.map(esc), ...(ab ? ["차이 (B−A)"] : []), "좋은 방향", ""];
    const body = keys.map((key) => {
      const first = rows.find((m) => m.key === key);
      return [
        `${esc(first.name)} <span class="muted small mono">${esc(key)}</span>`,
        ...systems.map((s) => evalValue(cell(key, s))),
        ...(ab ? [evalDiff(cell(key, "A"), cell(key, "B"))] : []),
        first.higher_is_better === false ? "낮을수록 좋음" : "높을수록 좋음",
        `<button class="btn-outline small" data-eval-metric="${esc(key)}">추세</button>`,
      ];
    });
    return `<div class="card"><h2>${esc(EVAL_QUESTIONS[q] ?? "기타 지표")}</h2>${table(headers, body)}</div>`;
  }).join("");
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
  const okTag = c.ok === true ? '<span class="tag ok">맞음</span>' : c.ok === false ? '<span class="tag bad">틀림</span>' : '<span class="tag">-</span>';
  const open = c.run_id && evalView.open.has(c.run_id);
  return `<div class="call"><div class="call-head">
      <b class="mono">${esc(c.case_id)}</b><span class="tag">${esc(c.system ?? "-")}</span><span class="muted small">회차 ${esc(c.run)}</span>${okTag}
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
  const side = (name, p) => `<div><div class="muted small">${name} ${p.ok ? '<span class="tag ok">맞음</span>' : '<span class="tag bad">틀림</span>'} <span class="tag">${esc(p.source ?? "-")}</span></div>
    <div class="eval-text">${esc(p.output ?? "(출력 없음)")}</div>${p.problems.length ? `<div class="muted small">${p.problems.map(esc).join(" · ")}</div>` : ""}</div>`;
  return `<div class="card"><h2>짝 비교 <span class="muted">같은 사례·회차의 A 와 B. 한쪽만 맞은 쌍 먼저</span></h2>
    ${pairs.map((p) => `<div class="call"><div class="call-head"><b class="mono">${esc(p.case_id)}</b><span class="muted small">회차 ${esc(p.run)}</span>
      ${p.only ? `<span class="tag blue">${esc(p.only)} 만 맞음</span>` : ""}</div>
      <div class="eval-text muted">${esc(p.input ?? "")}</div>
      <div class="eval-io">${side("A", p.A)}${side("B", p.B)}</div></div>`).join("")}</div>`;
}

function evalJudgeCard(check) {
  if (!check) return "";
  const rows = check.metrics.map((m) => [esc(m.system ?? "-"), `${esc(m.name)} <span class="muted small mono">${esc(m.key)}</span>`, evalValue(m)]);
  return `<div class="card"><h2>심판 검증 <span class="muted">판정기별 놓침·오거절, 목표 통과 여부</span></h2>
    ${table(["판정기", "지표", "값"], rows)}
    ${Object.keys(check.validation ?? {}).length ? `<pre class="eval-pre">${esc(JSON.stringify(check.validation, null, 1))}</pre>` : ""}</div>`;
}

async function renderEval() {
  const list = (await api(`${API}/evals`)).runs;
  if (!list.length) return `<div class="card"><div class="empty">평가 결과가 없어요. server 에서 <span class="mono">python -m Harness.evals &lt;스위트&gt;</span> 를 돌리면 ${esc("db/app_data/harness_eval/")} 에 남아요.</div></div>`;
  if (!list.some((r) => r.id === evalView.id)) evalView.id = (list.find((r) => !r.legacy) ?? list[0]).id;
  const params = new URLSearchParams({ id: evalView.id, limit: EVAL_PAGE, offset: evalView.offset, failed_only: evalView.failedOnly });
  if (evalView.system) params.set("system", evalView.system);
  const run = await api(`${API}/evals/run?${params}`);
  await Promise.all([...evalView.open].filter((id) => !evalView.steps[id]).map(async (id) => {
    evalView.steps[id] = (await api(`${API}/evals/trace?id=${encodeURIComponent(run.id)}&run_id=${encodeURIComponent(id)}`)).steps;
  }));
  if (evalView.metric && !run.metrics.some((m) => m.key === evalView.metric)) evalView.metric = null;
  const trend = evalView.metric ? await api(`${API}/evals/trend?suite=${encodeURIComponent(run.suite)}&metric=${encodeURIComponent(evalView.metric)}`) : null;
  const legacy = run.legacy
    ? `<div class="card"><h2>요약 <span class="muted">예전 형식 결과 (숫자만)</span></h2>${table(["항목", "값"], Object.entries(run.summary ?? {}).map(([k, v]) => [esc(k), `<span class="mono">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`]))}</div>`
    : evalView.table ? evalMetricTables(run) : vizMetricCards(run);
  const v = run.visuals ?? {};
  const charts = run.legacy ? "" : [vizMix(v.mix, run.systems), vizConditions(v.conditions, run.systems), vizByKind(v.by_kind, run.systems),
    vizConfusion(v.confusion, run.systems), vizProblems(v.problems, run.systems), vizLatency(v.latency, run.systems)].join("");
  const filters = `<div class="eval-filters">
      <button class="btn-outline small ${evalView.failedOnly ? "on" : ""}" data-eval-failed="${evalView.failedOnly ? "off" : "on"}">${evalView.failedOnly ? "실패만 보는 중" : "모두 보는 중"}</button>
      ${["", ...run.systems].map((s) => `<button class="btn-outline small ${evalView.system === s ? "on" : ""}" data-eval-system="${esc(s || "*")}">${esc(s || "모든 시스템")}</button>`).join("")}
      <span class="muted small">${num(run.cases_total)}건 중 ${num(run.offset + 1 > run.cases_total ? 0 : run.offset + 1)}~${num(Math.min(run.offset + EVAL_PAGE, run.cases_total))} (전체 사례 ${num(run.cases_all)})</span>
      ${run.offset > 0 ? '<button class="btn-outline small" data-eval-page="prev">◀ 앞</button>' : ""}
      ${run.offset + EVAL_PAGE < run.cases_total ? '<button class="btn-outline small" data-eval-page="next">뒤 ▶</button>' : ""}
    </div>`;
  return `
    <div class="card"><h2>평가 실행 <span class="muted">최근 먼저 · ${esc(list.length)}개</span></h2><div class="eval-runs">${list.map(evalRunRow).join("")}</div></div>
    <div class="card"><h2>${esc(run.suite)} · <span class="mono">${esc(run.id)}</span>
      <span class="muted">${esc(time(run.started_at))} · 커밋 ${esc(run.commit ?? "-")}${run.git?.dirty ? " (고친 파일 있음)" : ""}${run.baseline ? " · 기준점" : ""}</span></h2>
      ${run.legacy ? "" : `<button class="btn-outline small viz-toggle" data-eval-table="${evalView.table ? "off" : "on"}">${evalView.table ? "그래프로 보기" : "지표를 표로 보기"}</button>`}
      ${vizLegend(run.systems)}
      <div class="muted small">시스템 ${esc(run.systems.join(", ") || "-")}${run.config?.judge_mode ? ` · 심판 ${esc(run.config.judge_mode)}` : ""}${run.config?.path ? ` · 경로 ${esc(run.config.path)}` : ""}${run.config?.gold?.file ? ` · 정답지 ${esc(run.config.gold.file)} ${esc(String(run.config.gold.sha256 ?? "").slice(0, 12))}` : ""}</div>
    </div>
    ${trend ? `<div class="card" id="eval-trend-card"><h2>추세 · <span class="mono">${esc(trend.metric)}</span> <span class="muted">${esc(run.suite)} 실행별</span>
      <button class="btn-outline small" data-eval-metric="">닫기</button></h2>${evalTrendSvg(trend)}</div>` : ""}
    ${legacy}
    ${charts}
    ${evalJudgeCard(run.judge_check)}
    ${evalPairs(run.pairs)}
    <div class="card"><h2>사례</h2>${filters}
      ${run.cases.length ? run.cases.map(evalCaseCard).join("") : `<div class="empty">${evalView.failedOnly ? "실패한 사례가 없어요" : "사례가 없어요"}</div>`}</div>`;
}

async function onEvalClick(button) {
  const { evalPick, evalMetric, evalFailed, evalSystem, evalPage, evalTrace, evalTable, evalSet } = button.dataset;
  if (evalSet !== undefined) evalView.set = evalSet;
  if (evalTable !== undefined) evalView.table = evalTable === "on";
  if (evalPick !== undefined) Object.assign(evalView, { id: evalPick, offset: 0, system: "", metric: null, open: new Set(), steps: {} });
  if (evalMetric !== undefined) evalView.metric = evalMetric || null;
  if (evalFailed !== undefined) Object.assign(evalView, { failedOnly: evalFailed === "on", offset: 0 });
  if (evalSystem !== undefined) Object.assign(evalView, { system: evalSystem === "*" ? "" : evalSystem, offset: 0 });
  if (evalPage) evalView.offset = Math.max(0, evalView.offset + (evalPage === "next" ? EVAL_PAGE : -EVAL_PAGE));
  if (evalTrace) {
    if (evalView.open.has(evalTrace)) evalView.open.delete(evalTrace);
    else evalView.open.add(evalTrace);
  }
  const keep = window.scrollY;
  content.innerHTML = await renderEval();
  if (evalMetric) document.getElementById("eval-trend-card")?.scrollIntoView({ block: "start" }); // 아래에서 누른 추세를 바로 보이게
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

// ── 평가 탭 그래프 ──
// 색은 하는 일로 정한다. 시스템(정체) = 범주 색을 이름에 고정(필터로 바뀌지 않게), 크기 = 파랑 한 색 진하기,
// 상태(통과·물러남·놓침) = 상태 색 + 글자. 글자는 늘 잉크 색이고 색 칠한 표시(점·막대)가 옆에서 정체를 알린다.
// 모든 그래프 아래에 정확한 숫자(분자/분모)가 글자로 있고, 지표는 [표로 보기]로 예전 표를 볼 수 있다.

const VIZ_SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]; // 밝은 화면 범주 색 1~4 (검사 통과: 인접 CVD ΔE 9.1 이상)
const VIZ_SYSTEM_SLOT = { A: 0, B: 1, rule: 0, hcx: 1, voice: 2, regex: 0, critic: 1, judge_tools: 2, judge_thinking: 3, "rule+judge": 1 };
const VIZ_STATUS = { good: "#0ca30c", good2: "#006300", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b", neutral: "#c3c2b7" };
const VIZ_STATUS_INK = { warning: "#0b0b0b", neutral: "#0b0b0b" }; // 밝은 칸 안 글자는 검정, 나머지는 흰색
const VIZ_SEQ = ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]; // 파랑 단계 (0 은 거의 없음)

const vizColor = (system, systems) => VIZ_SERIES[(VIZ_SYSTEM_SLOT[system] ?? Math.max(0, systems.indexOf(system))) % VIZ_SERIES.length];
const vizPct = (v) => `${Math.round(v * 100)}%`;
const vizSeq = (rate) => (rate == null ? "#f0efec" : VIZ_SEQ[Math.min(VIZ_SEQ.length - 1, Math.round(rate * (VIZ_SEQ.length - 1)))]);
const vizSeqInk = (rate) => (rate != null && rate >= 0.5 ? "#ffffff" : "#0b0b0b");

function vizLegend(systems) {
  return `<div class="viz-legend">${systems.map((s) => `<span><i style="background:${vizColor(s, systems)}"></i>${esc(s)}</span>`).join("")}</div>`;
}

// 지표 하나를 시스템마다 막대 한 줄로. 비율·F1 은 0~100% 고정 축, 그 밖(초, 호출, 토큰)은 그 지표의 가장 큰 값 기준
// 지표 하나 = 한 줄 점 그림. 시스템마다 점 하나를 같은 축에 (비율·F1 은 0~100%, 시간·호출은 그 지표의 가장 큰 값까지).
// 둘 이상이면 가장 낮은 점과 높은 점을 회색 선으로 이어 차이를 보이고, 오른쪽에 정확한 값(분자/분모)을 글자로
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
      const offset = (i - (present.length - 1) / 2) * 5; // 같은 값이 겹쳐도 보이게 위아래로 조금씩
      return `<span class="viz-dot" style="left:${pos(m)}%;top:calc(50% + ${offset}px);background:${vizColor(s, systems)}"
        title="${esc(s)} · ${esc(first.name)}: ${esc(m.unit === "ratio" ? vizPct(m.value) : m.value)}${m.denominator != null ? ` (${m.numerator}/${m.denominator})` : ""}${m.note ? ` · ${esc(m.note)}` : ""}"></span>`;
    }).join("");
    const values = present.map((s) => `<span class="viz-v"><i style="background:${vizColor(s, systems)}"></i>${present.length > 1 ? `${esc(s)} ` : ""}${evalValue(cell(s))}</span>`).join("");
    const scale = fixed ? "" : `<span class="viz-scale-max muted small">${esc(Number.isInteger(max) ? max : max.toFixed(1))} ${esc(first.unit ?? "")}</span>`;
    return `<div class="viz-dotrow">
      <div class="viz-dot-name"><b>${esc(first.name)}</b><span class="muted small mono">${esc(key)}</span>
        <span class="viz-dir">${first.higher_is_better === false ? "↓ 낮을수록 좋음" : "↑ 높을수록 좋음"}</span></div>
      <div class="viz-dot-track">${span ? `<span class="viz-span" style="left:${span[0]}%;width:${span[1] - span[0]}%"></span>` : ""}${dots}${scale}</div>
      <div class="viz-dot-values">${values}${ab ? evalDiff(cell("A"), cell("B")) : ""}</div>
      <button class="btn-outline small" data-eval-metric="${esc(key)}">추세</button></div>`;
  }).join("");
}

function vizMetricCards(run) {
  // 세트(critic_cases·gold·all 등)가 붙은 지표는 한 세트씩 본다 (기본 all, 없으면 첫 세트)
  const sets = [...new Set(run.metrics.map((m) => m.set).filter(Boolean))];
  const chosen = sets.includes(evalView.set) ? evalView.set : sets.includes("all") ? "all" : sets[0];
  const setBar = sets.length > 1 ? `<div class="eval-filters viz-sets"><span class="muted small">세트</span>${sets.map((name) =>
    `<button class="btn-outline small ${name === chosen ? "on" : ""}" data-eval-set="${esc(name)}">${esc(name)}</button>`).join("")}</div>` : "";
  const groups = {};
  for (const m of run.metrics.filter((m) => !m.set || m.set === chosen)) (groups[m.question ?? "etc"] ??= []).push(m);
  const systems = run.systems.length ? run.systems : [...new Set(run.metrics.map((m) => m.system ?? "-"))];
  const ab = run.systems.includes("A") && run.systems.includes("B");
  return setBar + Object.keys(groups).sort().map((q) => `<div class="card"><h2>${esc(EVAL_QUESTIONS[q] ?? "기타 지표")}
      <span class="muted">점 위치 = 값 · 축은 비율·F1 이면 0~100%, 시간·호출이면 0~가장 큰 값 · 회색 선 = 시스템 사이 차이</span></h2>
      ${vizLegend(systems.filter((s) => groups[q].some((m) => (m.system ?? "-") === s)))}${vizMetricRows(groups[q], systems, ab)}</div>`).join("");
}

// 결과 구성: 시스템마다 사례가 어디로 갔는지 한 줄 막대 (상태 색 + 칸 안 비율 + 범례 글자)
function vizMix(mix, systems) {
  if (!mix) return "";
  const rows = systems.filter((s) => mix.systems[s]).map((s) => {
    const counts = mix.systems[s];
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const blocks = mix.order.filter((o) => counts[o.key]).map((o) => {
      const share = counts[o.key] / total;
      const label = share >= 0.08 ? `${vizPct(share)}` : "";
      return `<span class="viz-seg" style="flex:${counts[o.key]};background:${VIZ_STATUS[o.status]};color:${VIZ_STATUS_INK[o.status] ?? "#ffffff"}"
        title="${esc(s)} · ${esc(o.name)} ${counts[o.key]}/${total} (${vizPct(share)})">${label}</span>`;
    }).join("");
    return `<div class="viz-mix-row"><span class="viz-sys"><i style="background:${vizColor(s, systems)}"></i>${esc(s)}</span>
      <div class="viz-segbar">${blocks}</div><span class="muted small num">${total}건</span></div>`;
  }).join("");
  const legend = `<div class="viz-legend">${mix.order.map((o) => `<span><i style="background:${VIZ_STATUS[o.status]}"></i>${esc(o.name)}</span>`).join("")}</div>`;
  const title = mix.field === "source" ? "누가 답을 냈나 (에이전트 · 물러나기 · 템플릿 · 출력 없음)" : mix.field === "outcome" ? "판정 결과 구성" : "맞음 · 틀림";
  return `<div class="card"><h2>${esc(title)} <span class="muted">시스템마다 전체 사례를 100% 로</span></h2>${legend}${rows}</div>`;
}

// 칸 그림(히트맵): 행 = 시스템, 열 = 조건·종류. 칸 색은 파랑 한 색 진하기, 칸 안에 비율과 분자/분모
function vizHeatmap({ title, note, rows, cols, cell }) {
  const head = `<div class="viz-hm-row viz-hm-head" style="grid-template-columns:120px repeat(${cols.length}, minmax(64px, 1fr))"><span></span>${cols.map((c) => `<span>${esc(c)}</span>`).join("")}</div>`;
  const body = rows.map((r) => `<div class="viz-hm-row" style="grid-template-columns:120px repeat(${cols.length}, minmax(64px, 1fr))">
      <span class="viz-sys">${r.swatch ? `<i style="background:${r.swatch}"></i>` : ""}${esc(r.name)}</span>
      ${cols.map((c) => {
        const v = cell(r.key, c);
        if (!v) return '<span class="viz-hm-cell empty">-</span>';
        return `<span class="viz-hm-cell${v.mark ? " mark" : ""}" style="background:${vizSeq(v.rate)};color:${vizSeqInk(v.rate)}" title="${esc(r.name)} · ${esc(c)}: ${esc(v.tip)}">
          <b>${v.rate == null ? "-" : vizPct(v.rate)}</b><small>${esc(v.sub)}</small></span>`;
      }).join("")}</div>`).join("");
  const scale = `<div class="viz-scale"><span>0%</span>${VIZ_SEQ.map((c) => `<i style="background:${c}"></i>`).join("")}<span>100%</span></div>`;
  return `<div class="card"><h2>${esc(title)} <span class="muted">${esc(note)}</span></h2>${scale}<div class="viz-hm">${head}${body}</div></div>`;
}

function vizConditions(cond, systems) {
  if (!cond) return "";
  const rows = systems.filter((s) => cond.systems[s]).map((s) => ({ key: s, name: s, swatch: vizColor(s, systems) }));
  return vizHeatmap({
    title: "조건별 통과율", note: "진할수록 많이 통과 · 칸 = 통과/전체 (판단 불가는 따로)", rows, cols: cond.conditions,
    cell: (s, c) => {
      const v = cond.systems[s]?.[c];
      if (!v) return null;
      const total = v.pass + v.fail + v.unknown;
      return { rate: total ? v.pass / total : null, sub: `${v.pass}/${total}${v.unknown ? ` ?${v.unknown}` : ""}`, tip: `통과 ${v.pass}, 실패 ${v.fail}, 판단 불가 ${v.unknown}` };
    },
  });
}

function vizByKind(byKind, systems) {
  if (!byKind) return "";
  const rows = systems.filter((s) => byKind.systems[s]).map((s) => ({ key: s, name: s, swatch: vizColor(s, systems) }));
  return vizHeatmap({
    title: "종류별로 틀린 비율", note: `${byKind.what} · 진할수록 많이 틀림`, rows, cols: byKind.kinds,
    cell: (s, k) => {
      const v = byKind.systems[s]?.[k];
      return v ? { rate: v.rate, sub: `${v.wrong}/${v.total}${v.unknown ? ` ?${v.unknown}` : ""}`, tip: `틀림 ${v.wrong} / ${v.total}, 판단 불가 ${v.unknown}` } : null;
    },
  });
}

// 혼동 행렬: 분류기마다 작은 칸 그림 (행 = 정답, 열 = 예측, 칸 색 = 정답 행 안에서의 비율, 대각선 테두리 = 맞힌 칸)
function vizConfusion(confusion, systems) {
  if (!confusion) return "";
  const set = confusion.balanced ? "balanced" : Object.keys(confusion)[0];
  const tables = confusion[set] ?? {};
  const panels = Object.entries(tables).map(([system, rows]) => {
    const truths = Object.keys(rows);
    const preds = [...new Set(truths.flatMap((t) => Object.keys(rows[t])))];
    const order = (p) => { const i = truths.findIndex((t) => t.toLowerCase() === p.toLowerCase()); return i < 0 ? 99 : i; };
    preds.sort((a, b) => order(a) - order(b));
    const grid = `<div class="viz-cm" style="grid-template-columns:84px repeat(${preds.length}, 1fr)">
      <span class="muted small">정답 \\ 예측</span>${preds.map((p) => `<span class="muted small viz-cm-col">${esc(p)}</span>`).join("")}
      ${truths.map((t) => {
        const total = Object.values(rows[t]).reduce((a, b) => a + b, 0);
        return `<span class="small">${esc(t)} <span class="muted">${total}</span></span>` + preds.map((p) => {
          const n = rows[t][p] ?? 0;
          const rate = total ? n / total : null;
          const hit = p.toLowerCase() === t.toLowerCase();
          return `<span class="viz-hm-cell${hit ? " mark" : ""}" style="background:${vizSeq(rate)};color:${vizSeqInk(rate)}" title="정답 ${esc(t)} → ${esc(p)}: ${n}/${total}"><b>${n}</b></span>`;
        }).join("");
      }).join("")}</div>`;
    return `<div class="viz-cm-panel"><div class="viz-sys"><i style="background:${vizColor(system, systems)}"></i><b>${esc(system)}</b></div>${grid}</div>`;
  }).join("");
  return `<div class="card"><h2>혼동 행렬 · ${esc(set)} <span class="muted">행 = 정답, 열 = 예측 · 진할수록 그 정답 중 많이 · 테두리 칸이 맞힌 것</span></h2>
    <div class="viz-cm-wrap">${panels}</div></div>`;
}

// 문제 순위: 시스템마다 많이 걸린 까닭 가로 막대 (많은 것부터, 그 시스템 색 한 가지)
function vizProblems(problems, systems) {
  if (!problems) return "";
  const panels = systems.filter((s) => problems.systems[s]?.length).map((s) => {
    const rows = problems.systems[s];
    const max = Math.max(...rows.map((r) => r.count), 1);
    return `<div class="viz-rank"><div class="viz-sys"><i style="background:${vizColor(s, systems)}"></i><b>${esc(s)}</b></div>
      ${rows.map((r) => `<div class="viz-rank-row" title="${esc(r.label)}: ${r.count}건"><span class="viz-rank-label">${esc(r.label)}</span>
        <span class="viz-track"><span class="viz-fill" style="width:${(r.count / max) * 100}%;background:${vizColor(s, systems)}"></span></span>
        <span class="num small">${r.count}</span></div>`).join("")}</div>`;
  }).join("");
  return panels ? `<div class="card"><h2>많이 걸린 까닭 <span class="muted">시스템마다 상위 8개 · 같은 종류끼리 묶음 (따옴표 안 문구·숫자는 지움)</span></h2><div class="viz-rank-wrap">${panels}</div></div>` : "";
}

// 걸린 시간: 사례 하나 = 점 하나. 같은 가로축, 세로 막대 = 중앙값, 빨간 세로선 = 예산
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
    return `<text x="${L - 8}" y="${y + 4}" text-anchor="end" class="viz-axis-ink">${esc(s)}</text>
      ${values.map((v, k) => `<circle cx="${x(v).toFixed(1)}" cy="${(y + jitter(k)).toFixed(1)}" r="4" fill="${vizColor(s, systems)}" fill-opacity="0.55" stroke="#fcfcfb" stroke-width="1"><title>${esc(s)} ${v}초</title></circle>`).join("")}
      <line x1="${x(med)}" y1="${y - 10}" x2="${x(med)}" y2="${y + 10}" stroke="#0b0b0b" stroke-width="2"><title>${esc(s)} 중앙값 ${med.toFixed(1)}초</title></line>
      <text x="${W - R + 12}" y="${y + 4}" class="viz-axis-ink">중앙 ${med.toFixed(1)}초${within != null ? ` · 예산 안 ${within}/${values.length}` : ""}</text>`;
  }).join("");
  const grid = ticks.map((t) => `<line x1="${x(t)}" y1="${T}" x2="${x(t)}" y2="${H - 22}" stroke="#e1e0d9"/><text x="${x(t)}" y="${H - 8}" text-anchor="middle" class="viz-axis">${t}초</text>`).join("");
  const budget = latency.budget != null ? `<line x1="${x(latency.budget)}" y1="${T}" x2="${x(latency.budget)}" y2="${H - 22}" stroke="${VIZ_STATUS.critical}" stroke-width="2"/>
    <text x="${x(latency.budget) + 4}" y="${T + 10}" class="viz-axis-ink">예산 ${latency.budget}초</text>` : "";
  return `<div class="card"><h2>사례마다 걸린 시간 <span class="muted">점 하나 = 사례 하나 · 검은 세로 막대 = 중앙값${latency.budget != null ? " · 빨간 선 = 예산" : ""}</span></h2>
    <svg class="viz-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="사례마다 걸린 시간">${grid}${budget}${rows}</svg></div>`;
}

// 추세: 가는 선 + 점 + 끝 값 글자, 가로 격자, 기준점은 빈 동그라미. 점에 마우스를 올리면 값
function evalTrendSvg(t) {
  const points = t.points.filter((p) => p.value !== null && p.value !== undefined);
  if (!points.length) return '<div class="empty">값이 있는 실행이 없어요</div>';
  const runs = [...new Map(t.points.map((p) => [p.id, p])).values()];
  const systems = [...new Set(points.map((p) => p.system ?? "-"))];
  const ratio = t.points[0]?.unit === "ratio";
  const W = 680, H = 200, L = 46, R = 90, T = 14, B = 38;
  const values = points.map((p) => p.value);
  const lo = ratio ? 0 : Math.min(0, ...values), hi = ratio ? 1 : Math.max(...values, lo + 1e-9) * 1.1;
  const x = (i) => L + (runs.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (runs.length - 1));
  const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const fmtV = (v) => (ratio ? vizPct(v) : Number(v).toFixed(1));
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + (hi - lo) * f).map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" stroke="#e1e0d9"/>
    <text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="viz-axis">${esc(fmtV(v))}</text>`).join("");
  const lines = systems.map((s) => {
    const color = vizColor(s, systems);
    const pts = runs.map((r, i) => [i, points.find((p) => p.id === r.id && (p.system ?? "-") === s)]).filter(([, p]) => p);
    const path = pts.map(([i, p], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
    const [li, lp] = pts[pts.length - 1];
    return `<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` +
      pts.map(([i, p]) => `<circle cx="${x(i)}" cy="${y(p.value)}" r="${runs[i].baseline ? 6 : 4}" fill="${runs[i].baseline ? "#fcfcfb" : color}" stroke="${runs[i].baseline ? color : "#fcfcfb"}" stroke-width="2"><title>${esc(s)} ${esc(fmtV(p.value))}${p.denominator != null ? ` (${p.numerator}/${p.denominator})` : ""} · ${esc(runs[i].id)} · 커밋 ${esc(runs[i].commit ?? "-")}</title></circle>`).join("") +
      `<text x="${x(li) + 10}" y="${y(lp.value) + 4}" class="viz-axis-ink">${esc(s)} ${esc(fmtV(lp.value))}</text>`;
  }).join("");
  const axis = runs.map((r, i) => `<text x="${x(i)}" y="${H - 20}" text-anchor="middle" class="viz-axis mono">${esc(r.commit ?? "-")}</text>
      <text x="${x(i)}" y="${H - 6}" text-anchor="middle" class="viz-axis">${esc(time(r.started_at).slice(0, 11))}</text>`).join("");
  return `${systems.length > 1 ? vizLegend(systems) : ""}<svg class="viz-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t.metric)} 추세">${grid}${axis}${lines}</svg>
    <div class="muted small">아래는 커밋과 시각 · 빈 동그라미 = 기준점 · ${t.higher_is_better === false ? "낮을수록 좋음" : "높을수록 좋음"} · 점에 마우스를 올리면 값</div>`;
}

// 실행 목록의 대표 지표: 시스템마다 작은 막대 (비율일 때)
function vizHeadline(r) {
  const systems = r.systems;
  return r.headline.map((m) => {
    const bar = m.unit === "ratio" && m.value != null
      ? `<span class="viz-mini"><span style="width:${m.value * 100}%;background:${vizColor(m.system ?? "-", systems)}"></span></span>` : "";
    return `<span class="viz-head-item"><span class="muted small">${esc(m.system ?? "")} ${esc(m.id)}</span>${bar}${evalValue(m)}</span>`;
  }).join("");
}
