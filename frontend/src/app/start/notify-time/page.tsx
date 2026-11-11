import { Suspense } from "react";
import { NotifyTimeScreen } from "@/components/start/HoursScreens";

export default function Page() {
  return (
    <Suspense>
      <NotifyTimeScreen />
    </Suspense>
  );
}
