import { useState, type FormEvent } from "react";
import { api } from "../api";
import { credentialProblem, ROLE_LABEL } from "../lib/auth";
import { routeHref } from "../lib/route";
import { Avatar } from "./Avatar";
import { useCan, useSession } from "./AuthGate";

/** Nome + papel + sair, na barra superior. Some quando a autenticação está desligada. */
export function UserMenu() {
  const { user, authEnabled, signOut } = useSession();
  const [changing, setChanging] = useState(false);
  if (!authEnabled) return null;
  return (
    <>
      <a className="user-chip" href={routeHref({ name: "profile" })} title={`${user.username} · ${ROLE_LABEL[user.role]} — abrir perfil`}>
        <Avatar name={user.display_name} version={user.avatar_version} size={26} />
        <span className="user-chip-name">{user.display_name} <span className="muted small">({ROLE_LABEL[user.role]})</span></span>
      </a>
      <button className="btn ghost sm" onClick={() => setChanging(true)}>Senha</button>
      <button className="btn ghost sm" onClick={() => void signOut()}>Sair</button>
      {changing && <PasswordDialog username={user.username} onClose={() => setChanging(false)} />}
    </>
  );
}

/** Link "Perfil" da navegação (só com login ligado: sem ele não existe usuário para ter perfil). */
export function ProfileLink({ current }: { current: boolean }) {
  const { authEnabled } = useSession();
  if (!authEnabled) return null;
  return <a href={routeHref({ name: "profile" })} aria-current={current ? "page" : undefined}>Perfil</a>;
}

/** Link "Usuários" da navegação (só administradores). */
export function UsersLink({ current }: { current: boolean }) {
  const admin = useCan("admin");
  const { authEnabled } = useSession();
  if (!admin || !authEnabled) return null;
  return <a href={routeHref({ name: "users" })} aria-current={current ? "page" : undefined}>Usuários</a>;
}

/** Link "Assinaturas" (painel do SaaS: usuários por plano, MRR, eventos do Stripe) — só o administrador da plataforma. */
export function BillingAdminLink({ current }: { current: boolean }) {
  const admin = useCan("admin");
  const { authEnabled } = useSession();
  if (!admin || !authEnabled) return null;
  return <a href={routeHref({ name: "admin" })} aria-current={current ? "page" : undefined}>Assinaturas</a>;
}

function PasswordDialog({ username, onClose }: { username: string; onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = credentialProblem(username, next);
    if (problem) return setError(problem);
    try { await api.changePassword(current, next); setDone(true); setError(null); } catch (err) { setError((err as Error).message); }
  };

  return (
    <div className="modal-backdrop" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form className="modal card" style={{ maxWidth: 420 }} role="dialog" aria-modal="true" aria-label="Trocar senha" onSubmit={submit}>
        <div className="modal-head"><strong>Trocar senha</strong><span className="spacer" /><button type="button" className="btn ghost sm" onClick={onClose} aria-label="Fechar">✕</button></div>
        <div className="modal-body">
          {done ? <p>Senha alterada. Suas outras sessões foram encerradas.</p> : (
            <>
              {error && <div className="alert" role="alert">{error}</div>}
              <label className="field">Senha atual<input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" autoFocus required /></label>
              <label className="field">Nova senha<input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required /></label>
            </>
          )}
          <div>{done ? <button type="button" className="btn primary" onClick={onClose}>Fechar</button> : <button type="submit" className="btn primary">Trocar senha</button>}</div>
        </div>
      </form>
    </div>
  );
}
