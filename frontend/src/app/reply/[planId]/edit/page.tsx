import { Suspense } from "react";
import { EditReplyScreen } from "@/components/reply/ReplyScreens";

export default function Page() {
  return (
    <Suspense>
      <EditReplyScreen />
    </Suspense>
  );
}
