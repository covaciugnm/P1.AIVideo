"use client";

// Login page (security remediation). Public route — no internal shell.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, setSession } from "@/lib/auth";

// Map the backend's English status messages to the requested Romanian copy.
function roStatusMessage(msg: string): string {
  const m = msg.toLowerCase();
  if (m.includes("pending")) return "Contul este în așteptarea aprobării administratorului.";
  if (m.includes("suspended")) return "Contul este suspendat. Contactați administratorul.";
  if (m.includes("rejected")) return "Contul a fost respins.";
  if (m.includes("unavailable")) return "Cont indisponibil.";
  if (m.includes("invalid")) return "Utilizator sau parolă incorecte.";
  return msg;
}

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
      setError(roStatusMessage((err as Error).message || "Autentificare eșuată."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="public-landing">
      <form onSubmit={submit} className="public-card public-form">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/AIVideo.png" alt="P1.AIVideo" className="public-logo public-logo-sm" />
        <h1 className="public-title">P1.AIVideo</h1>
        <p className="public-tagline">Sign in</p>
        <label className="form-row">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus disabled={busy} />
        </label>
        <label className="form-row">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} />
        </label>
        <button type="submit" className="btn btn-primary public-btn" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p data-testid="login-error" className="public-error">{error}</p>}
        <div className="public-links">
          <Link href="/register">Register</Link>
          <Link href="/">← Home</Link>
        </div>
      </form>
    </div>
  );
}
