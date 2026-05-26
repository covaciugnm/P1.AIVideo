"use client";

// Public registration page. Independent state from login; never auto-logs-in,
// never stores token/password. Distinct field names so the browser cannot
// copy login credentials into this form.
import Link from "next/link";
import { useEffect, useState } from "react";

import { register } from "@/lib/auth";
import * as logBus from "@/lib/log-bus";

const EMPTY = { username: "", email: "", full_name: "", password: "", confirm: "" };

export default function RegisterPage() {
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPass, setShowPass] = useState(false);

  // Start clean on mount; wipe passwords on unmount.
  useEffect(() => {
    setForm({ ...EMPTY });
    return () => setForm((f) => ({ ...f, password: "", confirm: "" }));
  }, []);

  const set = (k: keyof typeof EMPTY, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (form.password !== form.confirm) {
      setError("Parolele nu coincid.");
      return;
    }
    setBusy(true);
    // Only the username (an identifier) is logged — never password/confirm.
    logBus.emit({ source: "frontend", level: "info", message: "register submitted", meta: { username: form.username.trim() } });
    try {
      await register(form.username.trim(), form.email.trim(), form.full_name.trim(), form.password);
      setForm({ ...EMPTY }); // clear everything (incl. passwords) after success
      setOk("Înregistrarea a fost trimisă. Contul trebuie aprobat de administrator înainte de autentificare.");
      logBus.emit({ source: "frontend", level: "success", message: "register success", meta: { username: form.username.trim() } });
    } catch (err) {
      setForm((f) => ({ ...f, password: "", confirm: "" }));
      const msg = (err as Error).message || "Înregistrare eșuată.";
      setError(msg);
      logBus.emit({ source: "frontend", level: "error", message: "register failed", meta: { username: form.username.trim(), error: msg } });
    } finally {
      setBusy(false);
    }
  };

  const field = (id: string, label: string, key: keyof typeof EMPTY, type = "text", ac = "off") => (
    <div className="auth-field">
      <label className="auth-label" htmlFor={id}>{label}</label>
      <input
        id={id} name={id} className="auth-input" type={type} autoComplete={ac}
        value={form[key]} onChange={(e) => set(key, e.target.value)} disabled={busy}
      />
    </div>
  );

  // Password field with a show/hide toggle. The single ``showPass`` state
  // governs both password inputs so they reveal/hide together.
  const passwordField = (id: string, label: string, key: keyof typeof EMPTY) => (
    <div className="auth-field">
      <label className="auth-label" htmlFor={id}>{label}</label>
      <div style={{ position: "relative" }}>
        <input
          id={id} name={id} className="auth-input"
          type={showPass ? "text" : "password"} autoComplete="new-password"
          value={form[key]} onChange={(e) => set(key, e.target.value)} disabled={busy}
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
  );

  return (
    <div className="public-landing">
      <div className="public-card public-form">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/AIVideo.png" alt="P1.AIVideo" className="public-logo public-logo-sm" />
        <h1 className="public-title">P1.AIVideo</h1>
        <p className="public-tagline">Înregistrare</p>
        {ok ? (
          <div data-testid="register-success">
            <p className="public-success">{ok}</p>
            <div className="public-links"><Link href="/login">Înapoi la autentificare</Link></div>
          </div>
        ) : (
          <form onSubmit={submit} className="auth-form" autoComplete="off">
            {field("register-username", "Utilizator", "username")}
            {field("register-email", "Email", "email", "email")}
            {field("register-full-name", "Nume complet", "full_name")}
            {passwordField("register-password", "Parolă", "password")}
            {passwordField("register-confirm-password", "Confirmă parola", "confirm")}
            <p className="auth-hint">
              Minim 10 caractere, cu majusculă, minusculă, cifră și un caracter special.
            </p>
            <button type="submit" className="auth-button" disabled={busy}>
              {busy ? "Se trimite…" : "Înregistrare"}
            </button>
            {error && <p data-testid="register-error" className="public-error">{error}</p>}
            <div className="public-links">
              <Link href="/login">Autentificare</Link>
              <Link href="/">← Acasă</Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
