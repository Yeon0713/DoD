import { Suspense } from "react";
import { WeekDetailScreen } from "@/components/week/WeekScreens";

export default function Page() {
  return (
    <Suspense>
      <WeekDetailScreen />
    </Suspense>
  );
}
