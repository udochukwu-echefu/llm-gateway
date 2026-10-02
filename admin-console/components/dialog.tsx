"use client";
import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { revealSheet, sheetDuration } from "./sheet-motion";
const CloseContext = createContext<() => void>(() => {});
export function SheetCloseButton() {
  const close = useContext(CloseContext);
  return (
    <button className="secondary" onClick={close}>
      Close
    </button>
  );
}
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
  const reveal = useRef<Animation | null>(null);
  const backdropAnimation = useRef<Animation | null>(null);
  const closing = useRef(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    if (drawer) dialog.classList.add("sheet-reveal");
    dialog.showModal();
    if (
      drawer &&
      typeof dialog.animate === "function" &&
      !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      reveal.current = revealSheet(dialog);
      backdropAnimation.current =
        dialog
          .getAnimations?.()
          .find((animation) => (animation as CSSAnimation).animationName === "sheet-backdrop") ??
        null;
    }
    dialog
      .querySelector<HTMLElement>(
        'button, input:not([type="hidden"]), select, a[href], [tabindex="0"]',
      )
      ?.focus();
    return () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);
      reveal.current?.cancel();
      backdropAnimation.current?.cancel();
      dialog.close();
      previous?.focus();
    };
  }, [drawer]);
  function requestClose() {
    if (closing.current) return;
    if (
      !drawer ||
      !reveal.current ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      onClose();
      return;
    }
    closing.current = true;
    ref.current?.classList.add("sheet-closing");
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (closeTimer.current) clearTimeout(closeTimer.current);
      closeTimer.current = null;
      onClose();
    };
    if (backdropAnimation.current) {
      backdropAnimation.current.currentTime = reveal.current.currentTime;
      backdropAnimation.current.reverse();
    }
    reveal.current.reverse();
    void reveal.current.finished.then(finish).catch(() => {});
    closeTimer.current = setTimeout(finish, sheetDuration + 150);
  }
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
    <CloseContext.Provider value={requestClose}>
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
          if (dismissOnBackdrop && backdropPress.current && outside(event)) requestClose();
          backdropPress.current = false;
        }}
        aria-labelledby="dialog-title"
        onCancel={(event) => {
          event.preventDefault();
          requestClose();
        }}
      >
        {drawer ? (
          <header className="sheet-heading">
            <h2 id="dialog-title">{title}</h2>
            <button
              className="sheet-close"
              type="button"
              aria-label="Close sheet"
              onClick={requestClose}
            >
              <span className="sheet-close-icon" aria-hidden="true" />
            </button>
          </header>
        ) : (
          <h2 id="dialog-title">{title}</h2>
        )}
        {drawer ? (
          <>
            <div className="sheet-grid" aria-hidden="true" />
            <div className="sheet-body">{children}</div>
            <div className="sheet-shine" aria-hidden="true" />
          </>
        ) : (
          children
        )}
      </dialog>
    </CloseContext.Provider>
  );
}
