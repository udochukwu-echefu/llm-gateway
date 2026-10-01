"use client";
import { useEffect, useState } from "react";
export function Toasts() {
  const [message, setMessage] = useState("");
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    function saved() {
      setMessage("Changes saved.");
      clearTimeout(timer);
      timer = setTimeout(() => setMessage(""), 4000);
    }
    window.addEventListener("console-saved", saved);
    return () => {
      window.removeEventListener("console-saved", saved);
      clearTimeout(timer);
    };
  }, []);
  return message ? (
    <div role="status" className="toast">
      {message}
    </div>
  ) : null;
}
