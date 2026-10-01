import { LoginForm } from "@/components/login-form";
import { DemoSignIn } from "@/components/demo-sign-in";
import { readConfig } from "@/lib/config";
export default function LoginPage() {
  const config = readConfig();
  return (
    <main className="login">
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
    </main>
  );
}
