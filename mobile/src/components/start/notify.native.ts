// 06-3b 알림 켜기 (앱). 고른 시각 3개에 매일 알림을 예약한다. 웹은 notify.ts (expo-notifications가 웹에서 묶이지 않아 나눴다).
// 실제 알림 내용은 서버 푸시가 생기면 그쪽으로 옮긴다. 지금은 "할 일을 챙겨 뒀어요" 한 줄.
import * as Notifications from "expo-notifications";
import type { Slot } from "@/types/contract";

const SLOTS: Slot[] = ["OPENING", "AFTERNOON", "CLOSING"];

async function schedule(slots: Record<Slot, string>, extra: string[] = []) {
  // 예전에 예약한 알림을 먼저 지운다.
  await Notifications.cancelAllScheduledNotificationsAsync();
  const times = [...SLOTS.map((slot) => ({ time: slots[slot], body: "오늘 할 일을 챙겨 뒀어요" })), ...extra.map((time) => ({ time, body: "남은 할 일이 있는지 확인해 보세요" }))];
  for (const t of times) {
    const [hour, minute] = t.time.split(":").map(Number);
    await Notifications.scheduleNotificationAsync({
      content: { title: "도나", body: t.body },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour, minute },
    });
  }
}

/** 알림 허락을 받고, 받으면 매일 알림 3개를 예약한다. 허락했는지 돌려준다. */
export async function turnOnNotifications(slots: Record<Slot, string>, extra: string[] = []): Promise<boolean> {
  try {
    const { granted } = await Notifications.requestPermissionsAsync();
    if (!granted) return false;
    await schedule(slots, extra).catch(() => undefined);
    return true;
  } catch {
    return false;
  }
}

/** 설정에서 알림 시각을 바꾸면, 이미 허락받은 경우에만 예약을 다시 한다(허락 창은 띄우지 않는다). */
export async function rescheduleIfAllowed(slots: Record<Slot, string>, extra: string[] = []) {
  try {
    const { granted } = await Notifications.getPermissionsAsync();
    if (granted) await schedule(slots, extra);
  } catch {
    /* 알림 예약이 안 돼도 저장은 된 것이다 */
  }
}
