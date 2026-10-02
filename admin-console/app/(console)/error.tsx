"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <section className="panel status-page">
      <h1>This page could not load.</h1>
      <p role="alert">Please try again.</p>
      <button onClick={reset}>Try again</button>
    </section>
  );
}
