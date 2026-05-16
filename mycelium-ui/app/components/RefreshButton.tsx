"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export default function RefreshButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <button
      onClick={() => startTransition(() => router.refresh())}
      disabled={isPending}
      className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50 transition-colors cursor-pointer"
    >
      {isPending ? "Refreshing…" : "Refresh"}
    </button>
  );
}
