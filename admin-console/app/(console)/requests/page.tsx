import { Suspense } from "react";
import { Requests } from "@/components/requests";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Requests />
    </Suspense>
  );
}
