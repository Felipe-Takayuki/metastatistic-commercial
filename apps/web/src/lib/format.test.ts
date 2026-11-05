import { describe, expect, it } from "vitest";
import { formatAxis, formatCell, formatNumber, formatRaw, parseFormat } from "./format";

describe("parseFormat", () => {
  it("lê chaves numéricas e flags", () => {
    expect(parseFormat("sf:4;dp:3;p:.001")).toEqual({ sf: 4, dp: 3, p: 0.001 });
    expect(parseFormat("pc;dp:1")).toEqual({ pc: true, dp: 1 });
    expect(parseFormat(undefined)).toEqual({});
  });
});

describe("formatNumber (valores conferidos com a saída do JASP)", () => {
  const t = { name: "t", format: "sf:4;dp:3" };
  it("usa casas decimais fixas, inclusive para inteiros", () => {
    expect(formatNumber(-2.6277, t)).toBe("-2.628");
    expect(formatNumber(78, t)).toBe("78.000");
    expect(formatNumber(72.719979, t)).toBe("72.720");
  });
  it("números grandes obedecem às cifras significativas", () => {
    expect(formatNumber(12345.678, t)).toBe("12346");
  });
  it("valor minúsculo não vira 0.000 (notação científica)", () => {
    expect(formatNumber(1.5e-7, t)).toBe("1.500e-7");
    expect(formatNumber(0, t)).toBe("0.000");
  });
  it("p-valor: sem zero à esquerda e '< .001' abaixo do limiar", () => {
    const p = { name: "p", type: "pvalue", format: "dp:3;p:.001" };
    expect(formatNumber(0.0103471, p)).toBe(".010");
    expect(formatNumber(1.5e-5, p)).toBe("< .001");
    expect(formatNumber(0.5, p)).toBe(".500");
    expect(formatNumber(0.001, p)).toBe(".001");
  });
  it("sem formato: valor como está; tipo integer arredonda", () => {
    expect(formatNumber(0.25, { name: "x" })).toBe("0.25");
    expect(formatNumber(59.6, { name: "n", type: "integer" })).toBe("60");
  });
  it("não finitos", () => {
    expect(formatNumber(NaN, t)).toBe("NaN");
    expect(formatNumber(Infinity, t)).toBe("∞");
    expect(formatNumber(-Infinity, t)).toBe("-∞");
  });
});

describe("formatCell", () => {
  it("vazio e texto passam sem alteração", () => {
    expect(formatCell(null, { name: "a" })).toBe("");
    expect(formatCell("Student", { name: "test" })).toBe("Student");
  });
});

describe("formatRaw / formatAxis", () => {
  it("dados brutos: nulos como traço, sem ruído de ponto flutuante", () => {
    expect(formatRaw(null)).toBe("—");
    expect(formatRaw(0.1 + 0.2)).toBe("0.3");
    expect(formatRaw(15.25)).toBe("15.25");
    expect(formatRaw(true)).toBe("true");
  });
  it("eixo: mesmo formato dos dados (ponto decimal) e compacto a partir de 10.000", () => {
    expect(formatAxis(1500, true)).toBe("1,500");
    expect(formatAxis(12500, true)).toBe("12.5K");
    expect(formatAxis(2_300_000, true)).toBe("2.3M");
    expect(formatAxis(12500, false)).toBe("12,500");
    expect(formatAxis(0.5, true)).toBe("0.5");
  });
});
