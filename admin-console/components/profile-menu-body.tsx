"use client";
import Link from "next/link";
import { useLayoutEffect, useRef } from "react";
import { ProfileIcon, type ProfileIconName } from "./profile-icon";
import { usePreferences } from "./preferences";
import { useProfileHighlight } from "./use-profile-highlight";
import type { DemoAvailability, DemoProfile } from "./profile-identity";

interface Props {
  open: boolean;
  demo: DemoAvailability;
  current: DemoProfile | null;
  pending: DemoProfile | "logout" | null;
  onSelect: (profile: DemoProfile | "logout") => void;
  close: () => void;
}
export function ProfileMenuBody({ open, demo, current, pending, onSelect, close }: Props) {
  const preferences = usePreferences();
  const { highlight, moveTo } = useProfileHighlight(open);
  const first = useRef<HTMLAnchorElement>(null);
  useLayoutEffect(() => {
    if (open && first.current) moveTo(first.current);
  }, [open, moveTo]);
  return (
    <div
      className="profile-body"
      onPointerOver={(event) => {
        const row = (event.target as Element).closest<HTMLElement>(".profile-row, .profile-tile");
        if (row && !row.matches(":disabled")) moveTo(row);
      }}
      onFocus={(event) => moveTo(event.target)}
    >
      <div className="profile-highlight" aria-hidden="true" ref={highlight} />
      <section aria-label="Navigation" className="profile-section">
        <h2>Navigation</h2>
        {(
          [
            ["View profile", "/settings", "user"],
            ["Requests", "/requests", "requests"],
            ["Analytics", "/analytics", "analytics"],
          ] as const
        ).map(([label, href, icon], index) => (
          <Link
            key={href}
            ref={index === 0 ? first : undefined}
            className="profile-row"
            href={href}
            prefetch={false}
            aria-disabled={!!pending}
            tabIndex={pending ? -1 : undefined}
            onClick={(event) => {
              if (pending) event.preventDefault();
              else close();
            }}
          >
            <ProfileIcon name={icon} />
            {label}
          </Link>
        ))}
        <button
          type="button"
          className="profile-row"
          disabled={!!pending}
          onClick={() => onSelect("logout")}
        >
          <ProfileIcon name="logout" />
          Sign out
          {pending === "logout" && <span className="profile-row-end">Signing out…</span>}
        </button>
      </section>
      {demo.enabled && (
        <section aria-label="Demo profiles" className="profile-section">
          <h2>Demo profiles</h2>
          <ProfileChoice
            profile="platform"
            title="Platform viewer"
            context="All organisations · Read-only"
            icon="platform"
            current={current}
            pending={pending}
            onSelect={onSelect}
          />
          {demo.org && (
            <ProfileChoice
              profile="org"
              title="Northwind Health viewer"
              context="Northwind Health · Read-only"
              icon="org"
              current={current}
              pending={pending}
              onSelect={onSelect}
            />
          )}
        </section>
      )}
      <section aria-label="Appearance" className="profile-section">
        <h2>Appearance</h2>
        <div className="profile-appearance">
          {(["light", "dark", "system"] as const).map((theme) => (
            <button
              key={theme}
              type="button"
              className="profile-tile"
              aria-pressed={preferences.value.theme === theme}
              disabled={!preferences.ready || !!pending}
              onClick={() => preferences.update({ theme })}
            >
              <ProfileIcon name={theme} />
              {theme[0].toUpperCase() + theme.slice(1)}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function ProfileChoice({
  profile,
  title,
  context,
  icon,
  current,
  pending,
  onSelect,
}: {
  profile: DemoProfile;
  title: string;
  context: string;
  icon: ProfileIconName;
  current: Props["current"];
  pending: Props["pending"];
  onSelect: Props["onSelect"];
}) {
  return (
    <button
      type="button"
      className="profile-row profile-choice"
      aria-pressed={profile === current}
      disabled={!!pending}
      onClick={() => onSelect(profile)}
    >
      <ProfileIcon name={icon} />
      <span className="profile-row-label">
        <span>{title}</span>
        <small>{context}</small>
      </span>
      <span className="profile-row-end">
        {profile === current ? (
          <>
            <ProfileIcon name="check" />
            <span className="sr-only">Current profile</span>
          </>
        ) : pending === profile ? (
          "Switching…"
        ) : null}
      </span>
    </button>
  );
}
