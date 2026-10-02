"use client";
import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
} from "react";
import { DateRangePicker } from "./date-range-picker";
import { dateKey, rangeFromValues } from "./date-range-dates";
import {
  utcTimestampHint,
  utcTimestampPattern,
  validUtcTimestamp,
  wholeDayTimes,
} from "./date-range-timestamps";

interface DateField {
  name: string;
  label: string;
  value: string;
}
const subscribeToPopover = () => () => {};
const hasPopover = () => typeof HTMLElement.prototype.showPopover === "function";

export function DateRangeFields({
  start,
  end,
  withTime,
}: {
  start: DateField;
  end: DateField;
  withTime: boolean;
}) {
  const id = useId();
  const supportsPopover = useSyncExternalStore(subscribeToPopover, hasPopover, () => true);
  const [values, setValues] = useState({ start: start.value, end: end.value });
  const [open, setOpen] = useState(false);
  const [today, setToday] = useState("");
  const picker = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement | HTMLInputElement>(null);
  const fields = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || supportsPopover) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !fields.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open, supportsPopover]);

  function openCalendar(element: HTMLButtonElement | HTMLInputElement) {
    trigger.current = element;
    setToday(dateKey(new Date()));
    setOpen(true);
    picker.current?.showPopover?.();
  }
  function closeCalendar() {
    picker.current?.hidePopover?.();
    setOpen(false);
    trigger.current?.focus();
  }
  function onInputKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.altKey && event.key === "ArrowDown") {
      event.preventDefault();
      openCalendar(event.currentTarget);
    }
  }
  return (
    <div className="date-range-fields" ref={fields}>
      {([start, end] as const).map((field, index) => {
        const side = index === 0 ? "start" : "end";
        return (
          <label key={field.name}>
            {field.label}
            <span className="calendar-input-frame">
              <input
                aria-label={field.label}
                name={field.name}
                type={withTime ? "text" : "date"}
                placeholder={withTime ? "YYYY-MM-DDTHH:mm" : undefined}
                pattern={withTime ? utcTimestampPattern : undefined}
                title={withTime ? utcTimestampHint : undefined}
                value={values[side]}
                onChange={(event) => {
                  const value = event.target.value;
                  event.target.setCustomValidity(
                    withTime && value && !validUtcTimestamp(value) ? utcTimestampHint : "",
                  );
                  setValues({ ...values, [side]: value });
                }}
                onKeyDown={onInputKey}
              />
              <button
                type="button"
                className="calendar-trigger"
                aria-label={`Open ${side} date calendar`}
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={id}
                onClick={(event) => openCalendar(event.currentTarget)}
              >
                <span className="calendar-icon" aria-hidden="true" />
              </button>
            </span>
          </label>
        );
      })}
      <div
        id={id}
        ref={picker}
        className="date-range-popover"
        popover={supportsPopover ? "auto" : undefined}
        role="dialog"
        aria-label="Date range"
        aria-hidden={!open}
        data-open={open}
        onToggle={(event) => setOpen(event.newState === "open")}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            closeCalendar();
          }
        }}
      >
        {open && (
          <DateRangePicker
            initialRange={rangeFromValues(values.start, values.end)}
            today={today}
            times={{
              start: values.start.slice(11) || wholeDayTimes.start,
              end: values.end.slice(11) || wholeDayTimes.end,
            }}
            withTime={withTime}
            onApply={(range, times) => {
              setValues({
                start: range.start + (withTime ? `T${times.start}` : ""),
                end: range.end + (withTime ? `T${times.end}` : ""),
              });
              fields.current
                ?.querySelectorAll("input")
                .forEach((input) => input.setCustomValidity(""));
              closeCalendar();
            }}
            onClear={() => {
              setValues({ start: "", end: "" });
              fields.current
                ?.querySelectorAll("input")
                .forEach((input) => input.setCustomValidity(""));
              closeCalendar();
            }}
            onCancel={closeCalendar}
          />
        )}
      </div>
    </div>
  );
}
