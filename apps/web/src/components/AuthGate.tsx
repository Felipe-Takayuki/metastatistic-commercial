import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, UNAUTHORIZED_EVENT, type AuthStatus, type Role, type User } from "../api";
import { credentialProblem, roleCan } from "../lib/auth";
import { LandingPage } from "./LandingPage";

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
  const [authModalTab, setAuthModalTab] = useState<"login" | "register" | null>(null);

  const load = useCallback(() => api.authStatus().then(setStatus).catch((e) => setError((e as Error).message)), []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    // qualquer 401 da API (sessão expirada, usuário desativado) devolve ao login
    const onExpired = () => setStatus((s) => (s && s.auth_enabled ? { ...s, user: null } : s));
    addEventListener(UNAUTHORIZED_EVENT, onExpired);
    return () => removeEventListener(UNAUTHORIZED_EVENT, onExpired);
  }, []);

  if (error) {
    return (
      <div className="auth-page">
        <div className="card auth-card">
          <h1>Metastatistic</h1>
          <div className="alert" role="alert">{error}</div>
          <button className="btn" onClick={() => { setError(null); void load(); }}>Tentar de novo</button>
        </div>
      </div>
    );
  }

  if (!status) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;

  if (status.user) {
    const signOut = async () => { try { await api.logout(); } finally { await load(); } };
    return (
      <SessionContext.Provider value={{ user: status.user, authEnabled: status.auth_enabled, signOut }}>
        {children}
      </SessionContext.Provider>
    );
  }

  return (
    <>
      <LandingPage onOpenAuth={(tab) => setAuthModalTab(tab)} />

      {authModalTab !== null && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget) setAuthModalTab(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setAuthModalTab(null);
          }}
          tabIndex={-1}
        >
          <CredentialsForm
            initialTab={authModalTab}
            setup={status.needs_setup}
            onClose={() => setAuthModalTab(null)}
            onDone={(user) => {
              setAuthModalTab(null);
              setStatus({ ...status, needs_setup: false, user });
            }}
          />
        </div>
      )}
    </>
  );
}

function CredentialsForm({
  initialTab = "login",
  setup,
  onClose,
  onDone,
}: {
  initialTab?: "login" | "register";
  setup: boolean;
  onClose?: () => void;
  onDone: (u: User) => void;
}) {
  const [tab, setTab] = useState<"login" | "register">(setup ? "register" : initialTab);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setTab(setup ? "register" : initialTab);
    setError(null);
  }, [initialTab, setup]);

  const switchTab = (nextTab: "login" | "register") => {
    setTab(nextTab);
    setError(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (tab === "register") {
      const problem = credentialProblem(username, password) ?? (password !== confirm ? "As senhas não são iguais." : null);
      if (problem) return setError(problem);
    }
    setBusy(true);
    setError(null);
    try {
      if (tab === "register") {
        const user = await api.register(username, password, displayName.trim() || undefined);
        onDone(user);
      } else {
        const user = await api.login(username, password);
        onDone(user);
      }
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="card auth-card" style={{ position: "relative" }}>
      {onClose && (
        <button
          type="button"
          className="btn ghost sm"
          onClick={onClose}
          aria-label="Fechar modal de autenticação"
          style={{ position: "absolute", top: 14, right: 14, zIndex: 2 }}
        >
          ✕
        </button>
      )}

      <div className="tabs auth-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "login"}
          className="tab"
          onClick={() => switchTab("login")}
        >
          Entrar
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "register"}
          className="tab"
          onClick={() => switchTab("register")}
        >
          {setup ? "Criar Administrador" : "Criar Conta"}
        </button>
      </div>

      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <h1>{tab === "login" ? "Entrar" : (setup ? "Criar o administrador" : "Criar Conta")}</h1>
        <p className="muted small" style={{ marginTop: -4, marginBottom: 4 }}>
          {tab === "login"
            ? "Metastatistic"
            : (setup
              ? "Primeiro acesso: esta conta gerencia os demais usuários."
              : "Preencha seus dados para criar sua conta no Metastatistic")}
        </p>

        {error && <div className="alert" role="alert">{error}</div>}

        {tab === "register" && (
          <label className="field">
            Nome Completo
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
              placeholder="Ex: Maria Silva"
            />
          </label>
        )}

        <label className="field">
          Usuário / E-mail
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder={tab === "register" ? "Ex: maria.silva" : "Seu usuário"}
            autoFocus
            required
          />
        </label>

        <label className="field">
          Senha
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={tab === "register" ? "new-password" : "current-password"}
            placeholder={tab === "register" ? "Mínimo 8 caracteres" : "Sua senha"}
            required
          />
        </label>

        {tab === "register" && (
          <label className="field">
            Confirmar Senha
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              placeholder="Repita a mesma senha"
              required
            />
          </label>
        )}

        <button className="btn primary" type="submit" disabled={busy} style={{ marginTop: 4 }}>
          {busy ? <span className="spinner" /> : null}{" "}
          {tab === "login" ? "Entrar" : (setup ? "Criar administrador e entrar" : "Criar minha conta")}
        </button>
      </form>

      <div className="auth-switch">
        {tab === "login" ? (
          <>
            Não tem uma conta?{" "}
            <button type="button" className="btn-link" onClick={() => switchTab("register")}>
              Criar conta
            </button>
          </>
        ) : (
          <>
            Já tem uma conta?{" "}
            <button type="button" className="btn-link" onClick={() => switchTab("login")}>
              Fazer login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
