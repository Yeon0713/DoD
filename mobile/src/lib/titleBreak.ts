// 제목·본문 줄 나누기 규칙. 사장님이 한눈에 읽게, 줄을 글자 수가 아니라 뜻의 덩어리로 나눈다.
// 규칙 설명과 예는 docs/title-line-break.md (화면 글을 새로 쓸 때도 같은 규칙을 따른다).
//
// 1. 한 줄에 들어가면 한 줄로 둔다.
// 2. 띄어쓰기 자리에서만 나눈다 (단어 가운데서 나누지 않는다).
// 3. 함께 읽어야 하는 말은 한 덩어리로 묶어 그 사이에서는 나누지 않는다.
//    - 서술어 덩어리: 본용언 + 보조용언 ("확인해 주세요", "바꿔 드릴게요", "보내지 않아요", "할 수 있어요")
//    - 꾸밈말 + 꾸밈받는 말: 관형어("온 숫자", "할 일", "바쁜 시간"), 관형사("이번 주말"), 부사("다시 열어", "조용히 할게요"),
//      조사 없는 수량("1개 남았어요", "3시에")
// 4. 줄을 바꿔야 하면 나눌 자리를 이 순서로 고른다.
//    ① 문장이 끝나는 자리(. ? !) 뒤
//    ② 마지막 덩어리(서술어) 앞 — 서술어를 아랫줄로 내리고 윗줄을 채운다 ("문자로 온 숫자 6자리를 / 입력해주세요.")
//    ③ 조사나 쉼표로 끝나는 덩어리 뒤 가운데 윗줄을 가장 많이 채우는 자리
//    ④ 윗줄에 들어가는 가장 뒤 덩어리 뒤
//    아랫줄도 넘치면 남은 글에 같은 규칙을 다시 쓴다.

// 굵은 Noto Sans KR 글자 폭 (글자 크기 1 기준, 웹에서 잰 값)
const WIDTH = { hangul: 0.92, space: 0.28, digit: 0.59, latin: 0.62, narrow: 0.33, mark: 0.5 };

function charWidth(ch: string): number {
  if (ch === " ") return WIDTH.space;
  if (/[0-9]/.test(ch)) return WIDTH.digit;
  if (/[A-Za-z]/.test(ch)) return WIDTH.latin;
  if (/[.,·:;'"()[\]]/.test(ch)) return WIDTH.narrow;
  if (/[?!~%-]/.test(ch)) return WIDTH.mark;
  return WIDTH.hangul;
}

/** 글 폭 (글자 크기 배수) */
export function textWidth(text: string): number {
  let w = 0;
  for (const ch of text) w += charWidth(ch);
  return w;
}

// ── 덩어리 묶기 ──

// 앞말에 붙는 보조용언·의존 명사로 시작하는 어절
const AUX = /^(주세요|주셔|주실|줘요|줘|줄게요|줄까요|주고|드려요|드릴게요|드릴까요|드렸어요|드립니다|드릴|봐요|볼게요|볼까요|보세요|봤어요|보여요|있어요|있었어요|있나요|있을|있는|없어요|없었어요|없는|않아요|않았어요|않을|않게|않고|같아요|두세요|둘게요|뒀어요|둬요|놓을게요|놨어요|놓았어요|버렸어요|버려요|싶어요|하세요|해요|했어요|할게요|돼요|됐어요|될게요)/;
// 보조용언 앞에 오는 연결 어미로 끝나는 어절 (적어 / 확인해 / 보내지 / 하고)
const CONNECTIVE_END = /(어|아|여|해|워|와|봐|줘|고|지|게|러)$/;
// ㄹ 받침 관형어 뒤에 오는 의존 명사 (할 수, 볼 거예요, 쓸 줄)
const BOUND_NOUN = /^(수|거|것|줄|적|때|만큼)/;
// 뒷말을 꾸미는 관형사·부사 (그대로 같은 어절일 때)
const MODIFIER_WORDS = new Set([
  "이", "그", "저", "이번", "새", "첫", "다른", "모든", "각", "매", "몇", "어느", "무슨", "다음", "지난", "오늘", "내일", "어제",
  "다시", "바로", "먼저", "같이", "함께", "잘", "꼭", "미리", "모두", "다", "더", "안", "못", "곧", "또", "좀", "아직", "이미",
  "지금", "벌써", "가장", "제일", "아주", "매우", "정말", "너무", "대신", "직접", "따로", "계속", "빨리", "천천히", "얼른",
]);
// 관형어(동사·형용사가 명사를 꾸미는 꼴)로 끝나는 어절: 늦었다는, 하는, 바쁜, 새로운, 온, 할 …
const ADNOMINAL_END = /(다는|하는|되는|있는|없는|오는|가는|보는|주는|받는|쓰는|던|로운|러운|쁜|픈|른|좋은|많은|작은|늦은|높은|낮은|된|온|할|볼|갈|쓸|될|올)$/;
// 조사·쉼표로 끝나는 어절 (덩어리가 끝나는 자연스러운 자리)
const PARTICLE_END = /(을|를|은|는|이|가|에|에서|에게|께|로|으로|와|과|도|만|의|까지|부터|보다|처럼|한테|엔|서|,|고|며|면|지만|데|니까)$/;
const SENTENCE_END = /[.?!]$/;

/** 이 어절이 뒷말을 꾸며서 뒷말과 붙어야 하는지 */
function gluesForward(word: string): boolean {
  if (MODIFIER_WORDS.has(word)) return true;
  if (/^[가-힣]+히$/.test(word) && word.length >= 2) return true; // 조용히, 천천히
  if (/^[가-힣]+게$/.test(word) && word.length >= 3 && !/가게$/.test(word)) return true; // 빠르게, 새롭게 (가게 같은 명사는 빼려고 3글자 이상)
  if (/^[0-9]+[가-힣]*$/.test(word) && !PARTICLE_END.test(word)) return true; // 조사 없는 수량: 1개, 3시
  return ADNOMINAL_END.test(word) && !/[을를]$/.test(word);
}

/** 이 어절이 앞말에 붙는 보조용언·의존 명사인지 */
function gluesBackward(prev: string, word: string): boolean {
  if (AUX.test(word) && (CONNECTIVE_END.test(prev) || /^(수|거|것|줄|적)$/.test(prev))) return true; // 적어 주세요, 받을 수 있어요
  return BOUND_NOUN.test(word) && /[할볼갈쓸될올을]$/.test(prev);
}

/** 어절을 함께 읽는 덩어리로 묶는다 */
export function chunks(text: string): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const out: string[] = [];
  let glueNext = false;
  for (const word of words) {
    const last = out[out.length - 1];
    const lastWord = last?.split(" ").pop() ?? "";
    if (last !== undefined && (glueNext || gluesBackward(lastWord, word))) out[out.length - 1] = `${last} ${word}`;
    else out.push(word);
    glueNext = gluesForward(word) && !SENTENCE_END.test(word);
  }
  return out;
}

// ── 나눌 자리 고르기 ──

/**
 * 제목을 폭(글자 크기 배수)에 맞춰 줄을 나눈 글을 돌려준다 (줄 사이는 "\n").
 * maxWidth 는 한 줄에 들어가는 폭을 글자 크기로 나눈 값 (예: 327px / 28px).
 */
export function breakTitle(text: string, maxWidth: number): string {
  const flat = text.replace(/\s*\n\s*/g, " ").trim();
  if (textWidth(flat) <= maxWidth) return flat;
  const parts = chunks(flat);
  if (parts.length < 2) return flat;
  const fits = (from: number, to: number) => textWidth(parts.slice(from, to).join(" ")) <= maxWidth;

  const lines: string[] = [];
  let start = 0;
  while (start < parts.length) {
    if (fits(start, parts.length)) {
      lines.push(parts.slice(start).join(" "));
      break;
    }
    const cut = pickCut(parts, start, fits);
    lines.push(parts.slice(start, cut).join(" "));
    start = cut;
  }
  return lines.join("\n");
}

/** parts[start..] 에서 윗줄을 parts[start..cut) 로 할 자리 cut 을 고른다 */
function pickCut(parts: string[], start: number, fits: (from: number, to: number) => boolean): number {
  const end = parts.length;
  const candidates: number[] = [];
  for (let cut = end - 1; cut > start; cut--) if (fits(start, cut)) candidates.push(cut); // 뒤에서부터 (윗줄을 많이 채우는 순)
  if (!candidates.length) return start + 1; // 덩어리 하나도 넘치면 그 덩어리만 한 줄로 (그 안에서는 화면이 단어 단위로 접는다)
  const endsWith = (re: RegExp) => (cut: number) => re.test(parts[cut - 1]);
  // ① 문장이 끝나는 자리
  const sentence = candidates.find(endsWith(SENTENCE_END));
  if (sentence) return sentence;
  // ② 서술어(마지막 덩어리)를 아랫줄로
  if (candidates[0] === end - 1) return end - 1;
  // ③ 조사·쉼표로 끝나는 자리 중 윗줄을 가장 많이 채우는 곳
  const particle = candidates.find(endsWith(PARTICLE_END));
  if (particle) return particle;
  // ④ 윗줄에 들어가는 가장 뒤
  return candidates[0];
}
