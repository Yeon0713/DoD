"""알림 묶음 안 충돌 찾기 (규칙, LLM 없음).

일꾼 에이전트는 각자 자기 일만 보므로, 각자 검사를 통과해도 아래 같은 어긋남이 생긴다.
메뉴 id, 불만 종류, 손님 키만 대조해서 찾는다. 충돌이 없는 묶음은 supervisor 를 부르지 않는다.

  PROMOTES_COMPLAINED_MENU  음식 불만(맛·양·위생·사진과 다름)이 열려 있는 메뉴를 메뉴판·포스터가 추천한다
  REPLY_VS_DIAGNOSIS        반복 불만 진단이 나왔는데, 같은 불만 리뷰의 답글이 같은 묶음에 있다 (서로 맞는지 supervisor 가 본다)
  SAME_CUSTOMER_TWICE       같은 손님에게 답글과 재주문 인사가 같은 묶음으로 간다

열린 위험 신호: 마지막 리뷰(last_at)가 지금 기준 7일 안인 것 (risk_signals.py 의 '열려 있음'과 같은 기준).
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

from app.planner.data_shapes import NotificationBatch, PlanItem, RiskSignal
from app.planner.rule_complaint_fix import COMPLAINT_NAMES
from Harness.spec import Proposal, RunContext

ConflictKind = Literal["PROMOTES_COMPLAINED_MENU", "REPLY_VS_DIAGNOSIS", "SAME_CUSTOMER_TWICE"]
KIND_NAMES = {
    "PROMOTES_COMPLAINED_MENU": "불만 메뉴를 홍보",
    "REPLY_VS_DIAGNOSIS": "원인 진단과 같은 불만 답글",
    "SAME_CUSTOMER_TWICE": "같은 손님에게 두 번",
}
FOOD_COMPLAINTS = {"TASTE", "PORTION", "HYGIENE", "PHOTO_MISMATCH"}
OPEN_WINDOW = dt.timedelta(days=7)


@dataclass
class Conflict:
    kind: ConflictKind
    plan_ids: list[str]  # 충돌에 걸린 묶음 안 할 일들
    detail: dict
    rule_notes: dict[str, str] = field(default_factory=dict)  # supervisor 를 못 쓸 때 카드에 붙일 규칙 메모 {plan_id: 메모}

    def describe(self) -> str:
        return f"{KIND_NAMES[self.kind]}: {', '.join(self.plan_ids)} ({'; '.join(f'{k}={v}' for k, v in self.detail.items())})"


def plan_ids_of(batch: NotificationBatch | list[str]) -> list[str]:
    ids = [entry.plan_id for entry in batch.entries if entry.plan_id] if isinstance(batch, NotificationBatch) else list(batch)
    return list(dict.fromkeys(ids))


def open_risks(ctx: RunContext) -> list[RiskSignal]:
    return [r for r in ctx.snapshot.risk_signals if r.status == "OPEN" and r.last_at > ctx.now - OPEN_WINDOW and r.detected_at <= ctx.now]


def _items(ctx: RunContext, plan_ids: list[str]) -> list[PlanItem]:
    plan = ctx.snapshot.plan
    by_id = {item.plan_id: item for item in plan.plan_items} if plan else {}
    return [by_id[pid] for pid in plan_ids if pid in by_id]


def _complained_menus(ctx: RunContext) -> dict[str, RiskSignal]:
    """음식 불만이 열려 있는 메뉴 id → 그 위험 신호. 메뉴는 불만 리뷰가 달린 주문의 메뉴다."""
    reviews = {r.review_id: r for r in ctx.snapshot.reviews}
    items_by_order: dict[str, set[str]] = {}
    for item in ctx.snapshot.inputs.order_items:
        items_by_order.setdefault(item.order_id, set()).add(item.menu_id)
    menus: dict[str, RiskSignal] = {}
    for risk in open_risks(ctx):
        if risk.complaint_type not in FOOD_COMPLAINTS:
            continue
        for review_id in risk.review_ids:
            review = reviews.get(review_id)
            for menu_id in items_by_order.get(review.order_id, ()) if review and review.order_id else ():
                menus.setdefault(menu_id, risk)
    return menus


def find_conflicts(batch: NotificationBatch | list[str], proposals: dict[str, Proposal], ctx: RunContext) -> list[Conflict]:
    plan_ids = plan_ids_of(batch)
    items = _items(ctx, plan_ids)
    reviews = {r.review_id: r for r in ctx.snapshot.reviews}
    names = {m.menu_id: m.name for m in ctx.snapshot.inputs.menus}
    conflicts: list[Conflict] = []

    # 1. 불만 메뉴를 홍보
    complained = _complained_menus(ctx)
    for item in items:
        proposal = proposals.get(item.plan_id)
        if item.task_type not in ("MENU_ORDER", "POSTER") or proposal is None:
            continue
        menu_names = {m.get("menu") for m in proposal.content.get("ments") or [] if isinstance(m, dict)}
        hit = [m for m in proposal.content.get("menu_ids") or [] if m in complained]
        hit += [m for m, name in names.items() if name in menu_names and m in complained and m not in hit]
        if hit:
            risk = complained[hit[0]]
            complaint = COMPLAINT_NAMES[risk.complaint_type]
            menus = [names.get(m, m) for m in hit]
            conflicts.append(Conflict(
                "PROMOTES_COMPLAINED_MENU", [item.plan_id],
                {"menu_ids": hit, "menus": menus, "risk_id": risk.risk_id, "complaint": complaint},
                {item.plan_id: f"{', '.join(menus)}에 {complaint} 불만이 열려 있어요. 홍보 메뉴를 확인해 주세요"},
            ))

    # 2. 원인 진단과 같은 불만 답글
    risks = {r.risk_id: r for r in ctx.snapshot.risk_signals}
    for fix in (i for i in items if i.task_type == "REVIEW_FIX"):
        proposal = proposals.get(fix.plan_id)
        risk = risks.get(fix.basis.ref_id)
        if proposal is None or risk is None or not proposal.content.get("hypotheses"):
            continue
        replies = [
            i.plan_id for i in items
            if i.task_type == "REVISIT_REPLY" and i.plan_id in proposals
            and (review := reviews.get(i.basis.ref_id)) is not None and review.label is not None
            and risk.complaint_type in review.label.complaint_types
        ]
        if replies:
            complaint = COMPLAINT_NAMES[risk.complaint_type]
            conflicts.append(Conflict(
                "REPLY_VS_DIAGNOSIS", [fix.plan_id, *replies],
                {"risk_id": risk.risk_id, "complaint": complaint, "diagnosis": proposal.content["hypotheses"][0]["text"]},
                {pid: f"같은 {complaint} 불만 점검 카드와 함께 보고, 답글의 개선 약속이 맞는지 확인해 주세요" for pid in replies},
            ))

    # 3. 같은 손님에게 두 번
    reply_customers = {
        review.customer_key: i.plan_id for i in items
        if i.task_type == "REVISIT_REPLY" and (review := reviews.get(i.basis.ref_id)) is not None and review.customer_key
    }
    for nudge in (i for i in items if i.task_type == "REORDER_NUDGE"):
        reply_id = reply_customers.get(nudge.basis.ref_id)
        if reply_id and reply_id in proposals and nudge.plan_id in proposals:
            conflicts.append(Conflict(
                "SAME_CUSTOMER_TWICE", [reply_id, nudge.plan_id], {"reply": reply_id, "nudge": nudge.plan_id},
                {nudge.plan_id: "같은 손님에게 답글도 함께 가요. 두 글이 겹치지 않는지 확인해 주세요"},
            ))
    return conflicts
