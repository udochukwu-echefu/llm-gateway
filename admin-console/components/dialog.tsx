"use client";
import { useEffect, useRef, type ReactNode } from "react";
export function Dialog({
  title,
  onClose,
  children,
  drawer = false,
  dismissOnBackdrop = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  drawer?: boolean;
  dismissOnBackdrop?: boolean;
}) {
  const backdropPress = useRef(false);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    if (drawer && !previous?.matches(":focus-visible")) dialog.classList.add("sheet-reveal");
    dialog.showModal();
    dialog
      .querySelector<HTMLElement>(
        'button, input:not([type="hidden"]), select, a[href], [tabindex="0"]',
      )
      ?.focus();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, [drawer]);
  function outside(
    event: React.MouseEvent<HTMLDialogElement> | React.PointerEvent<HTMLDialogElement>,
  ) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return (
      event.target === event.currentTarget &&
      (event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom)
    );
  }
  function containFocus(event: React.KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;
    const items = Array.from(
      ref.current!.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), a[href], [tabindex="0"]',
      ),
    );
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
  return (
    <dialog
      className={drawer ? "detail-drawer" : undefined}
      ref={ref}
      tabIndex={-1}
      onKeyDown={containFocus}
      onPointerDown={(event) => {
        backdropPress.current = dismissOnBackdrop && outside(event);
      }}
      onPointerCancel={() => {
        backdropPress.current = false;
      }}
      onClick={(event) => {
        if (dismissOnBackdrop && backdropPress.current && outside(event)) onClose();
        backdropPress.current = false;
      }}
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {drawer ? (
        <div className="sheet-heading">
          <h2 id="dialog-title">{title}</h2>
          <button
            className="secondary sheet-close"
            type="button"
            aria-label="Close sheet"
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
      ) : (
        <h2 id="dialog-title">{title}</h2>
      )}
      {children}
    </dialog>
  );
}
