import { LoginForm } from "@/components/login-form";
import { DemoSignIn } from "@/components/demo-sign-in";
import { readConfig } from "@/lib/config";
export default function LoginPage() {
  const config = readConfig();
  return (
    <main className="login">
      <section className="login-story" aria-label="About LLM Gateway">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          LLM Gateway<span className="brand-sub">Admin console</span>
        </div>
        <div>
          <h2>
            One gateway.
            <br />
            Clear oversight.
          </h2>
          <p>
            Understand every request. Control access, review spending, and manage your model
            providers in one place.
          </p>
          <div
            className="gateway-diagram"
            aria-label="Applications connect through the gateway to model providers"
          >
            <div className="gateway-node">
              Applications<small>Teams &amp; keys</small>
            </div>
            <div className="gateway-node gateway-node-center">
              Gateway<small>Access · Routing · Limits</small>
            </div>
            <div className="gateway-node">
              Providers<small>Models &amp; usage</small>
            </div>
          </div>
        </div>
        <span className="login-story-note">Request metadata, never conversations.</span>
      </section>
      <div className="login-access">
        <div className="login-card">
          <p className="eyebrow">GATEWAY / ADMIN CONSOLE</p>
          <h1>{config.DEMO_MODE ? "Explore the gateway." : "Welcome back."}</h1>
          <p className="muted">
            {config.DEMO_MODE
              ? "A live, read-only console with synthetic data. No account needed."
              : "One place to manage your gateway."}
          </p>
          {config.DEMO_MODE && <DemoSignIn org={!!config.DEMO_ORG_VIEWER_KEY} />}
          {(!config.DEMO_MODE || config.DEMO_ALLOW_KEY_SIGN_IN) && <LoginForm />}
          <p className="login-footnote">
            {config.DEMO_MODE
              ? "Synthetic data · No real provider spend · No visitor trackers"
              : "Private access · Encrypted session · Audited changes"}
          </p>
        </div>
      </div>
    </main>
  );
}
