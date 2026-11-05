/** Dados de exemplo determinísticos para a primeira execução (vendas por região, com efeito de tratamento). */
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function sampleCsv(n = 160): string {
  const rnd = mulberry32(42);
  const gauss = () => Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd());
  const regioes = ["Norte", "Sul", "Leste", "Oeste"];
  const lines = ["data,regiao,grupo,receita,custo,satisfacao"];
  for (let i = 0; i < n; i++) {
    const mes = i % 12;
    const regiao = regioes[Math.floor(rnd() * regioes.length)];
    const tratamento = rnd() < 0.5;
    const sazonal = 6 * Math.sin((mes / 12) * 2 * Math.PI);
    const receita = 100 + sazonal + (tratamento ? 9 : 0) + (regiao === "Sul" ? 6 : 0) + gauss() * 14;
    const custo = 60 + receita * 0.18 + gauss() * 5;
    const sat = Math.min(5, Math.max(1, Math.round(3.2 + (tratamento ? 0.5 : 0) + gauss() * 0.9)));
    const dia = String(1 + Math.floor(rnd() * 27)).padStart(2, "0");
    lines.push(`2024-${String(mes + 1).padStart(2, "0")}-${dia},${regiao},${tratamento ? "tratamento" : "controle"},${receita.toFixed(2)},${custo.toFixed(2)},${sat}`);
  }
  return lines.join("\n") + "\n";
}
