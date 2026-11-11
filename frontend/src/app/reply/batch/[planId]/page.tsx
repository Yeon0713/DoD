import { Suspense } from "react";
import { BatchReplyScreen } from "@/components/reply/ReplyScreens";

export default function Page() {
  return (
    <Suspense>
      <BatchReplyScreen />
    </Suspense>
  );
}
