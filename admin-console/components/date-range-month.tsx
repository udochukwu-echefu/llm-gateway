import { useId, type KeyboardEvent } from "react";
import {
  addCalendarDays,
  calendarDate,
  formatCalendarDate,
  type CalendarRange,
} from "./date-range-dates";

export function DateRangeMonth({
  month,
  range,
  today,
  tabbable,
  onPick,
  onHover,
  onKey,
}: {
  month: string;
  range: CalendarRange | null;
  today: string;
  tabbable: string;
  onPick: (date: string) => void;
  onHover: (date: string) => void;
  onKey: (event: KeyboardEvent<HTMLButtonElement>, date: string) => void;
}) {
  const id = useId();
  const offset = calendarDate(month).getUTCDay();
  const rows = Array.from({ length: 6 }, (_, row) =>
    Array.from({ length: 7 }, (_, col) => {
      const day = row * 7 + col - offset + 1;
      const date = new Date(calendarDate(month));
      date.setUTCDate(day);
      return date.getUTCFullYear() >= 1 && date.getUTCFullYear() <= 9999
        ? addCalendarDays(month, day - 1)
        : "";
    }),
  );
  const inMonth = (date: string) => date.slice(0, 7) === month.slice(0, 7);
  const inRange = (date: string) =>
    !!(range && inMonth(date) && date >= range.start && date <= range.end);
  return (
    <div className="calendar-month">
      <p id={id} className="calendar-month-title">
        {formatCalendarDate(month, { month: "long", year: "numeric" })}
      </p>
      <div role="grid" aria-labelledby={id}>
        <div role="row" className="calendar-weekdays">
          {["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].map(
            (day) => (
              <span role="columnheader" aria-label={day} key={day}>
                {day.slice(0, 2)}
              </span>
            ),
          )}
        </div>
        {rows.map((row, rowIndex) => (
          <div role="row" className="calendar-week" key={rowIndex}>
            {row.map((date, col) => {
              if (!date || !inMonth(date))
                return <span role="gridcell" className="calendar-cell" key={col} />;
              const selected = inRange(date);
              const start = range?.start === date;
              const end = range?.end === date;
              const current = date === today;
              return (
                <span
                  role="gridcell"
                  aria-selected={selected}
                  className="calendar-cell"
                  data-range={selected || undefined}
                  data-segment-start={
                    (selected && (col === 0 || !inRange(row[col - 1]))) || undefined
                  }
                  data-segment-end={
                    (selected && (col === 6 || !inRange(row[col + 1]))) || undefined
                  }
                  key={date}
                >
                  <button
                    type="button"
                    className="calendar-day"
                    data-date={date}
                    data-edge={start || end || undefined}
                    data-range={selected || undefined}
                    aria-label={formatCalendarDate(date, {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    })}
                    aria-current={current ? "date" : undefined}
                    tabIndex={date === tabbable ? 0 : -1}
                    onClick={() => onPick(date)}
                    onPointerEnter={() => onHover(date)}
                    onKeyDown={(event) => onKey(event, date)}
                  >
                    <span>{calendarDate(date).getUTCDate()}</span>
                    {current && <span className="calendar-today-dot" aria-hidden="true" />}
                  </button>
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
