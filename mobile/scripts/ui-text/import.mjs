// 밖에서 고친 화면 글 JSON 의 "수정"을 edits.json 에 더한다: `npm run ui-text:import -- <파일>`
// 코드에 넣기는 따로: 대시보드 '화면 글' 탭의 [코드에 넣기] 또는 `npm run ui-text:apply`
import { readFileSync } from "node:fs";
import path from "node:path";
import { EDITS_FILE, importDoc } from "./core.mjs";

const file = process.argv[2];
if (!file) {
  console.error("올릴 JSON 파일을 적어 주세요: npm run ui-text:import -- <파일>");
  process.exit(1);
}
const doc = JSON.parse(readFileSync(path.resolve(process.env.INIT_CWD ?? process.cwd(), file), "utf8"));
const { asked, loaded, skipped, editsCount } = importDoc(doc);
for (const l of loaded) console.log(`담음  ${l.file}:${l.line}\n  - ${JSON.stringify(l.original)}\n  + ${JSON.stringify(l.edited)}`);
for (const s of skipped) console.log(`못 담음  ${s.where} ${JSON.stringify(s.original)}\n  까닭: ${s.reason}`);
console.log(`\n고친 글 ${asked}개 중 ${loaded.length}개를 ${EDITS_FILE} 에 담았어요 (담긴 수정 모두 ${editsCount}개).`);
if (loaded.length) console.log("코드에 넣기: 대시보드 '화면 글' 탭 [코드에 넣기] 또는 npm run ui-text:apply");
process.exitCode = skipped.length ? 1 : 0;
