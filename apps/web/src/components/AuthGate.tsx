import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, UNAUTHORIZED_EVENT, type AuthStatus, type Role, type User } from "../api";
import { credentialProblem, roleCan } from "../lib/auth";

interface Session { user: User; authEnabled: boolean; signOut: () => Promise<void> }
const SessionContext = createContext<Session | null>(null);

export const useSession = (): Session => {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession fora do AuthGate");
  return s;
};
/** O usuário atual tem pelo menos este papel? (a API impõe; a interface só esconde o que daria 403) */
export const useCan = (role: Role): boolean => roleCan(useSession().user.role, role);

/** Decide entre primeiro acesso, login e o app. Com a autenticação desligada, passa direto. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api.authStatus().then(setStatus).catch((e) => setError((e as Error).message)), []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    // qualquer 401 da API (sessão expirada, usuário desativado) devolve ao login
    const onExpired = () => setStatus((s) => (s && s.auth_enabled ? { ...s, user: null } : s));
    addEventListener(UNAUTHORIZED_EVENT, onExpired);
    return () => removeEventListener(UNAUTHORIZED_EVENT, onExpired);
  }, []);

  if (error) return <div className="auth-page"><div className="card auth-card"><h1>Metastatistic</h1><div className="alert" role="alert">{error}</div><button className="btn" onClick={() => { setError(null); void load(); }}>Tentar de novo</button></div></div>;
  if (!status) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;
  if (status.user) {
    const signOut = async () => { try { await api.logout(); } finally { await load(); } };
    return <SessionContext.Provider value={{ user: status.user, authEnabled: status.auth_enabled, signOut }}>{children}</SessionContext.Provider>;
  }
  return <CredentialsForm setup={status.needs_setup} onDone={(user) => setStatus({ ...status, needs_setup: false, user })} />;
}

function CredentialsForm({ setup, onDone }: { setup: boolean; onDone: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = setup ? credentialProblem(username, password) ?? (password !== confirm ? "As senhas não são iguais." : null) : null;
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      onDone(setup ? await api.setup(username, password, displayName) : await api.login(username, password));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>{setup ? "Criar o administrador" : "Entrar"}</h1>
        <p className="muted small" style={{ marginTop: 0 }}>
          {setup ? "Primeiro acesso: esta conta gerencia os demais usuários." : "Metastatistic"}
        </p>
        {error && <div className="alert" role="alert">{error}</div>}
        <label className="field">Usuário
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        {setup && (
          <label className="field">Nome exibido (opcional)
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="name" />
          </label>
        )}
        <label className="field">Senha
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={setup ? "new-password" : "current-password"} required />
        </label>
        {setup && (
          <label className="field">Repita a senha
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
          </label>
        )}
        <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spinner" /> : null} {setup ? "Criar e entrar" : "Entrar"}</button>
      </form>
    </div>
  );
}
