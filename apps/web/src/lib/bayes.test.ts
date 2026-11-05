import { describe, expect, it } from "vitest";
import { bayesNotes, evidence, fmtBF, toBF10 } from "./bayes";

const table = (data: Record<string, unknown>[]) => ({ schema: { fields: [] }, data });
const tree = (tables: Record<string, Record<string, unknown>[]>) => Object.fromEntries(Object.entries(tables).map(([k, v]) => [k, table(v)]));

describe("toBF10", () => {
  it("converte as três escalas do JASP", () => {
    expect(toBF10(4, "BF10")).toBe(4);
    expect(toBF10(4, undefined)).toBe(4);
    expect(toBF10(4, "BF01")).toBe(0.25);
    expect(toBF10(Math.log(4), "LogBF10")).toBeCloseTo(4, 12);
  });
});

describe("evidence (Lee & Wagenmakers)", () => {
  it.each([
    [1.5, "H1", "anedótica"], [3.0001, "H1", "moderada"], [9.9, "H1", "moderada"], [10, "H1", "forte"], [29.9, "H1", "forte"], [30, "H1", "muito forte"], [99, "H1", "muito forte"], [100, "H1", "extrema"], [6.86e35, "H1", "extrema"],
    [0.5, "H0", "anedótica"], [1 / 5, "H0", "moderada"], [1 / 10, "H0", "forte"], [1 / 50, "H0", "muito forte"], [1 / 1000, "H0", "extrema"],
  ])("BF₁₀ = %s favorece %s com evidência %s", (bf, favors, strength) => {
    expect(evidence(bf)).toMatchObject({ favors, strength });
  });
  it("BF₁₀ = 1 não favorece nada; o fator é sempre ≥ 1", () => {
    expect(evidence(1)).toMatchObject({ favors: "none", ratio: 1 });
    expect(evidence(0.25).ratio).toBeCloseTo(4, 12);
  });
});

describe("fmtBF", () => {
  it("vírgula decimal e notação científica nos extremos", () => {
    expect(fmtBF(4.356)).toBe("4,36");
    expect(fmtBF(6.8595e35)).toBe("6,86e35");
    expect(fmtBF(0.0004)).toBe("4,00e-4");
  });
});

describe("bayesNotes", () => {
  it("t bayesiano: frase com o BF, a força e o lado favorecido, mais a legenda", () => {
    const n = bayesNotes("TTestBayesianIndependentSamples", {}, tree({ "ttestContainer/ttestTable": [{ variable: "score", BF: 4.356, error: 0.007 }] }));
    expect(n[0].text).toMatch(/^score: BF₁₀ = 4,36: evidência moderada a favor de H₁ \(há diferença\).*4,36 vezes mais prováveis sob H₁ do que sob H₀/);
    expect(n.at(-1)!.text).toMatch(/Lee e Wagenmakers/);
  });
  it("respeita BF₀₁ e log: a interpretação é sempre sobre BF₁₀", () => {
    const row = (bf: number) => tree({ "x/ttestTable": [{ variable: "y", BF: bf }] });
    expect(bayesNotes("TTestBayesianOneSample", { bayesFactorType: "BF01" }, row(1 / 12))[0].text).toMatch(/BF₁₀ = 12,00: evidência forte a favor de H₁/);
    expect(bayesNotes("TTestBayesianOneSample", { bayesFactorType: "LogBF10" }, row(Math.log(0.05)))[0].text).toMatch(/BF₁₀ = 0,05: evidência forte a favor de H₀/);
  });
  it("pareado nomeia as duas medidas; unilateral fala de H₁ direcional; BF = 1 não favorece ninguém", () => {
    const n = bayesNotes("TTestBayesianPairedSamples", { alternative: "greater" }, tree({ "x/ttestTable": [{ variable1: "antes", separator: "-", variable2: "depois", BF: 20 }] }));
    expect(n[0].text).toMatch(/^antes − depois: BF₁₀ = 20,00: evidência forte a favor de H₁ \(unilateral\)/);
    expect(bayesNotes("TTestBayesianOneSample", {}, tree({ "x/ttestTable": [{ variable: "y", BF: 1 }] }))[0].text).toMatch(/não favorecem nem H₁ nem H₀/);
  });
  it("ANOVA bayesiana: BF de inclusão por efeito (interação com ×); só na escala BF₁₀", () => {
    const res = tree({ "tableEffects": [{ Effects: "tratamento", BFInclusion: 0.935 }, { Effects: "bloco", BFInclusion: 12 }, { Effects: "A ✻ B", BFInclusion: 0.02 }] });
    const n = bayesNotes("AnovaBayesian", {}, res);
    expect(n[0].text).toMatch(/^tratamento: BF de inclusão = 0,94: evidência anedótica a favor de excluir/);
    expect(n[1].text).toMatch(/^bloco: .*evidência forte a favor de incluir/);
    expect(n[2].text).toMatch(/^A × B: .*muito forte a favor de excluir/);
    expect(bayesNotes("AnovaBayesian", { bayesFactorType: "BF01" }, res)).toEqual([]);
  });
  it("análises não bayesianas, tabelas ausentes ou BF não numérico: nada", () => {
    expect(bayesNotes("Anova", {}, tree({ "x/ttestTable": [{ BF: 3 }] }))).toEqual([]);
    expect(bayesNotes("TTestBayesianOneSample", {}, tree({}))).toEqual([]);
    expect(bayesNotes("TTestBayesianOneSample", {}, tree({ "x/ttestTable": [{ variable: "y", BF: "" }] }))).toEqual([]);
    expect(bayesNotes("TTestBayesianOneSample", {}, null)).toEqual([]);
  });
});
