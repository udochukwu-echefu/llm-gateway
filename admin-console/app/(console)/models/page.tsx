import { Suspense } from "react";
import { Models } from "@/components/models";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Models />
    </Suspense>
  );
}
