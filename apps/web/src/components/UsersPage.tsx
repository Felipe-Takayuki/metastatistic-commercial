import { useEffect, useState, type FormEvent } from "react";
import { api, type Role, type User } from "../api";
import { credentialProblem, formatAttributes, parseAttributes, ROLE_HELP, ROLE_LABEL } from "../lib/auth";
import { AuditLog } from "./AuditLog";
import { useCan, useSession } from "./AuthGate";

const ROLES: Role[] = ["viewer", "editor", "admin"];

export function UsersPage() {
  const { user: me, authEnabled } = useSession();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = useCan("admin");
  const [tab, setTab] = useState<"users" | "audit">("users");

  const load = () => api.listUsers().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => { if (isAdmin) void load(); }, [isAdmin]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); }
  };

  const resetPassword = (u: User) => {
    const pw = window.prompt(`Nova senha para "${u.username}" (mínimo 8 caracteres). As sessões abertas dele serão encerradas.`);
    if (pw) void act(() => api.patchUser(u.id, { password: pw }));
  };
  const editAttributes = (u: User) => {
    const text = window.prompt(
      `Atributos de "${u.username}" para a segurança por linha, no formato nome=valor1,valor2; outro=valor (vazio apaga todos):`,
      formatAttributes(u.attributes),
    );
    if (text !== null) void act(() => api.patchUser(u.id, { attributes: parseAttributes(text) }));
  };
  const remove = (u: User) => {
    if (window.confirm(`Excluir o usuário "${u.username}"? Isso não pode ser desfeito.`)) void act(() => api.deleteUser(u.id));
  };

  if (!isAdmin) return <div className="card empty"><h2>Sem permissão</h2><p>Apenas administradores gerenciam usuários.</p></div>;
  if (!authEnabled) {
    return (
      <div className="card empty">
        <h2>A autenticação está desligada</h2>
        <p style={{ margin: "0 auto", maxWidth: 520 }}>
          Hoje qualquer pessoa que alcance o servidor tem acesso total. Para exigir login, inicie a API com <span className="chip">AUTH_ENABLED=true</span>;
          o primeiro acesso cria o administrador.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="page-head"><h1>Usuários</h1></div>
      <div className="tabs" role="tablist">
        <button className="tab" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>Usuários</button>
        <button className="tab" role="tab" aria-selected={tab === "audit"} onClick={() => setTab("audit")}>Auditoria</button>
      </div>
      {tab === "audit" ? <AuditLog /> : <>
      {error && <div className="alert" role="alert">{error}</div>}
      {users === null && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      {users && (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="users-table">
            <thead><tr><th>Usuário</th><th>Nome</th><th>Papel</th><th>Atributos</th><th>Situação</th><th /></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} data-user={u.username}>
                  <td><strong>{u.username}</strong>{u.id === me.id && <span className="chip" style={{ marginLeft: 8 }}>você</span>}</td>
                  <td>{u.display_name}</td>
                  <td>
                    <select value={u.role} aria-label={`Papel de ${u.username}`} onChange={(e) => void act(() => api.patchUser(u.id, { role: e.target.value as Role }))}>
                      {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </select>
                  </td>
                  <td className="small">{formatAttributes(u.attributes) || <span className="muted">—</span>}</td>
                  <td>{u.active ? "Ativo" : <span className="muted">Desativado</span>}</td>
                  <td className="users-actions">
                    <button className="btn ghost sm" onClick={() => void act(() => api.patchUser(u.id, { active: !u.active }))}>{u.active ? "Desativar" : "Reativar"}</button>
                    <button className="btn ghost sm" onClick={() => editAttributes(u)} aria-label={`Atributos de ${u.username}`}>Atributos</button>
                    <button className="btn ghost sm" onClick={() => resetPassword(u)}>Nova senha</button>
                    <button className="btn ghost sm" onClick={() => remove(u)} aria-label={`Excluir ${u.username}`}>Excluir</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NewUser onCreate={(u) => act(() => api.createUser(u))} />
      <p className="muted small">
        {ROLES.map((r) => <span key={r} style={{ display: "block" }}><strong>{ROLE_LABEL[r]}</strong>: {ROLE_HELP[r]}.</span>)}
      </p>
      </>}
    </>
  );
}

function NewUser({ onCreate }: { onCreate: (u: { username: string; password: string; display_name: string; role: Role }) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = credentialProblem(username, password);
    setProblem(p);
    if (p) return;
    await onCreate({ username, password, display_name: displayName, role });
    setUsername(""); setDisplayName(""); setPassword("");
  };

  return (
    <form className="card new-user" onSubmit={submit}>
      <h2 style={{ margin: 0, fontSize: 16 }}>Novo usuário</h2>
      {problem && <div className="alert" role="alert">{problem}</div>}
      <div className="new-user-fields">
        <label className="field">Usuário<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" required /></label>
        <label className="field">Nome exibido<input value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="off" /></label>
        <label className="field">Senha inicial<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required /></label>
        <label className="field">Papel
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </label>
      </div>
      <div><button className="btn primary" type="submit">Criar usuário</button></div>
    </form>
  );
}
