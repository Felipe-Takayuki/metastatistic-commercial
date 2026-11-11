import { useRef, useState } from "react";
import { api } from "../api";
import { AVATAR_ACCEPT, AVATAR_MAX_BYTES, avatarProblem } from "../lib/avatar";
import { ROLE_LABEL } from "../lib/auth";
import { Avatar } from "./Avatar";
import { useSession } from "./AuthGate";

/** Aba "Perfil": foto de perfil (guardada no bucket do Garage) e dados da conta. */
export function ProfilePage() {
  const { user, authEnabled, updateUser } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!authEnabled) {
    return (
      <div className="card card-pad">
        <h1>Perfil</h1>
        <p className="muted">O perfil fica disponível quando o login está ligado (<span className="mono">AUTH_ENABLED=true</span>).</p>
      </div>
    );
  }

  const send = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    setNotice(null);
    const problem = avatarProblem(file);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      updateUser(await api.uploadAvatar(file));
      setNotice("Foto atualizada.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.deleteAvatar();
      updateUser({ ...user, avatar_version: null });
      setNotice("Foto removida.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="profile">
      <div className="page-head"><h1>Perfil</h1></div>
      <section className="card card-pad profile-card" aria-labelledby="profile-photo">
        <div className="profile-avatar"><Avatar name={user.display_name} version={user.avatar_version} size={112} /></div>
        <div className="profile-body">
          <h2 id="profile-photo">Foto de perfil</h2>
          <p className="muted small">PNG, JPEG, WebP ou GIF, até {AVATAR_MAX_BYTES / 1024 / 1024} MB. Arrastar a imagem para a área abaixo também funciona.</p>
          {error && <div className="alert" role="alert">{error}</div>}
          {notice && <p className="small" role="status">{notice}</p>}
          <div
            className={`dropzone${over ? " over" : ""}`}
            role="button"
            tabIndex={0}
            aria-label="Escolher imagem de perfil"
            onClick={() => !busy && input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), !busy && input.current?.click())}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) void send(e.dataTransfer.files[0]); }}
          >
            {busy ? <span className="spinner" aria-label="Enviando" /> : <><strong>{user.avatar_version ? "Trocar a foto" : "Enviar uma foto"}</strong><span className="small">clique ou arraste a imagem</span></>}
            <input ref={input} type="file" accept={AVATAR_ACCEPT} hidden onChange={(e) => void send(e.target.files?.[0])} />
          </div>
          {user.avatar_version && <div><button className="btn sm" onClick={() => void remove()} disabled={busy}>Remover foto</button></div>}
        </div>
      </section>

      <section className="card card-pad" aria-labelledby="profile-account" style={{ marginTop: 16 }}>
        <h2 id="profile-account">Conta</h2>
        <dl className="profile-facts">
          <dt>Nome</dt><dd>{user.display_name}</dd>
          <dt>Usuário</dt><dd className="mono">{user.username}</dd>
          <dt>Papel</dt><dd>{ROLE_LABEL[user.role]}</dd>
        </dl>
      </section>
    </div>
  );
}
