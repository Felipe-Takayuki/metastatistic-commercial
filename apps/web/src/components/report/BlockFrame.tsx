import type { ReactNode } from "react";

interface Props {
  label: string;
  index: number;
  count: number;
  onMove: (delta: -1 | 1) => void;
  onDelete: () => void;
  children: ReactNode;
}

/** Moldura de um bloco no modo de edição: tipo, mover para cima/baixo, excluir. */
export function BlockFrame({ label, index, count, onMove, onDelete, children }: Props) {
  return (
    <section className="block-frame" aria-label={`Bloco ${index + 1} de ${count}: ${label}`}>
      <header className="block-head">
        <span className="block-type">{label}</span>
        <span className="spacer" />
        <button className="btn ghost sm" onClick={() => onMove(-1)} disabled={index === 0} aria-label="Mover bloco para cima" title="Mover para cima">↑</button>
        <button className="btn ghost sm" onClick={() => onMove(1)} disabled={index === count - 1} aria-label="Mover bloco para baixo" title="Mover para baixo">↓</button>
        <button className="btn ghost sm" onClick={onDelete} aria-label="Excluir bloco" title="Excluir bloco">✕</button>
      </header>
      <div className="block-body">{children}</div>
    </section>
  );
}
