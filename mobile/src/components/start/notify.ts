// 06-3b 알림 켜기 (웹). 브라우저 허락만 받는다. 앱은 notify.native.ts가 매일 알림 3개를 예약한다.
import type { Slot } from "@/types/contract";

/** 알림 허락을 받는다. 허락했는지 돌려준다. */
export async function turnOnNotifications(_slots: Record<Slot, string>, _extra: string[] = []): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  return (await Notification.requestPermission()) === "granted";
}

/** 웹은 예약 알림이 없다. */
export async function rescheduleIfAllowed(_slots: Record<Slot, string>, _extra: string[] = []) {}
