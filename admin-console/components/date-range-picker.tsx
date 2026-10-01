"use client";
// DevClub Date Range Picker, adapted to local CSS and UTC calendar dates.
// License: public/licenses/devclub-components.txt.
import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import {
  addCalendarDays,
  addCalendarMonths,
  calendarDate,
  calendarDayCount,
  calendarPresets,
  formatCalendarRange,
  monthStart,
  orderCalendarRange,
  shiftCalendarMonth,
  type CalendarRange,
} from "./date-range-dates";
import { DateRangeMonth } from "./date-range-month";

function subscribeToScreen(notify: () => void) {
  const media = window.matchMedia("(max-width: 767px)");
  media.addEventListener("change", notify);
  return () => media.removeEventListener("change", notify);
}
const readSmallScreen = () => window.matchMedia("(max-width: 767px)").matches;

export function DateRangePicker({
  initialRange,
  today,
  times,
  withTime,
  onApply,
  onClear,
  onCancel,
}: {
  initialRange: CalendarRange | null;
  today: string;
  times: { start: string; end: string };
  withTime: boolean;
  onApply: (range: CalendarRange, times: { start: string; end: string }) => void;
  onClear: () => void;
  onCancel: () => void;
}) {
  const compact = useSyncExternalStore(subscribeToScreen, readSmallScreen, () => false);
  const count = compact ? 1 : 2;
  const [selectedView, setView] = useState<string>();
  const view = calendarView(
    selectedView ?? initialRange?.end ?? today,
    selectedView || compact ? 0 : -1,
    count,
  );
  const [direction, setDirection] = useState(1);
  const [draft, setDraft] = useState(initialRange);
  const [anchor, setAnchor] = useState<string>();
  const [hover, setHover] = useState<string>();
  const [time, setTime] = useState(times);
  const [focusDay, setFocusDay] = useState(initialRange?.start ?? today);
  const root = useRef<HTMLDivElement>(null);
  const focusRequested = useRef(false);
  const shown = anchor ? orderCalendarRange(anchor, hover ?? anchor) : draft;
  const months = Array.from({ length: count }, (_, index) => addCalendarMonths(view, index));
  const presets = calendarPresets(today);
  const active =
    !anchor && draft
      ? presets.findIndex(({ range }) => range.start === draft.start && range.end === draft.end)
      : -1;
  const tabbable = months.some((month) => month.slice(0, 7) === focusDay.slice(0, 7))
    ? focusDay
    : view;
  const summary = shown ? formatCalendarRange(shown) : "Select dates";
  const days = shown ? calendarDayCount(shown) : 0;

  useEffect(() => {
    if (focusRequested.current) {
      root.current?.querySelector<HTMLButtonElement>(`[data-date="${focusDay}"]`)?.focus();
      focusRequested.current = false;
    }
  }, [focusDay, view]);
  useEffect(() => {
    root.current?.querySelector<HTMLButtonElement>('.calendar-day[tabindex="0"]')?.focus();
  }, []);

  function goTo(month: string) {
    setDirection(month >= view ? 1 : -1);
    setView(calendarView(month, 0, count));
  }
  function pick(date: string) {
    setFocusDay(date);
    if (!anchor) {
      setAnchor(date);
      setHover(date);
    } else {
      setDraft(orderCalendarRange(anchor, date));
      setAnchor(undefined);
      setHover(undefined);
    }
  }
  function choosePreset(range: CalendarRange) {
    setDraft(range);
    setAnchor(undefined);
    setHover(undefined);
    setFocusDay(range.start);
    goTo(addCalendarMonths(range.end, compact ? 0 : -1));
  }
  function onDayKey(event: KeyboardEvent<HTMLButtonElement>, date: string) {
    const weekday = calendarDate(date).getUTCDay();
    const moves: Record<string, () => string> = {
      ArrowLeft: () => addCalendarDays(date, -1),
      ArrowRight: () => addCalendarDays(date, 1),
      ArrowUp: () => addCalendarDays(date, -7),
      ArrowDown: () => addCalendarDays(date, 7),
      Home: () => addCalendarDays(date, -weekday),
      End: () => addCalendarDays(date, 6 - weekday),
      PageUp: () => shiftCalendarMonth(date, event.shiftKey ? -12 : -1),
      PageDown: () => shiftCalendarMonth(date, event.shiftKey ? 12 : 1),
    };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    const next = move();
    setFocusDay(next);
    focusRequested.current = true;
    if (anchor) setHover(next);
    if (monthStart(next) < view) goTo(monthStart(next));
    else if (monthStart(next) > months[count - 1]) goTo(addCalendarMonths(next, -(count - 1)));
  }
  return (
    <div
      ref={root}
      className="calendar-picker"
      onKeyDown={(event) => {
        if (event.key === "Enter" && event.target instanceof HTMLInputElement)
          event.preventDefault();
      }}
    >
      <div className="calendar-body">
        <div
          className="calendar-presets"
          role="group"
          aria-label="Date presets"
          data-active-preset={active}
        >
          {presets.map(({ label, range }, index) => (
            <button
              type="button"
              className="calendar-preset"
              aria-pressed={index === active}
              key={label}
              onClick={() => choosePreset(range)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="calendar-months-frame" onPointerLeave={() => anchor && setHover(undefined)}>
          <button
            type="button"
            className="calendar-nav calendar-previous"
            aria-label="Previous month"
            disabled={view === "0001-01-01"}
            onClick={() => goTo(addCalendarMonths(view, -1))}
          >
            <span className="calendar-chevron" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="calendar-nav calendar-next"
            aria-label="Next month"
            disabled={months[count - 1] === "9999-12-01"}
            onClick={() => goTo(addCalendarMonths(view, 1))}
          >
            <span className="calendar-chevron" aria-hidden="true" />
          </button>
          <div className="calendar-months" data-direction={direction} key={`${view}-${count}`}>
            {months.map((month) => (
              <DateRangeMonth
                month={month}
                range={shown}
                today={today}
                tabbable={tabbable}
                onPick={pick}
                onHover={(date) => anchor && setHover(date)}
                onKey={onDayKey}
                key={month}
              />
            ))}
          </div>
        </div>
      </div>
      {withTime && (
        <div className="calendar-times">
          <label>
            Start time (UTC)
            <input
              aria-label="Start time (UTC)"
              type="time"
              value={time.start}
              onChange={(event) => setTime({ ...time, start: event.target.value })}
            />
          </label>
          <label>
            End time (UTC)
            <input
              aria-label="End time (UTC)"
              type="time"
              value={time.end}
              onChange={(event) => setTime({ ...time, end: event.target.value })}
            />
          </label>
        </div>
      )}
      <div className="calendar-footer">
        <div className="calendar-summary">
          <span className="calendar-summary-icon" aria-hidden="true">
            <span className="calendar-icon" />
          </span>
          <div>
            <span className="calendar-range-label" key={summary}>
              {summary}
            </span>
            {shown && (
              <span className="calendar-count">
                {anchor && hover === anchor
                  ? "Pick an end date"
                  : `${days} ${days === 1 ? "day" : "days"}`}
              </span>
            )}
          </div>
        </div>
        <div className="calendar-footer-actions">
          <button type="button" className="calendar-cancel" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="calendar-apply"
            disabled={!shown || (withTime && (!time.start || !time.end))}
            onClick={() => {
              const range = anchor ? { start: anchor, end: anchor } : draft;
              if (range) onApply(range, time);
            }}
          >
            Apply
          </button>
        </div>
      </div>
      <div className="calendar-clear-row">
        <button type="button" className="calendar-clear" onClick={onClear}>
          Clear dates
        </button>
      </div>
      <p className="calendar-status" role="status">
        {anchor
          ? `Start ${anchor}. Choose an end date.`
          : shown
            ? `${summary}, ${days} ${days === 1 ? "day" : "days"}`
            : "Choose a start and end date."}
      </p>
    </div>
  );
}

function calendarView(date: string, offset: number, count: number): string {
  const month = addCalendarMonths(date, offset);
  return count === 2 && month === "9999-12-01" ? "9999-11-01" : month;
}
