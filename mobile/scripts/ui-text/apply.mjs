// edits.json 의 [수정] 글을 코드에 넣는다 (개발자 대시보드 없이): `npm run ui-text:apply`
import { apply, EDITS_FILE } from "./core.mjs";

const { applied, failed } = apply();
for (const a of applied) console.log(`바꿈  ${a.file}:${a.line}\n  - ${JSON.stringify(a.from)}\n  + ${JSON.stringify(a.to)}`);
for (const f of failed) console.log(`못 바꿈  ${f.file ?? ""}:${f.line ?? ""} ${JSON.stringify(f.original)}\n  까닭: ${f.reason}`);
console.log(`\n바꾼 글 ${applied.length}개, 못 바꾼 글 ${failed.length}개. 남은 수정은 ${EDITS_FILE} 에 있어요.`);
if (applied.length) console.log("확인: npx tsc --noEmit");
process.exitCode = failed.length ? 1 : 0;
