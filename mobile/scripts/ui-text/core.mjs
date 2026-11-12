// 앱 화면 글(한글)을 코드에서 뽑고, 고친 글을 코드에 다시 넣는다.
// - 뽑기: src/app, src/components, src/lib 의 .ts/.tsx 를 TypeScript 파서로 읽어 한글이 든 글(문자열, `템플릿`, JSX 글)을 모은다.
//   주석, import, 타입, 비교·검사에 쓰는 문자열(=== "점심", startsWith("인사") 등)은 뺀다.
// - 묶기: 화면 경로(src/app/**) → 그 화면이 쓰는 함수 → 그 함수가 쓰는 함수 … 를 따라가 글을 화면별로 묶는다.
//   한 화면에서만 쓰면 그 화면, 여러 화면이 쓰면 "여러 화면이 같이 쓰는 글".
// - 적용: edits.json 의 [수정] 글을 원래 자리(파일, 함수, 원본 글이 같은 곳)에 넣는다. 넣은 수정은 edits.json 에서 지운다.
//   코드가 바뀌어 원본을 못 찾으면 넣지 않고 남겨 둔다.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import ts from "typescript";

export const MOBILE = path.resolve(import.meta.dirname, "..", "..");
const SRC = path.join(MOBILE, "src");
const DIRS = ["app", "components", "lib"];
const HANGUL = /[가-힣]/;
export const EDITS_FILE = path.join(import.meta.dirname, "edits.json");
const SCREENS_FILE = path.join(import.meta.dirname, "screens.json");

const rel = (abs) => path.relative(MOBILE, abs).split(path.sep).join("/");

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.(test|spec)\.|\.d\.ts$/.test(name)) out.push(p);
  }
  return out;
}

function parse(file) {
  const text = readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  return { text, sf };
}

/** 노드가 들어 있는 맨 위 선언의 이름 (함수, 변수, default) */
function topName(node) {
  let n = node;
  while (n.parent && !ts.isSourceFile(n.parent)) n = n.parent;
  if (ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n)) return n.name?.text ?? "default";
  if (ts.isVariableStatement(n)) {
    const d = n.declarationList.declarations[0];
    return ts.isIdentifier(d.name) ? d.name.text : "(변수)";
  }
  if (ts.isExportAssignment(n)) return "default";
  return "(파일)";
}

const COMPARE_CALLS = new Set(["startsWith", "endsWith", "includes", "indexOf", "split", "replace", "replaceAll", "match", "test", "has", "get", "getItem", "setItem"]);

/** 화면에 보이지 않는(코드 동작에 쓰는) 문자열이면 true */
function isCodeOnly(node) {
  const p = node.parent;
  if (!p) return true;
  if (ts.isPropertyAssignment(p) && p.name === node) return true; // { "점심": … } 의 키
  if (ts.isElementAccessExpression(p)) return true;
  if (ts.isCaseClause(p)) return true;
  if (ts.isBinaryExpression(p) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(p.operatorToken.kind)) return true;
  if (ts.isCallExpression(p) && ts.isPropertyAccessExpression(p.expression) && COMPARE_CALLS.has(p.expression.name.text)) return true;
  if (ts.isTaggedTemplateExpression(p)) return true;
  for (let a = p; a; a = a.parent) {
    if (ts.isImportDeclaration(a) || ts.isExportDeclaration(a) || ts.isTypeNode(a)) return true;
    if (ts.isCallExpression(a) && ts.isPropertyAccessExpression(a.expression) && ts.isIdentifier(a.expression.expression) && a.expression.expression.text === "console") return true;
  }
  return false;
}

const ATTR_LABEL = {
  title: "제목",
  placeholder: "입력칸 예시",
  accessibilityLabel: "읽어 주기 이름 (화면엔 안 보임)",
  accessibilityHint: "읽어 주기 설명 (화면엔 안 보임)",
  label: "이름표",
  sub: "설명",
  subtitle: "설명",
  description: "설명",
  desc: "설명",
  body: "설명",
  hint: "설명",
  note: "설명",
  right: "오른쪽 글",
  badge: "띠",
  tag: "띠",
};
const KEY_LABEL = { ...ATTR_LABEL, text: "글", name: "이름", title: "제목", line: "설명", cta: "버튼", primary: "버튼", secondary: "버튼", button: "버튼", later: "버튼", toast: "띠", error: "오류" };
const CALL_LABEL = { flashToast: "띠 (잠깐 뜨는 알림)", setErr: "오류", setError: "오류", setServerNote: "안내", setNote: "안내", alert: "확인 창", confirm: "확인 창" };

/** 그 글이 화면 어디에 쓰이는지 짐작한 이름 */
function roleOf(node) {
  const base = baseRole(node);
  for (let a = node.parent; a; a = a.parent) {
    if (ts.isJsxElement(a) && a.openingElement.tagName.getText() === "Sheet") return base === "제목" ? "시트 제목" : `시트 안 ${base}`;
    if (ts.isJsxSelfClosingElement(a) && a.tagName.getText() === "Sheet") return base === "제목" ? "시트 제목" : `시트 안 ${base}`;
  }
  return base;
}

function baseRole(node) {
  let n = node;
  for (let i = 0; i < 8 && n.parent; i++) {
    const p = n.parent;
    if (ts.isJsxAttribute(p)) {
      const name = p.name.getText();
      return ATTR_LABEL[name] ?? `${name} 칸`;
    }
    if (ts.isJsxElement(p)) {
      const tag = p.openingElement.tagName.getText();
      if (/Button|Pressable|Link/.test(tag)) return "버튼";
      const cls = p.openingElement.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText() === "className");
      const c = cls?.initializer?.getText() ?? "";
      if (/text-display|text-title|text-h1|text-h2/.test(c)) return "제목";
      if (/text-small|text-caption/.test(c)) return "작은 글";
      return "글";
    }
    if (ts.isCallExpression(p)) {
      const callee = p.expression.getText().split(".").pop();
      if (CALL_LABEL[callee]) return CALL_LABEL[callee];
    }
    if (ts.isPropertyAssignment(p) && p.initializer === n) {
      const key = p.name.getText().replace(/["']/g, "");
      return KEY_LABEL[key] ?? `이름 (${key})`;
    }
    if (ts.isThrowStatement(p) || (ts.isNewExpression(p) && /Error|Failure/.test(p.expression.getText()))) return "오류";
    n = p;
  }
  return "글";
}

/** `${…}` 자리들을 순서대로 */
export function placeholders(s) {
  const out = [];
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "$" && s[i + 1] === "{") {
      let depth = 0;
      let j = i + 1;
      for (; j < s.length; j++) {
        if (s[j] === "{") depth++;
        else if (s[j] === "}" && --depth === 0) break;
      }
      out.push(s.slice(i, j + 1));
      i = j;
    }
  }
  return out;
}

const hash = (s) => createHash("sha1").update(s).digest("hex").slice(0, 8);

/** 한 파일의 글들. 각 글은 원래 자리(start, end)와 다시 쓰는 법(encode)을 가진다 */
function stringsOf(file) {
  const { text, sf } = parse(file);
  const r = rel(file);
  const found = [];
  const visit = (node) => {
    let kind = null;
    if (ts.isStringLiteral(node) && HANGUL.test(node.text)) kind = "string";
    else if ((ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateExpression(node)) && HANGUL.test(node.getText(sf))) kind = "template";
    else if (ts.isJsxText(node) && HANGUL.test(node.text)) kind = "jsx";
    if (kind && !isCodeOnly(node)) {
      const start = kind === "jsx" ? node.pos : node.getStart(sf);
      const end = node.end;
      const src = text.slice(start, end);
      let shown;
      let quote = null;
      if (kind === "string") {
        shown = node.text;
        quote = src[0];
      } else if (kind === "template") {
        shown = src.slice(1, -1).replace(/\\n/g, "\n").replace(/\\`/g, "`");
      } else {
        shown = src.replace(/\s+/g, " ").trim();
      }
      found.push({ file: r, start, end, src, kind, quote, text: shown, func: topName(node), label: roleOf(node), line: sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1 });
      if (kind === "template") return; // 안의 ${…} 는 템플릿과 함께 고친다
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  // 같은 함수 안에 같은 글이 여러 번 있으면 순서 번호로 나눈다
  const seen = new Map();
  for (const s of found) {
    const k = `${s.func}\u0000${s.text}`;
    const n = seen.get(k) ?? 0;
    seen.set(k, n + 1);
    s.id = `${s.file}::${s.func}::${hash(s.text)}::${n}`;
    s.placeholders = s.kind === "template" ? placeholders(s.text) : [];
  }
  return found;
}

/** 고친 글을 코드 모양으로 */
function encode(s, edited) {
  if (s.kind === "string") {
    const q = s.quote;
    return q + edited.replace(/\\/g, "\\\\").replace(new RegExp(q, "g"), `\\${q}`).replace(/\r?\n/g, "\\n") + q;
  }
  if (s.kind === "template") {
    return "`" + edited.replace(/\\(?![$`\\])/g, "\\\\").replace(/(?<!\\)`/g, "\\`").replace(/\r?\n/g, "\\n") + "`";
  }
  const lead = s.src.match(/^\s*/)[0];
  const trail = s.src.match(/\s*$/)[0];
  const body = /[{}<>\n]/.test(edited) ? `{${JSON.stringify(edited)}}` : edited;
  return lead + body + trail;
}

// ---------- 화면별로 묶기 ----------

function resolveImport(fromFile, spec) {
  let base;
  if (spec.startsWith("@/")) base = path.join(SRC, spec.slice(2));
  else if (spec.startsWith(".")) base = path.resolve(path.dirname(fromFile), spec);
  else return null;
  for (const cand of [base, `${base}.tsx`, `${base}.ts`, path.join(base, "index.tsx"), path.join(base, "index.ts")]) {
    if (existsSync(cand) && statSync(cand).isFile()) return cand;
  }
  return null;
}

function routeOf(appFile) {
  const parts = path.relative(path.join(SRC, "app"), appFile).replace(/\.(tsx|ts)$/, "").split(path.sep);
  if (parts.at(-1) === "_layout") return null;
  const kept = parts.filter((p) => !/^\(.*\)$/.test(p));
  if (kept.at(-1) === "index") kept.pop();
  return "/" + kept.join("/");
}

/** 파일마다: 맨 위 선언 이름 → 그 선언이 쓰는 (파일#이름) 목록 */
function graphOf(files) {
  const edges = new Map(); // key → Set(key)
  for (const file of files) {
    const { sf } = parse(file);
    const imports = new Map(); // 로컬 이름 → key
    const decls = new Set();
    for (const st of sf.statements) {
      if (ts.isImportDeclaration(st) && st.importClause) {
        const target = resolveImport(file, st.moduleSpecifier.text);
        if (!target) continue;
        // foo.ts 를 불러오면 휴대폰 앱에서 쓰는 foo.native.ts 도 함께 본다
        const native = target.replace(/\.(tsx?)$/, ".native.$1");
        const targets = existsSync(native) ? [target, native] : [target];
        const ic = st.importClause;
        if (ic.name) imports.set(ic.name.text, targets.map((t) => `${t}#default`));
        if (ic.namedBindings && ts.isNamedImports(ic.namedBindings)) {
          for (const el of ic.namedBindings.elements) imports.set(el.name.text, targets.map((t) => `${t}#${(el.propertyName ?? el.name).text}`));
        }
      } else {
        const name = topName(st);
        if (name && !name.startsWith("(")) decls.add(name);
      }
    }
    for (const st of sf.statements) {
      if (ts.isImportDeclaration(st)) continue;
      const name = topName(st);
      const key = `${file}#${name}`;
      const set = edges.get(key) ?? new Set();
      const look = (n) => {
        if (ts.isIdentifier(n)) {
          if (imports.has(n.text)) for (const k of imports.get(n.text)) set.add(k);
          else if (decls.has(n.text) && n.text !== name) set.add(`${file}#${n.text}`);
        }
        ts.forEachChild(n, look);
      };
      look(st);
      edges.set(key, set);
      // export default function Foo → default 로도 찾을 수 있게
      if (ts.isFunctionDeclaration(st) && st.modifiers?.some((m) => m.kind === ts.SyntaxKind.DefaultKeyword)) {
        edges.set(`${file}#default`, new Set([key]));
      }
    }
  }
  return edges;
}

function loadScreens() {
  try {
    return JSON.parse(readFileSync(SCREENS_FILE, "utf8"));
  } catch {
    return [];
  }
}

/** 화면별로 묶은 글 전부 */
export function collect() {
  const files = DIRS.flatMap((d) => walk(path.join(SRC, d)));
  const edges = graphOf(files);
  // 화면마다 닿는 선언들
  const reach = new Map(); // key → Set(route)
  const direct = new Map(); // route → 화면 파일이 바로 부르는 선언들 (그 화면의 본문)
  const appFiles = files.filter((f) => f.startsWith(path.join(SRC, "app") + path.sep));
  for (const f of appFiles) {
    const route = routeOf(f);
    const tag = route ?? `(틀) ${rel(f)}`;
    // 개발 화면은 거의 모든 부품을 열어 보므로, 개발 화면 파일 안에서만 따라간다
    const devOnly = route === "/dev";
    const roots = [...edges.keys()].filter((k) => k.startsWith(`${f}#`));
    direct.set(tag, new Set([...roots, ...roots.flatMap((k) => [...(edges.get(k) ?? [])])]));
    const stack = [...roots];
    const seen = new Set();
    while (stack.length) {
      const k = stack.pop();
      if (seen.has(k)) continue;
      seen.add(k);
      if (!reach.has(k)) reach.set(k, new Set());
      reach.get(k).add(tag);
      for (const nxt of edges.get(k) ?? []) if (!devOnly || nxt.includes(`${path.sep}components${path.sep}dev${path.sep}`)) stack.push(nxt);
    }
  }
  const screens = loadScreens();
  const info = new Map(screens.map((s) => [s.route, s]));
  const groups = new Map();
  const groupOf = (id, make) => {
    if (!groups.has(id)) groups.set(id, { id, ...make(), items: [] });
    return groups.get(id);
  };
  for (const s of screens) groupOf(s.route, () => ({ type: "screen", route: s.route, name: s.name, desc: s.desc }));
  const FRAME = {
    "(틀) src/app/_layout.tsx": { name: "앱 틀 (모든 화면 바깥)", desc: "모든 화면을 감싸는 틀. 화면 이름표, 띠 같은 것." },
    "(틀) src/app/(tabs)/_layout.tsx": { name: "아래 탭", desc: "화면 아래 탭 이름 (홈, 이번 주, 매출, 설정)." },
  };
  for (const [r, v] of Object.entries(FRAME)) info.set(r, { route: r, ...v });

  const all = files.flatMap(stringsOf);
  for (const s of all) {
    const key = `${path.join(MOBILE, s.file)}#${s.func}`;
    const routes = [...(reach.get(key) ?? [])].sort();
    const main = routes.length === 1 && direct.get(routes[0])?.has(key);
    const item = { main: !!main, id: s.id, file: s.file, line: s.line, func: s.func, label: s.label, kind: s.kind, text: s.text, placeholders: s.placeholders };
    if (routes.length === 1) {
      const r = routes[0];
      const g = groupOf(r, () => ({ type: "screen", route: r, name: info.get(r)?.name ?? r, desc: info.get(r)?.desc ?? "" }));
      g.items.push(item);
    } else if (routes.length > 1) {
      const names = routes.map((r) => info.get(r)?.name ?? r);
      const g = groupOf(`shared:${s.file}#${s.func}`, () => ({
        type: "shared",
        name: `${path.basename(s.file)} › ${s.func}`,
        desc: `여러 화면이 같이 쓰는 글 (${routes.length}개 화면): ${names.slice(0, 6).join(", ")}${names.length > 6 ? " 외" : ""}`,
        routes,
      }));
      g.items.push(item);
    } else {
      const g = groupOf(`file:${s.file}`, () => ({ type: "unused", name: s.file, desc: "화면에서 쓰는 곳을 찾지 못한 글 (안 쓰는 코드이거나, 다른 방법으로 불러옴)" }));
      g.items.push(item);
    }
  }
  // 화면 안에서는 제목을 먼저, 나머지는 파일·줄 순서
  const order = (a, b) => (a.label === "제목") - (b.label === "제목") || 0;
  for (const g of groups.values()) {
    g.items.sort((a, b) => -order(a, b) || b.main - a.main || a.file.localeCompare(b.file) || a.line - b.line);
  }
  const typeRank = { screen: 0, shared: 1, unused: 2 };
  const screenRank = new Map(screens.map((s, i) => [s.route, i]));
  const list = [...groups.values()]
    .filter((g) => g.items.length || g.type === "screen")
    .sort((a, b) => typeRank[a.type] - typeRank[b.type] || (screenRank.get(a.route) ?? 999) - (screenRank.get(b.route) ?? 999) || a.name.localeCompare(b.name));
  return { groups: list, total: all.length };
}

// ---------- 수정 파일 ----------

export function loadEdits() {
  if (!existsSync(EDITS_FILE)) return {};
  try {
    return JSON.parse(readFileSync(EDITS_FILE, "utf8")).edits ?? {};
  } catch {
    return {};
  }
}

export function saveEdits(edits) {
  const clean = {};
  for (const [id, e] of Object.entries(edits)) {
    if (e && typeof e.edited === "string" && e.edited !== e.original) clean[id] = e;
  }
  const doc = {
    "설명": "도나 화면 글 고치기. 각 줄의 original 이 지금 코드의 글, edited 가 바꿀 글입니다. 개발자 대시보드(http://localhost:8000/dev-dashboard/#uitext) '화면 글' 탭에서 고치거나, 이 파일을 직접 고친 뒤 `npm run ui-text:apply` 로 코드에 넣습니다.",
    edits: clean,
  };
  writeFileSync(EDITS_FILE, JSON.stringify(doc, null, 2) + "\n");
  return clean;
}

/** edits.json 의 수정을 코드에 넣는다 */
export function apply() {
  const edits = loadEdits();
  const byFile = new Map();
  const files = DIRS.flatMap((d) => walk(path.join(SRC, d)));
  const index = new Map();
  for (const f of files) for (const s of stringsOf(f)) index.set(s.id, s);
  const applied = [];
  const failed = [];
  const remaining = { ...edits };
  for (const [id, e] of Object.entries(edits)) {
    const s = index.get(id);
    if (!s) {
      failed.push({ id, file: e.file, line: e.line, original: e.original, edited: e.edited, reason: "코드에서 원본 글을 찾지 못했어요 (코드가 바뀌었을 수 있어요)" });
      continue;
    }
    if (e.edited === s.text) {
      delete remaining[id];
      continue;
    }
    if (s.kind === "template") {
      const a = placeholders(s.text).join("\u0000");
      const b = placeholders(e.edited).join("\u0000");
      if (a !== b) {
        failed.push({ id, file: s.file, line: s.line, original: s.text, edited: e.edited, reason: `\${…} 자리는 그대로 두어야 해요: ${placeholders(s.text).join(" ")}` });
        continue;
      }
    }
    if (!byFile.has(s.file)) byFile.set(s.file, []);
    byFile.get(s.file).push({ s, e, id });
  }
  for (const [file, list] of byFile) {
    const abs = path.join(MOBILE, file);
    let text = readFileSync(abs, "utf8");
    list.sort((a, b) => b.s.start - a.s.start);
    for (const { s, e, id } of list) {
      if (text.slice(s.start, s.end) !== s.src) {
        failed.push({ id, file, line: s.line, original: s.text, edited: e.edited, reason: "파일이 바뀌는 중이라 넣지 못했어요. 다시 해 주세요" });
        continue;
      }
      text = text.slice(0, s.start) + encode(s, e.edited) + text.slice(s.end);
      applied.push({ file, line: s.line, func: s.func, from: s.text, to: e.edited });
      delete remaining[id];
    }
    writeFileSync(abs, text);
  }
  saveEdits(remaining);
  return { applied, failed };
}
