"use client";

// Login page (public). No internal shell. Independent local state; the app
// never persists the password (no localStorage/sessionStorage/global state).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { login, setSession } from "@/lib/auth";
import * as logBus from "@/lib/log-bus";

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
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Defensive: never carry credentials across mounts/navigation. Clear on
  // mount and on unmount (the password must not survive a refresh in app state).
  useEffect(() => {
    setUsername("");
    setPassword("");
    return () => setPassword("");
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // Only the username (an identifier) is logged — never the password.
    logBus.emit({ source: "frontend", level: "info", message: "login submitted", meta: { username: username.trim() } });
    try {
      const res = await login(username.trim(), password);
      setPassword(""); // drop it immediately after use
      setSession(res.access_token, res.user);
      logBus.emit({ source: "frontend", level: "success", message: "login success", meta: { username: username.trim() } });
      router.push("/characters");
    } catch (err) {
      const msg = (err as Error).message || "Autentificare eșuată.";
      setError(roStatusMessage(msg));
      logBus.emit({ source: "frontend", level: "error", message: "login failed", meta: { username: username.trim(), error: msg } });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="public-landing">
      <form onSubmit={submit} className="public-card public-form" autoComplete="off">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/AIVideo.png" alt="P1.AIVideo" className="public-logo public-logo-sm" />
        <h1 className="public-title">P1.AIVideo</h1>
        <p className="public-tagline">Autentificare</p>

        <div className="auth-form">
          <div className="auth-field">
            <label className="auth-label" htmlFor="login-username">Utilizator</label>
            <input
              id="login-username"
              name="login-username"
              className="auth-input"
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              autoFocus
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="login-password">Parolă</label>
            <div style={{ position: "relative" }}>
              <input
                id="login-password"
                name="login-password"
                className="auth-input"
                type={showPass ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                style={{ paddingRight: 44, width: "100%" }}
              />
              <button
                type="button"
                onClick={() => setShowPass((v) => !v)}
                aria-label={showPass ? "Ascunde parola" : "Arată parola"}
                title={showPass ? "Ascunde parola" : "Arată parola"}
                style={{
                  position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)",
                  background: "none", border: "none", cursor: "pointer", fontSize: 16, padding: 4,
                  lineHeight: 1,
                }}
              >
                {showPass ? "🙈" : "👁️"}
              </button>
            </div>
          </div>

          <button type="submit" className="auth-button" disabled={busy || !username || !password}>
            {busy ? "Se autentifică…" : "Autentificare"}
          </button>
        </div>

        {error && <p data-testid="login-error" className="public-error">{error}</p>}
        <div className="public-links">
          <Link href="/register">Înregistrare</Link>
          <Link href="/">← Acasă</Link>
        </div>
      </form>
    </div>
  );
}
