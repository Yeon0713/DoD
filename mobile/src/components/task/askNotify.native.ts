// 알림 권한을 묻는다 (앱).
import * as Notifications from "expo-notifications";

export async function askNotify(): Promise<boolean> {
  try {
    const r = await Notifications.requestPermissionsAsync();
    return r.granted;
  } catch {
    return false;
  }
}
