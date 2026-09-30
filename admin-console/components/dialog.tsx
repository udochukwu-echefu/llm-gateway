"use client";
import { useEffect, useRef, type ReactNode } from "react";
export function Dialog({ title, onClose, children }: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    dialog.showModal();
    dialog.querySelector<HTMLElement>("button, input, select, a[href], [tabindex=\"0\"]")?.focus();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  function containFocus(event: React.KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab")
      return;
    const items = Array.from(ref.current!.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex=\"0\"]"));
    const first = items[0];
    const last = items.at(-1);
    if (!first || !last) {
      event.preventDefault();
      ref.current!.focus();
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  return <dialog ref={ref} tabIndex={-1} onKeyDown={containFocus} aria-labelledby="dialog-title" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <h2 id="dialog-title">{title}</h2>{children}
  </dialog>;
}
