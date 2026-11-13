// 밖에서 고치는 화면 글 JSON 을 만든다 (모든 원본 + 빈 "수정" 칸): `npm run ui-text:export -- [저장할 파일]`
// 파일을 안 적으면 ui-text-<날짜>.json 으로 지금 폴더에 만든다.
import { writeFileSync } from "node:fs";
import path from "node:path";
import { exportDoc } from "./core.mjs";

const doc = exportDoc();
const out = path.resolve(process.env.INIT_CWD ?? process.cwd(), process.argv[2] ?? `ui-text-${doc["뽑은 날"]}.json`);
writeFileSync(out, JSON.stringify(doc, null, 2) + "\n");
console.log(`${out}\n글 ${doc["글 수"]}개, 묶음 ${doc.화면.length}개. "수정" 칸을 채운 뒤 npm run ui-text:import -- <파일> 또는 대시보드 [JSON 등록]으로 올리세요.`);
