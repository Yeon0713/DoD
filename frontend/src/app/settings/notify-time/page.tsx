import { Suspense } from "react";
import { NotifyTimeSettingsScreen } from "@/components/settings/SettingsScreens";

export default function Page() {
  return (
    <Suspense>
      <NotifyTimeSettingsScreen />
    </Suspense>
  );
}
