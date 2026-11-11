import { Suspense } from "react";
import { NotifyOnScreen } from "@/components/start/StartScreens";

export default function Page() {
  return (
    <Suspense>
      <NotifyOnScreen />
    </Suspense>
  );
}
