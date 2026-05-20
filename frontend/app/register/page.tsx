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
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await register(form.username.trim(), form.email.trim(), form.full_name.trim(), form.password);
      setOk(res.message);
    } catch (err) {
      setError((err as Error).message || "Registration failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: "6vh auto", padding: 16 }}>
      <h1>Register</h1>
      {ok ? (
        <div data-testid="register-success" style={{ marginTop: 12 }}>
          <p style={{ color: "var(--accent, #54d39a)" }}>{ok}</p>
          <p style={{ marginTop: 12 }}><Link href="/login">Back to sign in</Link></p>
        </div>
      ) : (
        <>
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
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Submitting…" : "Register"}
            </button>
          </form>
          {error && <p data-testid="register-error" style={{ color: "var(--danger)", marginTop: 10 }}>{error}</p>}
          <p style={{ marginTop: 16, fontSize: 13 }}>
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
        </>
      )}
    </div>
  );
}
