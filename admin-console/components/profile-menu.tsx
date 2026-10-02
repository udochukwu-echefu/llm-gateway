"use client";
import { useId, useRef, useState } from "react";
import type { Identity } from "@/lib/contracts";
import { ProfileIcon } from "./profile-icon";
import { ProfileMenuBody } from "./profile-menu-body";
import { useProfileDisclosure } from "./use-profile-disclosure";
import { useProfilePlacement } from "./use-profile-placement";
import { usePolicyNavigation } from "./unsaved-policy";
import { navigateProfileDocument, signOutProfile, switchDemoProfile } from "./profile-session";
import {
  noDemoProfiles,
  profileIdentity,
  type DemoAvailability,
  type DemoProfile,
} from "./profile-identity";

export function ProfileMenu({
  identity,
  demo = noDemoProfiles,
}: {
  identity: Identity;
  demo?: DemoAvailability;
}) {
  const {
    root: rootRef,
    trigger: triggerRef,
    close,
    open,
    toggle,
    preview,
    leave: leavePreview,
    pin,
  } = useProfileDisclosure();
  useProfilePlacement(rootRef, open);
  const leave = usePolicyNavigation();
  const profile = profileIdentity(identity, demo);
  const id = useId();
  const locked = useRef(false);
  const [pending, setPending] = useState<DemoProfile | "logout" | null>(null);
  const [error, setError] = useState("");
  async function select(action: DemoProfile | "logout") {
    if (locked.current || action === profile.current || !leave()) return;
    locked.current = true;
    setPending(action);
    setError("");
    try {
      if (action === "logout") await signOutProfile();
      else await switchDemoProfile(action);
      close();
      navigateProfileDocument(action === "logout" ? "/login" : "/overview");
    } catch (failure) {
      setError(
        failure instanceof Error
          ? `${failure.message} Your current session is unchanged; please try again.`
          : "The request failed. Your current session is unchanged; please try again.",
      );
      setPending(null);
      locked.current = false;
    }
  }
  return (
    <div
      className="profile-slot"
      ref={rootRef}
      onPointerEnter={(event) => preview(event.pointerType)}
      onPointerLeave={leavePreview}
      onFocusCapture={(event) => {
        if (!event.target.closest(".profile-trigger")) pin();
      }}
      onBlur={(event) => {
        // Disabling the focused choice must not hide pending or failure feedback.
        if (!locked.current && !event.currentTarget.contains(event.relatedTarget)) close();
      }}
    >
      <div className="profile-card" data-open={open}>
        <button
          ref={triggerRef}
          type="button"
          className="profile-trigger"
          aria-label={`Profile menu: ${profile.title}`}
          aria-expanded={open}
          aria-controls={id}
          title={profile.title}
          onClick={toggle}
        >
          <span className="profile-avatar" aria-hidden="true">
            {profile.initials}
            <span className="profile-online" />
          </span>
          <span className="profile-heading">
            <span className="profile-title" title={profile.title}>
              {profile.title}
            </span>
            <span className="profile-context">{profile.context}</span>
          </span>
          <span className="profile-chevron">
            <ProfileIcon name="chevron" />
          </span>
        </button>
        <div className="profile-reveal" id={id} inert={!open} aria-hidden={!open}>
          <div className="profile-reveal-inner">
            <div
              className="profile-scroll"
              role="region"
              aria-label="Profile actions"
              aria-busy={!!pending}
            >
              <ProfileMenuBody
                open={open}
                demo={demo}
                current={profile.current}
                pending={pending}
                onSelect={(action) => void select(action)}
                close={close}
              />
              {pending && (
                <p className="sr-only" role="status">
                  {pending === "logout"
                    ? "Signing out…"
                    : `Switching to ${pending === "platform" ? "Platform viewer" : "Northwind Health viewer"}…`}
                </p>
              )}
              {error && (
                <p className="profile-error" role="alert">
                  {error}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
