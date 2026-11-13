// 화면 글 고치기를 서버(개발자 대시보드 "화면 글" 탭)가 부르는 입구. 결과는 JSON 한 덩어리로 stdout 에 쓴다.
//   node scripts/ui-text/cli.mjs data            화면별 글, 저장해 둔 수정, 원본을 못 찾은 수정
//   node scripts/ui-text/cli.mjs save  < {edits}   edits.json 에 저장
//   node scripts/ui-text/cli.mjs apply < {edits}   저장하고 코드에 넣은 뒤 타입 검사(tsc)
//   node scripts/ui-text/cli.mjs export            밖에서 고치는 JSON (모든 원본 + 빈 수정 칸)
//   node scripts/ui-text/cli.mjs import < {doc}     밖에서 고친 JSON 의 수정을 edits.json 에 더하기
// 서버: server/app/modules/dev_tools/ui_text.py → /api/dev_tools/ui_text
import { execFile } from "node:child_process";
import path from "node:path";
import { apply, collect, EDITS_FILE, exportDoc, importDoc, loadEdits, MOBILE, saveEdits } from "./core.mjs";

async function readStdin() {
  let data = "";
  for await (const chunk of process.stdin) data += chunk;
  return data.trim() ? JSON.parse(data) : {};
}

function typecheck() {
  return new Promise((resolve) => {
    execFile("npx", ["tsc", "--noEmit"], { cwd: MOBILE, timeout: 120000 }, (err, stdout, stderr) => {
      const out = `${stdout}${stderr}`.split("\n").filter((l) => l.trim() && !l.includes("trust settings")).join("\n");
      resolve({ ok: !err, output: out.slice(0, 4000) });
    });
  });
}

function data() {
  const { groups, total } = collect();
  const edits = loadEdits();
  const ids = new Set(groups.flatMap((g) => g.items.map((i) => i.id)));
  const stale = Object.entries(edits)
    .filter(([id]) => !ids.has(id))
    .map(([id, e]) => ({ id, ...e }));
  return { groups, total, edits, stale, editsFile: path.relative(path.dirname(MOBILE), EDITS_FILE) };
}

const command = process.argv[2];
try {
  let result;
  if (command === "data") result = data();
  else if (command === "save") {
    const saved = saveEdits((await readStdin()).edits ?? {});
    result = { ok: true, count: Object.keys(saved).length, at: new Date().toISOString() };
  } else if (command === "apply") {
    const { edits } = await readStdin();
    if (edits) saveEdits(edits);
    const done = apply();
    result = { ...done, check: done.applied.length ? await typecheck() : { ok: true, output: "" } };
  } else if (command === "export") {
    result = exportDoc();
  } else if (command === "import") {
    result = importDoc((await readStdin()).doc);
  } else {
    throw new Error(`모르는 명령이에요: ${command ?? "(없음)"} (data, save, apply, export, import)`);
  }
  process.stdout.write(JSON.stringify(result));
} catch (e) {
  process.stderr.write(String(e?.stack ?? e));
  process.exitCode = 1;
}
