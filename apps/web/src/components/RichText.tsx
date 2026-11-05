import { createElement, useMemo, type ReactNode } from "react";

/** Só estas tags do JASP (ênfase/índices) viram elementos; o resto vira texto. Sem dangerouslySetInnerHTML. */
const ALLOWED = new Set(["em", "i", "sub", "sup", "b", "strong"]);

function convert(node: Node, key: string, trim = false): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return trim ? node.textContent?.trim() : node.textContent;
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const tag = (node as Element).tagName.toLowerCase();
  // O JASP escreve "<em> grupo </em>": os espaços internos viram "grupo ," na tela. Corta nas bordas das tags inline.
  const children = Array.from(node.childNodes).map((c, i) => convert(c, `${key}.${i}`, ALLOWED.has(tag)));
  return ALLOWED.has(tag) ? createElement(tag, { key }, ...children) : <span key={key}>{children}</span>;
}

export function RichText({ html }: { html: string | undefined }) {
  const content = useMemo(() => {
    if (!html) return null;
    // DOMParser cria um documento inerte: não executa scripts nem carrega recursos.
    const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
    return Array.from(doc.body.childNodes).map((n, i) => convert(n, String(i)));
  }, [html]);
  return <>{content}</>;
}
