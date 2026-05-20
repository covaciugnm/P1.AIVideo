"use client";

// Login page (security remediation). Public route.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, setSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(username.trim(), password);
      setSession(res.access_token, res.user);
      router.push("/characters");
    } catch (err) {
      // Backend returns status-specific messages (pending/suspended/rejected).
      setError((err as Error).message || "Login failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 380, margin: "8vh auto", padding: 16 }}>
      <h1>Sign in</h1>
      <p className="muted" style={{ fontSize: 13 }}>P1.AIVideo</p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label className="form-row">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus disabled={busy} />
        </label>
        <label className="form-row">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      {error && (
        <p data-testid="login-error" style={{ color: "var(--danger)", marginTop: 10 }}>{error}</p>
      )}
      <p style={{ marginTop: 16, fontSize: 13 }}>
        No account? <Link href="/register">Register</Link>
      </p>
    </div>
  );
}
