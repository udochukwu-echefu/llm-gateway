"use client";
import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
  type KeyboardEvent,
} from "react";

const subscribeToPopover = () => () => {};
const hasPopover = () => typeof HTMLElement.prototype.showPopover === "function";

type OptionProps = { value?: string | number; disabled?: boolean; children?: ReactNode };
type SelectProps = {
  "aria-label": string;
  children: ReactNode;
  value?: string;
  defaultValue?: string;
  name?: string;
  disabled?: boolean;
  onValueChange?: (value: string) => void;
};

export function Select({
  children,
  value,
  defaultValue,
  name,
  disabled,
  onValueChange,
  "aria-label": label,
}: SelectProps) {
  const supportsPopover = useSyncExternalStore(subscribeToPopover, hasPopover, () => true);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const typeahead = useRef({ text: "", time: 0 });
  const options = Children.toArray(children).flatMap((child) => {
    if (!isValidElement<OptionProps>(child) || child.type !== "option") return [];
    const text = Children.toArray(child.props.children).join("");
    return [
      { value: String(child.props.value ?? text), label: text, disabled: !!child.props.disabled },
    ];
  });
  const initial = defaultValue ?? options[0]?.value ?? "";
  const [internal, setInternal] = useState(initial);
  const selected = value ?? internal;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const enabled = options.flatMap((option, index) => (option.disabled ? [] : [index]));

  useEffect(() => {
    if (open)
      menu.current?.querySelector('[data-active="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [open, active]);
  useEffect(() => {
    const form = trigger.current?.closest("form");
    const reset = () => setInternal(initial);
    form?.addEventListener("reset", reset);
    return () => form?.removeEventListener("reset", reset);
  }, [initial]);

  function openMenu(
    index = options.findIndex((option) => option.value === selected && !option.disabled),
  ) {
    setActive(index < 0 ? (enabled[0] ?? 0) : index);
    setOpen(true);
    menu.current?.showPopover?.();
  }
  function closeMenu(focus = true) {
    menu.current?.hidePopover?.();
    setOpen(false);
    typeahead.current.text = "";
    if (focus) trigger.current?.focus();
  }
  function choose(index: number, focus = true) {
    const option = options[index];
    if (!option || option.disabled) return;
    if (value === undefined) setInternal(option.value);
    onValueChange?.(option.value);
    closeMenu(focus);
  }
  function search(character: string, now: number) {
    const previous = now - typeahead.current.time < 700 ? typeahead.current.text : "";
    const repeated = previous.split("").every((letter) => letter === character);
    const text = repeated ? character : previous + character;
    typeahead.current = { text, time: now };
    const start = open ? active : options.findIndex((option) => option.value === selected);
    const candidates = [
      ...enabled.filter((index) => index > start),
      ...enabled.filter((index) => index <= start),
    ];
    const found = candidates.find((index) =>
      options[index].label.toLocaleLowerCase().startsWith(text),
    );
    if (found !== undefined) {
      if (open) setActive(found);
      else openMenu(found);
    }
  }
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (["ArrowDown", "ArrowUp", "Home", "End", "PageDown", "PageUp"].includes(event.key)) {
      event.preventDefault();
      if (!open) {
        openMenu(
          event.key === "End"
            ? enabled.at(-1)
            : event.key === "Home" || event.key === "ArrowUp"
              ? enabled[0]
              : undefined,
        );
        return;
      }
      const step = event.key.startsWith("Page") ? 10 : 1;
      const next =
        enabled.indexOf(active) + (["ArrowUp", "PageUp"].includes(event.key) ? -step : step);
      const index =
        event.key === "Home"
          ? enabled[0]
          : event.key === "End"
            ? enabled.at(-1)
            : enabled[Math.max(0, Math.min(enabled.length - 1, next))];
      if (index !== undefined) setActive(index);
    } else if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      if (open) choose(active);
      else openMenu();
    } else if (open && event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    } else if (open && event.key === "Tab") {
      choose(active, false);
    } else if (event.key.length === 1) {
      event.preventDefault();
      search(event.key.toLocaleLowerCase(), event.timeStamp);
    }
  }
  return (
    <span className="select-root">
      {name !== undefined && (
        <input type="hidden" name={name} value={selected} disabled={disabled} />
      )}
      <button
        ref={trigger}
        type="button"
        className="secondary select-trigger"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={id}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        data-value={selected}
        disabled={disabled}
        popoverTarget={id}
        onKeyDown={onKeyDown}
        onClick={() => {
          if (!open) {
            const index = options.findIndex(
              (option) => option.value === selected && !option.disabled,
            );
            setActive(index < 0 ? (enabled[0] ?? 0) : index);
          }
          if (!menu.current?.showPopover) {
            if (open) closeMenu();
            else openMenu();
          }
        }}
      >
        <span className="select-value">
          {options.find((option) => option.value === selected)?.label ?? selected}
        </span>
        <span className="select-chevron" aria-hidden="true" />
      </button>
      <div
        ref={menu}
        id={id}
        role="listbox"
        aria-label={label}
        aria-hidden={!open}
        popover={supportsPopover ? "auto" : undefined}
        className="select-menu"
        data-open={open}
        onBeforeToggle={(event) => setOpen(event.newState === "open")}
        onToggle={(event) => setOpen(event.newState === "open")}
      >
        {options.map((option, index) => (
          <div
            key={option.value}
            id={`${id}-${index}`}
            role="option"
            aria-selected={selected === option.value}
            aria-disabled={option.disabled || undefined}
            className="select-option"
            data-value={option.value}
            data-active={active === index}
            onPointerMove={() => !option.disabled && setActive(index)}
            onPointerDown={(event) => event.preventDefault()}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              choose(index);
            }}
          >
            <span>{option.label}</span>
            {selected === option.value && <span className="select-check" aria-hidden="true" />}
          </div>
        ))}
      </div>
    </span>
  );
}
