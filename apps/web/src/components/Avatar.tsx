import { useEffect, useState } from "react";
import { api } from "../api";
import { initials } from "../lib/avatar";

// Uma foto por versão: a barra superior e o perfil mostram a mesma imagem sem baixar duas vezes.
const urls = new Map<string, string>();
const loading = new Map<string, Promise<string>>();

function objectUrl(version: string): Promise<string> {
  const cached = urls.get(version);
  if (cached) return Promise.resolve(cached);
  let pending = loading.get(version);
  if (!pending) {
    pending = api.avatarBlob().then((blob) => {
      const url = URL.createObjectURL(blob);
      urls.set(version, url);
      return url;
    }).finally(() => loading.delete(version));
    loading.set(version, pending);
  }
  return pending;
}

interface Props { name: string; version?: string | null; size?: number }

/** Foto de perfil redonda; sem foto (ou se ela não carregar), mostra as iniciais. */
export function Avatar({ name, version, size = 28 }: Props) {
  const [src, setSrc] = useState<{ version: string; url: string } | null>(null);
  useEffect(() => {
    if (!version) return;
    let live = true;
    objectUrl(version).then((url) => live && setSrc({ version, url })).catch(() => live && setSrc(null));
    return () => { live = false; };
  }, [version]);

  const url = version && src?.version === version ? src.url : null;
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: Math.max(11, Math.round(size * 0.4)) }} aria-hidden={!url ? undefined : true}>
      {url ? <img src={url} alt="" /> : <span aria-label={name}>{initials(name)}</span>}
    </span>
  );
}
