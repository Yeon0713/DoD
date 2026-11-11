import { Suspense } from "react";
import { BusySettingsScreen } from "@/components/settings/SettingsScreens";

export default function Page() {
  return (
    <Suspense>
      <BusySettingsScreen />
    </Suspense>
  );
}
