"use client";

// User management — protected super admin only (security remediation).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getCurrentUser, isProtectedSuperAdmin } from "@/lib/auth";
import {
  approveUser, deleteUser, listUsers, reactivateUser, rejectUser, suspendUser,
  type ManagedUser,
} from "@/lib/users";

const TABS = ["pending", "active", "suspended", "rejected", "deleted"] as const;
type Tab = (typeof TABS)[number];

export default function UsersPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<readonly ManagedUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const u = getCurrentUser();
    if (!u) { router.push("/login"); return; }
    setAllowed(isProtectedSuperAdmin(u));
  }, [router]);

  const reload = async (t: Tab) => {
    setError(null);
    try {
      const res = await listUsers(t, t === "deleted");
      setRows(res.items);
    } catch (err) { setError((err as Error).message); }
  };

  useEffect(() => { if (allowed) void reload(tab); /* eslint-disable-next-line */ }, [allowed, tab]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); await reload(tab); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };

  if (allowed === null) return <p className="muted">Loading…</p>;
  if (!allowed) return <p data-testid="users-denied" style={{ color: "var(--danger)" }}>Access denied.</p>;

  return (
    <div>
      <h1>Users</h1>
      <p className="muted" style={{ fontSize: 12 }}>
        Per-user data isolation is not implemented in this phase. All approved users operate on shared workspace data.
      </p>
      <div className="tabs" style={{ display: "flex", gap: 8, margin: "12px 0", flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button key={t} type="button" className={`btn ${tab === t ? "btn-primary" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      <table className="simple" style={{ width: "100%", fontSize: 13 }}>
        <thead><tr>
          <th>username</th><th>email</th><th>role</th><th>status</th><th>active</th><th>created</th><th>actions</th>
        </tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={7} className="muted">No users.</td></tr>}
          {rows.map((u) => (
            <tr key={u.id}>
              <td>{u.username}{u.is_protected && <span className="badge badge-success" style={{ marginLeft: 6 }}>Protected Super Admin</span>}</td>
              <td>{u.email ?? "—"}</td>
              <td>{u.role}</td>
              <td>{u.user_status}</td>
              <td>{u.is_active ? "yes" : "no"}</td>
              <td>{u.created_at?.slice(0, 10) ?? "—"}</td>
              <td style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {u.is_protected ? (
                  <span className="muted">—</span>
                ) : (
                  <>
                    {u.user_status === "pending" && (
                      <>
                        <button className="btn btn-primary" disabled={busy}
                          onClick={() => act(() => approveUser(u.id, "operator"))}>Approve (operator)</button>
                        <button className="btn" disabled={busy} onClick={() => act(() => rejectUser(u.id))}>Reject</button>
                      </>
                    )}
                    {u.user_status === "active" && (
                      <button className="btn" disabled={busy} onClick={() => act(() => suspendUser(u.id))}>Suspend</button>
                    )}
                    {u.user_status === "suspended" && (
                      <button className="btn btn-primary" disabled={busy} onClick={() => act(() => reactivateUser(u.id))}>Reactivate</button>
                    )}
                    {u.user_status !== "deleted" && (
                      <button className="btn btn-danger" disabled={busy}
                        onClick={() => { if (confirm(`Delete ${u.username}?`)) act(() => deleteUser(u.id)); }}>Delete</button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
