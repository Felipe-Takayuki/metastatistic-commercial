import type { TextBlock } from "../../api";
import { renderMarkdown } from "../../lib/markdown";

export function TextBlockView({ block }: { block: TextBlock }) {
  return <div className="report-block markdown">{renderMarkdown(block.markdown)}</div>;
}

export function TextBlockEditor({ block, onChange }: { block: TextBlock; onChange: (b: TextBlock) => void }) {
  return (
    <>
      <textarea
        className="md-input"
        value={block.markdown}
        onChange={(e) => onChange({ ...block, markdown: e.target.value })}
        rows={Math.min(14, Math.max(4, block.markdown.split("\n").length + 1))}
        placeholder={"Escreva em Markdown: # Título, **negrito**, *itálico*, - listas, > citação"}
        aria-label="Texto do bloco (Markdown)"
      />
      {block.markdown.trim() && (
        <div className="md-preview">
          <div className="section-label" style={{ marginBottom: 6 }}>Pré-visualização</div>
          <div className="markdown">{renderMarkdown(block.markdown)}</div>
        </div>
      )}
    </>
  );
}
