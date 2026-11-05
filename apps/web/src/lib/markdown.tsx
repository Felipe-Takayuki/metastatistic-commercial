import { createElement, type ReactNode } from "react";

/**
 * Markdown mínimo e seguro para blocos de texto de relatório.
 * Tudo vira nós de texto do React (escapados); não existe caminho para HTML cru.
 * Suporta: # ## ### (viram h2-h4: o título do relatório é o único h1), listas, citação, código, ---, **negrito**,
 * *itálico*, `código`, [texto](http|https|mailto).
 */
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\s][^*\n]*\*)|(\[[^\]\n]+\]\([^)\s]+\))/g;
const SAFE_URL = /^(https?:|mailto:)/i;

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(INLINE)) {
    const i = m.index!;
    if (i > last) out.push(text.slice(last, i));
    const tok = m[0];
    const key = `${keyBase}.${n++}`;
    if (m[1]) out.push(<code key={key}>{tok.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={key}>{inline(tok.slice(2, -2), key)}</strong>);
    else if (m[3]) out.push(<em key={key}>{inline(tok.slice(1, -1), key)}</em>);
    else {
      const [, label, url] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
      // esquemas fora da lista (javascript:, data:…) não viram link: o texto digitado aparece como está
      out.push(SAFE_URL.test(url) ? <a key={key} href={url} target="_blank" rel="noopener noreferrer">{inline(label, key)}</a> : tok);
    }
    last = i + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function renderMarkdown(src: string): ReactNode[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let k = 0;
  const key = () => `b${k++}`;
  const isSpecial = (l: string) => /^(#{1,3}\s|>\s?|[-*]\s|\d+\.\s|```|---+\s*$)/.test(l);

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (line.startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++; // fecha o bloco (ou fim do texto)
      out.push(<pre key={key()}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) { out.push(createElement(`h${h[1].length + 1}`, { key: key() }, ...inline(h[2], `h${k}`))); i++; continue; }
    if (/^---+\s*$/.test(line)) { out.push(<hr key={key()} />); i++; continue; }
    if (/^>\s?/.test(line)) {
      const q: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) q.push(lines[i++].replace(/^>\s?/, ""));
      out.push(<blockquote key={key()}>{inline(q.join(" "), `q${k}`)}</blockquote>);
      continue;
    }
    const ul = /^[-*]\s+/.test(line);
    if (ul || /^\d+\.\s+/.test(line)) {
      const re = ul ? /^[-*]\s+/ : /^\d+\.\s+/;
      const items: ReactNode[] = [];
      while (i < lines.length && re.test(lines[i])) {
        items.push(<li key={items.length}>{inline(lines[i].replace(re, ""), `li${k}.${items.length}`)}</li>);
        i++;
      }
      out.push(createElement(ul ? "ul" : "ol", { key: key() }, ...items));
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !isSpecial(lines[i])) para.push(lines[i++].trim());
    out.push(<p key={key()}>{inline(para.join(" "), `p${k}`)}</p>);
  }
  return out;
}
