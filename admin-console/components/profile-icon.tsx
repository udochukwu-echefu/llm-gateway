// DevClub profile-menu icon geometry. License: public/licenses/devclub-components.txt.
const paths = {
  user: "M6 20v-1a6 6 0 0 1 12 0v1 M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  requests: "M5 3h14v18H5z M9 8h6 M9 12h6 M9 16h4",
  analytics: "M4 4v16h16 M8 16v-4 M12 16V8 M16 16V6",
  logout: "M9 4H4v16h5 M10 12h10 M16 8l4 4-4 4",
  platform: "M3 5h18v14H3z M7 9h3 M14 9h3 M7 15h3 M14 15h3",
  org: "M4 21V7h10v14 M14 11h6v10 M8 3h2v4 M7 11h4 M7 15h4 M8 21v-3h2v3",
  light:
    "M12 3v1 M12 20v1 M3 12h1 M20 12h1 M5.6 5.6l.7.7 M17.7 17.7l.7.7 M5.6 18.4l.7-.7 M17.7 6.3l.7-.7 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  dark: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8",
  system: "M3 4h18v13H3z M12 17v4 M8 21h8",
  chevron: "m6 9 6 6 6-6",
  check: "m5 12 4 4L19 6",
};
export type ProfileIconName = keyof typeof paths;
export function ProfileIcon({ name }: { name: ProfileIconName }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
