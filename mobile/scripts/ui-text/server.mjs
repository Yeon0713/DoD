// 화면 글 고치기 페이지를 띄운다: `npm run ui-text` → http://localhost:8090
// 페이지에서 [수정] 칸에 적으면 edits.json 에 저장되고, "코드에 넣기"를 누르면 코드의 글이 바뀐다.
// 다시 열면 바뀐 코드에서 글을 새로 뽑으므로 원본이 수정본으로 바뀌어 보인다.
import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { apply, collect, EDITS_FILE, loadEdits, MOBILE, saveEdits } from "./core.mjs";

const PORT = Number(process.env.PORT ?? 8090);
const PAGE = path.join(import.meta.dirname, "page.html");

function send(res, code, body, type = "application/json; charset=utf-8") {
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch (e) {
        reject(e);
      }
    });
  });
}

function typecheck() {
  return new Promise((resolve) => {
    execFile("npx", ["tsc", "--noEmit"], { cwd: MOBILE, timeout: 120000 }, (err, stdout, stderr) => {
      const out = `${stdout}${stderr}`.split("\n").filter((l) => l.trim() && !l.includes("trust settings")).join("\n");
      resolve({ ok: !err, output: out.slice(0, 4000) });
    });
  });
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (req.method === "GET" && url.pathname === "/") return send(res, 200, readFileSync(PAGE, "utf8"), "text/html; charset=utf-8");
    if (req.method === "GET" && url.pathname === "/api/data") {
      const { groups, total } = collect();
      const edits = loadEdits();
      const ids = new Set(groups.flatMap((g) => g.items.map((i) => i.id)));
      const stale = Object.entries(edits)
        .filter(([id]) => !ids.has(id))
        .map(([id, e]) => ({ id, ...e }));
      return send(res, 200, { groups, total, edits, stale, editsFile: path.relative(MOBILE, EDITS_FILE) });
    }
    if (req.method === "POST" && url.pathname === "/api/save") {
      const { edits } = await readBody(req);
      const saved = saveEdits(edits ?? {});
      return send(res, 200, { ok: true, count: Object.keys(saved).length, at: new Date().toISOString() });
    }
    if (req.method === "POST" && url.pathname === "/api/apply") {
      const { edits } = await readBody(req);
      if (edits) saveEdits(edits);
      const result = apply();
      const check = result.applied.length ? await typecheck() : { ok: true, output: "" };
      return send(res, 200, { ...result, check });
    }
    send(res, 404, { error: "없는 주소예요" });
  } catch (e) {
    send(res, 500, { error: String(e?.stack ?? e) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`화면 글 고치기: http://localhost:${PORT}`);
  console.log(`수정 파일: ${EDITS_FILE}`);
});
