// 알림 권한을 묻는다 (웹). 앱은 askNotify.native.ts. expo-notifications는 웹 번들에서 풀리지 않아 따로 둔다.
export async function askNotify(): Promise<boolean> {
  try {
    const N = (globalThis as { Notification?: { requestPermission: () => Promise<string> } }).Notification;
    return N ? (await N.requestPermission()) === "granted" : false;
  } catch {
    // 알림을 물어볼 수 없는 브라우저
    return false;
  }
}
