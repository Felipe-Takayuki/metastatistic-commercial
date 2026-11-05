import { useEffect, useRef, useState } from "react";

const cache = new Map<string, Promise<unknown>>();

/** Esvazia o cache (chamar quando os dados mudam: upload, exclusão, nível de medida). */
export function clearRemoteCache(): void {
  cache.clear();
}

export interface Remote<T> { data?: T; error?: string; loading: boolean }

/**
 * Busca com cache por chave. Enquanto recarrega, mantém o dado anterior (a tela não "pisca").
 * Falhas não ficam em cache. `key === null` = não buscar.
 */
export function useRemote<T>(key: string | null, fn: () => Promise<T>): Remote<T> {
  const [state, setState] = useState<Remote<T>>({ loading: key !== null });
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (key === null) {
      setState({ loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ data: s.data, loading: true }));
    let p = cache.get(key) as Promise<T> | undefined;
    if (!p) {
      p = fnRef.current();
      cache.set(key, p);
      p.catch(() => cache.delete(key));
    }
    p.then((data) => !cancelled && setState({ data, loading: false }))
      .catch((e) => !cancelled && setState({ error: (e as Error).message, loading: false }));
    return () => { cancelled = true; };
  }, [key]);

  return state;
}
