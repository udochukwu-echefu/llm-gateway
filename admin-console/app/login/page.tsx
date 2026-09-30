import { LoginForm } from "@/components/login-form";
export default function LoginPage() {
  return (
    <main className="login">
      <div className="login-card">
        <p className="eyebrow">GATEWAY / ADMIN CONSOLE</p>
        <h1>Welcome back.</h1>
        <p className="muted">One place to manage your gateway.</p>
        <LoginForm />
        <p className="login-footnote">Private access · Encrypted session · Audited changes</p>
      </div>
    </main>
  );
}
