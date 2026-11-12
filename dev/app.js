// 도나 개발자 대시보드 화면 동작.
// 탭마다 render 함수 하나가 서버 /api/dev_tools/... 를 불러 그린다. 라이브러리 없이 HTML 글자로 그린다.
// 서버 글(리뷰, 가게 이름 등)은 모두 esc() 로 감싸서 HTML 로 해석되지 않게 한다.

const API = "/api/dev_tools";
const state = { tab: "overview", storeId: null, usageDays: 30 };
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

// ── 탭: 개요 ──

async function renderOverview() {
  const o = await api(`${API}/overview`);
  const shift = o.clock_shift_minutes ? ` (시계 +${Math.round(o.clock_shift_minutes / 60)}시간)` : "";
  return `
    <div class="stats">
      ${stat("총 매장", num(o.stores_total), `목업 ${o.stores_mock} · 등록 ${o.registered_stores}`, true)}
      ${stat("연결된 사장님 계정", num(o.owners), "네이버 로그인으로 가게를 등록한 계정")}
      ${stat("오늘 CLOVA 호출", num(o.clova_today.calls), `토큰 ${num(o.clova_today.input_tokens + o.clova_today.output_tokens)}`)}
      ${stat("이번 달 CLOVA 비용", o.price_set ? won(o.clova_month.cost_won) : "단가 미설정", o.price_set ? `이번 달 예상 ${won(o.clova_month.projected_cost_won)}` : ".env 에 CLOVA_PRICE_*_PER_1K 를 넣어 주세요")}
    </div>
    <div class="grid-2">
      <div class="card"><h2>업종 분포</h2>${bars(o.categories.map((c) => ({ label: c.name, value: c.count })), { valueText: (r) => `${r.value}곳` })}</div>
      <div class="card"><h2>서버 상태</h2>
        ${table(["항목", "값"], [
          ["지금 서버 시각", `<span class="mono">${esc(time(o.now))}</span>${esc(shift)}`],
          ["계산해 둔 가게", `${o.computed_stores} / ${o.stores_total}곳`],
          ["이번 달 CLOVA 호출", `${num(o.clova_month.calls)}번 (실패 ${num(o.clova_month.failed)})`],
          ["이번 달 토큰", `입력 ${num(o.clova_month.input_tokens)} · 출력 ${num(o.clova_month.output_tokens)}`],
        ])}
      </div>
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

async function renderAnalysis() {
  const a = await api(`${API}/analysis?store_id=${state.storeId}`);
  const rs = a.review_summary;
  const busy = a.calendar.filter((c) => c.signal === "HIGH");
  return `
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
  return `${rules}${days || '<div class="card"><div class="empty">이 기간에는 알림이 없어요</div></div>'}`;
}

// ── 탭: AI 비용 ──

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

// ── 탭: AI 품질 ──

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

// ── 탭: 시스템 ──

async function renderSystem() {
  const s = await api(`${API}/system`);
  const onOff = (v) => `<span class="dot ${v ? "on" : "off"}"></span>${v ? "켜짐" : "꺼짐"}`;
  const has = (v) => `<span class="dot ${v ? "on" : "off"}"></span>${v ? "있음" : "없음"}`;
  return `
    <div class="card"><h2>API 상태</h2>
      <div class="control-actions"><button class="btn" id="health">헬스체크 실행</button><span id="health-result" class="muted"></span></div>
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
      ${table(["아이디", "비밀번호", "시나리오", "연결된 가게"], s.test_accounts.map((a) => [
        `<span class="mono">${esc(a.login_id)}</span>`, `<span class="mono">${esc(a.password)}</span>`, esc(a.scenario),
        a.linked_store ? `<span class="tag blue">${esc(a.linked_store)}</span>` : '<span class="muted small">없음</span>',
      ]))}
    </div>
    <div class="card"><h2>서버</h2>${table(["항목", "값"], [
      ["boot_id (서버가 켜질 때마다 바뀜)", `<span class="mono small">${esc(s.boot_id)}</span>`],
      ["지금 서버 시각", `<span class="mono">${esc(time(s.now))}</span>`],
      ["시계 앞당김", `${Math.round(s.clock_shift_minutes / 60)}시간`],
    ])}</div>`;
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
    <div class="card"><h2>가상 시각 <span class="muted">지금 앞당김 ${Math.round(s.clock_shift_minutes / 60)}시간 · 서버 시각 ${esc(time(s.now))}</span></h2>
      <div class="control-row"><div><b>서버 시계 앞당기기</b><div class="desc">"내일 아침이면 어떤 알림이 뜰까?"를 바로 봐요. 앱도 서버와 같은 시각을 봐요</div></div>
        <div class="control-actions">
          <button class="btn-outline" data-clock="60" ${clockOn ? "" : "disabled"}>+1시간</button>
          <button class="btn-outline" data-clock="360" ${clockOn ? "" : "disabled"}>+6시간</button>
          <button class="btn-outline" data-clock="1440" ${clockOn ? "" : "disabled"}>+1일</button>
          <button class="btn-outline" data-clock="saturday" ${clockOn ? "" : "disabled"}>이번 토요일 10:05</button>
          <button class="btn" data-clock="reset" ${clockOn ? "" : "disabled"}>실제 시각으로</button>
        </div></div>
    </div>
    <div class="card"><h2>AI</h2>
      <div class="control-row"><div><b>카드 문장 다듬기 (CLOVA)</b><div class="desc">지금 ${s.switches.SENTENCE_POLISH_ENABLED ? "켜짐" : "꺼짐"}. 서버를 다시 켜면 .env 값으로 돌아가요</div></div>
        <div class="control-actions"><button class="btn-outline" data-polish="${s.switches.SENTENCE_POLISH_ENABLED ? "off" : "on"}">${s.switches.SENTENCE_POLISH_ENABLED ? "끄기" : "켜기"}</button></div></div>
      <div class="control-row"><div><b>CLOVA 사용 기록 지우기</b><div class="desc">AI 비용·품질 탭의 기록을 처음부터 다시 쌓아요</div></div>
        <div class="control-actions"><button class="btn-danger" data-action="clear-log">기록 지우기</button></div></div>
    </div>
    <div class="card"><h2>처음 상태로</h2>
      <div class="control-row"><div><b>데모 초기화</b><div class="desc">등록한 가게, 불러온 리뷰, 로그인 기록, 고친 설정, 계산 결과를 지우고 시계를 실제 시각으로 돌려요. 목업 가게(s001~s003)는 그대로예요</div></div>
        <div class="control-actions"><button class="btn-danger" data-action="reset" ${clockOn ? "" : "disabled"}>초기화</button></div></div>
      <div class="control-row"><div><b>앱 열기</b><div class="desc">mobile/ 앱을 웹으로 켠 주소</div></div>
        <div class="control-actions"><a class="btn-outline" href="http://localhost:8082" target="_blank" rel="noopener">http://localhost:8082 열기</a></div></div>
    </div>`;
}

async function moveClock(kind) {
  const s = await api(`${API}/system`);
  let minutes = s.clock_shift_minutes;
  if (kind === "reset") minutes = 0;
  else if (kind === "saturday") {
    // 서버 시각(앞당긴 시각) 기준으로 이번 토요일 10:05 까지 남은 분만큼 더 앞당긴다. 이미 지났으면 다음 주 토요일
    const now = new Date(s.now);
    const today = s.now.slice(0, 10);
    const weekday = new Date(`${today}T12:00:00+09:00`).getUTCDay(); // 0=일 ~ 6=토 (서울 날짜 기준)
    let target = new Date(new Date(`${today}T10:05:00+09:00`).getTime() + ((6 - weekday + 7) % 7) * 86400e3);
    if (target <= now) target = new Date(target.getTime() + 7 * 86400e3);
    minutes += Math.round((target - now) / 60000);
  } else minutes += Number(kind);
  const r = await api(`/dev/clock?hours=${minutes / 60}`, { method: "POST" });
  toast(`서버 시각 ${time(r.now)}`);
}

// ── 탭: 시연 (Figma UC01~UC16) ──
// 가게를 고르면 서버가 그 가게 시연 기간(2주)을 훑어 UC01~UC16 단계를 만든다 (/api/dev_tools/demo_steps).
// 단계를 누르면 서버 시계를 그 단계 시각으로 옮기고(demo_go), 오른쪽 휴대폰 틀에 앱 입구(/demo-jump)를 연다.
// 휴대폰 틀이 다시 그려지지 않도록, 이 탭의 버튼은 화면 전체를 다시 그리지 않고 필요한 곳만 바꾼다.

const DEMO_APP_KEY = "dona-dev-app-url";
const demo = { steps: {}, index: -1, appUrl: (() => { try { return localStorage.getItem(DEMO_APP_KEY) || "http://localhost:8082"; } catch { return "http://localhost:8082"; } })() };

function demoJumpUrl(step) {
  const q = new URLSearchParams({ store: state.storeId, t: String(Date.now()) });
  for (const [k, v] of Object.entries(step.open)) {
    if (v === true) q.set(k, "1");
    else if (v !== null && v !== undefined && v !== false && k !== "note") q.set(k, String(v));
  }
  return `${demo.appUrl.replace(/\/+$/, "")}/demo-jump?${q}`;
}

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

async function renderDemo() {
  const stores = await api(`${API}/stores`);
  if (!demo.steps[state.storeId]) demo.steps[state.storeId] = await api(`${API}/demo_steps?store_id=${state.storeId}`);
  const d = demo.steps[state.storeId];
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
      <div class="card demo-stores"><h2>가게</h2>
        ${stores.map((s) => `<button class="demo-store ${s.store_id === state.storeId ? "on" : ""}" data-demo-store="${esc(s.store_id)}">
          <b>${esc(s.name)}</b><div class="muted small">${esc(s.store_id)} · ${esc(s.category)} ${s.kind === "registered" ? "· 등록" : ""}</div></button>`).join("")}
        <div class="demo-tools">
          <label class="muted small">앱 주소<input id="demo-app-url" value="${esc(demo.appUrl)}"></label>
          <button class="btn-outline small" data-demo-action="rescan">이 가게 다시 훑기</button>
          <button class="btn-outline small" data-demo-action="clock-reset">시계 실제 시각으로</button>
        </div>
      </div>
      <div class="card demo-steps"><h2>${esc(d.store.name)} <span class="muted">시연 기간 ${esc(d.demo_week.first)} ~ ${esc(d.demo_week.last)} · 열 수 있는 화면 ${available} / ${d.steps.length}</span></h2>
        ${d.unavailable ? `<div class="note">${esc(d.unavailable)}</div>` : ""}
        ${groups}
      </div>
      <div class="demo-phone-col">
        <div class="demo-nav">
          <button class="btn-outline" data-demo-action="prev">◀ 이전</button>
          <div id="demo-now" class="small muted">단계를 누르거나 다음을 눌러 시작해요</div>
          <button class="btn" data-demo-action="next">다음 ▶</button>
        </div>
        <div class="demo-phone"><iframe id="demo-frame" title="도나 앱" src="about:blank"></iframe></div>
        <div class="muted small">앱은 <span class="mono">cd mobile && npm run web</span> 로 켜 두세요. 서버는 DEV_CLOCK_ENABLED=true 여야 시계를 옮길 수 있어요.</div>
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
  row?.scrollIntoView({ block: "nearest" });
  const label = document.getElementById("demo-now");
  label.textContent = `${step.uc} · ${step.figma} 여는 중…`;
  if (step.at) await api(`${API}/demo_go`, { method: "POST", body: JSON.stringify({ store_id: state.storeId, at: step.at }) });
  document.getElementById("demo-frame").src = demoJumpUrl(step);
  label.textContent = `${step.uc} · ${step.figma} ${step.title}${step.at_label ? ` · 서버 시각 ${step.at_label}` : ""}`;
  checkServer();
}

function nextDemoIndex(direction) {
  const steps = demo.steps[state.storeId]?.steps ?? [];
  for (let i = demo.index + direction; i >= 0 && i < steps.length; i += direction) if (steps[i].available) return i;
  return -1;
}

async function onDemoClick(button) {
  const { demoStep, demoStore, demoAction } = button.dataset;
  if (demoStep !== undefined) return openDemoStep(Number(demoStep));
  if (demoStore) {
    state.storeId = demoStore;
    demo.index = -1;
    document.getElementById("store-select").value = demoStore;
    try { localStorage.setItem("dona-dev-store", demoStore); } catch {}
    return show("demo");
  }
  if (demoAction === "next" || demoAction === "prev") {
    const i = nextDemoIndex(demoAction === "next" ? 1 : -1);
    return i >= 0 ? openDemoStep(i) : toast(demoAction === "next" ? "마지막 단계예요" : "첫 단계예요");
  }
  if (demoAction === "rescan") {
    button.disabled = true;
    toast("시연 기간을 다시 훑어요 (30초쯤)");
    demo.steps[state.storeId] = await api(`${API}/demo_rescan?store_id=${state.storeId}`, { method: "POST" });
    demo.index = -1;
    return show("demo");
  }
  if (demoAction === "clock-reset") {
    const r = await api(`${API}/demo_clock_reset?store_id=${state.storeId}`, { method: "POST" });
    toast(`서버 시각 ${time(r.now)}`);
    return checkServer();
  }
}

// ── 탭 전환, 버튼 ──

const RENDER = {
  demo: renderDemo,
  overview: renderOverview,
  stores: renderStores,
  analysis: renderAnalysis,
  timeline: renderTimeline,
  usage: renderUsage,
  quality: renderQuality,
  system: renderSystem,
  controls: renderControls,
};

async function show(tab = state.tab) {
  state.tab = tab;
  try { localStorage.setItem("dona-dev-tab", tab); } catch {}
  if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const loading = tab === "demo" && !demo.steps[state.storeId]
    ? "시연 기간을 훑는 중… (가게마다 처음 한 번 30초쯤 걸려요)"
    : "불러오는 중… (가게를 처음 계산하면 몇 초 걸려요)";
  content.innerHTML = `<div class="card"><div class="empty">${loading}</div></div>`;
  try {
    content.innerHTML = await RENDER[tab]();
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
  try { localStorage.setItem("dona-dev-store", state.storeId); } catch {}
  show();
});

content.addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  // 시연 탭 버튼은 휴대폰 틀을 살려 두려고 화면 전체를 다시 그리지 않는다
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
    if (action === "clear-log" && confirm("CLOVA 사용 기록을 모두 지울까요?")) {
      await api(`${API}/clova_log/clear`, { method: "POST" });
      toast("CLOVA 기록을 지웠어요");
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

content.addEventListener("change", (e) => {
  if (e.target.id !== "demo-app-url") return;
  demo.appUrl = e.target.value.trim() || "http://localhost:8082";
  try { localStorage.setItem(DEMO_APP_KEY, demo.appUrl); } catch {}
  toast(`앱 주소 ${demo.appUrl}`);
});

(async function start() {
  // 주소 끝의 #analysis 같은 탭 이름이 있으면 그 탭부터 연다. 없으면 지난번에 본 탭
  const fromHash = location.hash.slice(1);
  if (RENDER[fromHash]) state.tab = fromHash;
  else try { state.tab = localStorage.getItem("dona-dev-tab") || state.tab; } catch {}
  await checkServer();
  await loadStores();
  show();
  setInterval(checkServer, 30000);
})();
