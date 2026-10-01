"use client";
import { useState, type ReactNode } from "react";
import { PolicyConfirmation } from "./policy-confirmation";
import { useReadOnly, ReadOnlyNotice, READ_ONLY_REASON } from "./read-only";
export function PolicyEditorFrame({
  title,
  level,
  explanation,
  changes,
  error,
  conflict,
  needsReload,
  busy,
  notice,
  reload,
  save,
  danger,
  valid = true,
  children,
}: {
  title: string;
  level: string;
  explanation: string;
  changes: string[];
  error: string;
  conflict: boolean;
  needsReload: boolean;
  busy: boolean;
  notice: string;
  reload: () => Promise<void>;
  save: (clear: boolean) => Promise<void>;
  danger?: string;
  valid?: boolean;
  children: ReactNode;
}) {
  const readOnly = useReadOnly();
  const [confirmation, setConfirmation] = useState<{ clear: boolean; consequence: string }>();
  function submit(clear: boolean) {
    if (readOnly) return;
    const consequence = clear
      ? `Remove the override for ${level}? Inherited restrictions and built-in defaults still apply.`
      : danger;
    if (consequence) setConfirmation({ clear, consequence });
    else void save(false);
  }
  return (
    <section className="panel policy-editor" aria-label={title}>
      <div className="section-heading">
        <h2>{title}</h2>
        <span className="badge">
          {readOnly ? "Viewing" : "Editing"} {level}
        </span>
      </div>
      <p className="muted">{explanation}</p>
      {conflict && (
        <div role="alert" className="conflict">
          <p>Someone else changed this policy. Reload to see their version</p>
          <button className="secondary" disabled={busy} onClick={() => void reload()}>
            Reload policy
          </button>
        </div>
      )}
      {needsReload && (
        <p role="alert">
          Policy saved, but its updated view could not be loaded. Reload before editing again.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <ReadOnlyNotice />
      <fieldset disabled={busy || readOnly}>
        <legend className="sr-only">{title} settings</legend>
        {children}
      </fieldset>
      {changes.length > 0 && (
        <div className="policy-changes">
          <h3>Changes</h3>
          <ul>
            {changes.map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="actions">
        {(changes.length > 0 || readOnly) && (
          <button
            disabled={busy || conflict || needsReload || !valid || readOnly}
            title={readOnly ? READ_ONLY_REASON : undefined}
            onClick={() => submit(false)}
          >
            Save {title.toLowerCase()}
          </button>
        )}
        <button
          className="secondary"
          disabled={busy || conflict || needsReload || readOnly}
          title={readOnly ? READ_ONLY_REASON : undefined}
          onClick={() => submit(true)}
        >
          Remove override
        </button>
        <button className="secondary" disabled={busy} onClick={() => void reload()}>
          Reload {title.toLowerCase()}
        </button>
      </div>
      {confirmation && (
        <PolicyConfirmation
          {...confirmation}
          level={level}
          busy={busy}
          onClose={() => setConfirmation(undefined)}
          onConfirm={async () => {
            const clear = confirmation.clear;
            setConfirmation(undefined);
            await save(clear);
          }}
        />
      )}
    </section>
  );
}
