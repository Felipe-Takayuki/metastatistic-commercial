import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

const html = (md: string) => renderToStaticMarkup(<>{renderMarkdown(md)}</>);

describe("renderMarkdown", () => {
  it("títulos viram h2–h4 (o título do relatório é o único h1)", () => {
    expect(html("# A\n## B\n### C")).toBe("<h2>A</h2><h3>B</h3><h4>C</h4>");
  });
  it("parágrafos, negrito, itálico e código inline", () => {
    expect(html("Isso é **forte**, *leve* e `x <- 1`.")).toBe("<p>Isso é <strong>forte</strong>, <em>leve</em> e <code>x &lt;- 1</code>.</p>");
  });
  it("linhas seguidas formam um parágrafo; linha em branco separa", () => {
    expect(html("um\ndois\n\ntrês")).toBe("<p>um dois</p><p>três</p>");
  });
  it("listas ordenadas e não ordenadas, e citação", () => {
    expect(html("- a\n- b")).toBe("<ul><li>a</li><li>b</li></ul>");
    expect(html("1. x\n2. y")).toBe("<ol><li>x</li><li>y</li></ol>");
    expect(html("> nota\n> longa")).toBe("<blockquote>nota longa</blockquote>");
  });
  it("bloco de código preserva o conteúdo literal (sem interpretar markdown)", () => {
    expect(html("```\n# não é título **nem negrito**\n```")).toBe("<pre><code># não é título **nem negrito**</code></pre>");
  });
  it("bloco de código sem fechamento não trava nem engole o resto do texto de forma errada", () => {
    expect(html("```\ncodigo")).toBe("<pre><code>codigo</code></pre>");
  });
  it("régua horizontal", () => {
    expect(html("a\n\n---\n\nb")).toBe("<p>a</p><hr/><p>b</p>");
  });
  it("links http/https/mailto viram âncoras seguras", () => {
    expect(html("[site](https://exemplo.com/x?a=1)")).toBe('<p><a href="https://exemplo.com/x?a=1" target="_blank" rel="noopener noreferrer">site</a></p>');
    expect(html("[m](mailto:a@b.com)")).toContain('href="mailto:a@b.com"');
  });
});

describe("renderMarkdown — segurança (texto do relatório é conteúdo de usuário)", () => {
  it("HTML e <script> aparecem como texto escapado", () => {
    const out = html('<script>alert(1)</script> <img src=x onerror="alert(2)">');
    expect(out).not.toContain("<script");
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;script&gt;");
    expect(out).toContain("&lt;img src=x onerror=&quot;alert(2)&quot;&gt;");
  });
  it.each(["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "//evil.com", "file:///etc/passwd"])(
    "link com esquema perigoso '%s' não vira âncora",
    (url) => {
      const out = html(`[clique](${url})`);
      expect(out).not.toContain("<a ");
      expect(out).not.toContain("href=");
    },
  );
  it("HTML dentro de negrito, título e lista também é escapado", () => {
    for (const md of ["**<b onclick=x>**", "# <i>t</i>", "- <u>x</u>", "> <s>q</s>"]) {
      const out = html(md);
      expect(out).not.toMatch(/<(b|i|u|s) /);
      expect(out).not.toMatch(/<(i|u|s)>/);
    }
  });
  it("entrada patológica não trava (sem regex catastrófica)", () => {
    const t0 = Date.now();
    html("*".repeat(20000) + "[" .repeat(5000) + "`".repeat(5000) + "**a".repeat(3000));
    expect(Date.now() - t0).toBeLessThan(1000);
  });
  it("texto vazio ou só espaços não gera nada", () => {
    expect(html("")).toBe("");
    expect(html("   \n \n")).toBe("");
  });
});
