"use client";
import { useState } from "react";
export function CopyId({ value }: { value: string }) {
  const [notice, setNotice] = useState("");
  return (
    <span className="copy-id">
      <code>{value}</code>{" "}
      <button
        className="secondary"
        aria-label={`Copy ${value}`}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setNotice("Copied");
          } catch {
            setNotice("Copy unavailable. Select the ID to copy.");
          }
        }}
      >
        {notice || "Copy"}
      </button>
    </span>
  );
}
