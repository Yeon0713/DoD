// 사장님 확인 (가입 흐름: 이 가게가 맞나요? → 사장님 확인 → 심사 → 가게 정보 확인).
// 서버(server/app/modules/owner_check)가 목업 국세청으로 심사하고, 승인되면 계정과 가게를 잇는다.
// 앱 안 목업 모드(EXPO_PUBLIC_USE_MOCK)에서는 서버 없이 여기서 흉내 낸다: 모양이 맞으면 3초 뒤 승인.
import { api, USE_MOCK, type OwnerCheckInput, type OwnerCheckResult } from "./api";
import { createStore } from "./store";

/** 신청한 심사 (심사 화면이 다시 열려도 이어 보게). again: 설정 "우리 가게 다시 찾기"에서 왔는지 */
export const ownerCheck = createStore<{ checkId: string | null; storeId: string | null; again: boolean }>("dona.ownerCheck.v1", { checkId: null, storeId: null, again: false });

const WEIGHTS = [1, 3, 7, 1, 3, 7, 1, 3, 5];

/** 사업자등록번호 10자리 + 마지막 검증 숫자 (국세청 규칙). 잘못 쓴 번호를 보내기 전에 알려 준다 */
export function isBusinessNo(digits: string): boolean {
  if (!/^\d{10}$/.test(digits)) return false;
  const d = [...digits].map(Number);
  const total = WEIGHTS.reduce((sum, w, i) => sum + d[i] * w, 0) + Math.floor((d[8] * 5) / 10);
  return (10 - (total % 10)) % 10 === d[9];
}

/** 000-00-00000 */
export function formatBusinessNo(digits: string): string {
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}

/** 20210401 → 2021.04.01 (쓰는 동안) */
export function formatDate(digits: string): string {
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}.${digits.slice(4)}`;
  return `${digits.slice(0, 4)}.${digits.slice(4, 6)}.${digits.slice(6)}`;
}

/** 20210401 → 2021-04-01. 없는 날짜면 null */
export function isoDate(digits: string): string | null {
  if (!/^\d{8}$/.test(digits)) return null;
  const iso = `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
  const d = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso ? iso : null;
}

// 앱 안 목업: 신청 시각을 기억해 두고 3초 뒤 승인
const MOCK_SECONDS = 3;
let mockSubmittedAt = 0;

export async function submitOwnerCheck(storeId: string, ownerKey: string, input: OwnerCheckInput): Promise<OwnerCheckResult> {
  if (USE_MOCK) {
    mockSubmittedAt = Date.now();
    return mockResult(storeId);
  }
  return api.ownerCheckSubmit({ ...input, store_id: storeId, owner_key: ownerKey });
}

export async function readOwnerCheck(checkId: string, storeId: string): Promise<OwnerCheckResult> {
  if (USE_MOCK) return mockResult(storeId);
  return api.ownerCheckResult(checkId);
}

/** 시험용 값 (데모 테스트 모드). 서버의 목업 국세청 자료에서 그 가게로 통과하는 값 */
export async function ownerCheckSample(storeId: string): Promise<OwnerCheckInput | null> {
  if (USE_MOCK) return { business_no: "1208103450", owner_name: "김도나", opened_on: "2021-04-01", document: "사업자등록증_시험용.jpg" };
  try {
    const s = await api.ownerCheckSample(storeId);
    return { business_no: s.business_no, owner_name: s.owner_name, opened_on: s.opened_on, document: s.document };
  } catch {
    return null;
  }
}

function mockResult(storeId: string): OwnerCheckResult {
  const left = Math.max(0, MOCK_SECONDS - (Date.now() - mockSubmittedAt) / 1000);
  return { check_id: "mock", store_id: storeId, status: left > 0 ? "reviewing" : "approved", reason_code: null, reason_title: null, reason_sub: null, business_no: "", seconds_left: left };
}
