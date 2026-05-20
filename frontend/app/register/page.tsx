"use client";

// Public registration page (security remediation). Never auto-logs-in.
import Link from "next/link";
import { useState } from "react";

import { register } from "@/lib/auth";

export default function RegisterPage() {
  const [form, setForm] = useState({ username: "", email: "", full_name: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (form.password !== form.confirm) {
      setError("Parolele nu coincid.");
      return;
    }
    setBusy(true);
    try {
      await register(form.username.trim(), form.email.trim(), form.full_name.trim(), form.password);
      setOk("Înregistrarea a fost trimisă. Contul trebuie aprobat de administrator înainte de autentificare.");
    } catch (err) {
      setError((err as Error).message || "Înregistrare eșuată.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="public-landing">
      <div className="public-card public-form">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/AIVideo.png" alt="P1.AIVideo" className="public-logo public-logo-sm" />
        <h1 className="public-title">P1.AIVideo</h1>
        <p className="public-tagline">Register</p>
        {ok ? (
          <div data-testid="register-success">
            <p className="public-success">{ok}</p>
            <div className="public-links"><Link href="/login">Back to sign in</Link></div>
          </div>
        ) : (
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <label className="form-row"><span>Username</span>
              <input value={form.username} onChange={(e) => set("username", e.target.value)} disabled={busy} /></label>
            <label className="form-row"><span>Email</span>
              <input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} disabled={busy} /></label>
            <label className="form-row"><span>Full name</span>
              <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} disabled={busy} /></label>
            <label className="form-row"><span>Password</span>
              <input type="password" value={form.password} onChange={(e) => set("password", e.target.value)} disabled={busy} /></label>
            <label className="form-row"><span>Confirm password</span>
              <input type="password" value={form.confirm} onChange={(e) => set("confirm", e.target.value)} disabled={busy} /></label>
            <p className="muted" style={{ fontSize: 12 }}>
              Min 10 chars, with uppercase, lowercase, digit and a special character.
            </p>
            <button type="submit" className="btn btn-primary public-btn" disabled={busy}>
              {busy ? "Submitting…" : "Register"}
            </button>
            {error && <p data-testid="register-error" className="public-error">{error}</p>}
            <div className="public-links">
              <Link href="/login">Sign in</Link>
              <Link href="/">← Home</Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
