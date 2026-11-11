// 그 날 메뉴판을 어떤 순서로 바꿀지 (Figma 04-53 바꿀 순서, 05-12n 카드 미리 보기).
// 서버 GET /api/menu-order/{plan_id}가 생기기 전까지 업종별 예시 메뉴(mocks/extras storeMenus)와 달력으로 정한다.
import { storeMenus } from "@/mocks/extras";
import type { CalendarCell, PlanItem } from "@/types/contract";
import { dayChange } from "./calendarDay";

export function menuOrderFor(plan: PlanItem, cells: CalendarCell[], category: string) {
  const change = dayChange(cells, plan.target_date);
  const menus = storeMenus(category);
  const tag = change?.on ? change.tag : null;
  const order = tag ? [...menus.filter((m) => m.tags.includes(tag)), ...menus.filter((m) => !m.tags.includes(tag))] : menus;
  const top = order[0];
  return { change, tag, menus, order, top, from: menus.indexOf(top) + 1 };
}
