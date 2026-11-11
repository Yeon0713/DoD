import { Suspense } from "react";
import { HoursConfirmScreen } from "@/components/start/HoursScreens";

export default function Page() {
  return (
    <Suspense>
      <HoursConfirmScreen mode="settings" />
    </Suspense>
  );
}
