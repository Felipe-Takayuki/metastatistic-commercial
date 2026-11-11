import { describe, expect, it } from "vitest";
import { AVATAR_MAX_BYTES, avatarProblem, initials } from "./avatar";

describe("avatarProblem", () => {
  it("aceita os formatos suportados dentro do limite", () => {
    for (const type of ["image/png", "image/jpeg", "image/webp", "image/gif"]) expect(avatarProblem({ type, size: 1000 })).toBeNull();
    expect(avatarProblem({ type: "image/png", size: AVATAR_MAX_BYTES })).toBeNull();
  });
  it("recusa SVG e outros tipos (SVG pode carregar script)", () => {
    expect(avatarProblem({ type: "image/svg+xml", size: 100 })).toMatch(/PNG, JPEG, WebP ou GIF/);
    expect(avatarProblem({ type: "application/pdf", size: 100 })).not.toBeNull();
    expect(avatarProblem({ type: "", size: 100 })).not.toBeNull();
  });
  it("recusa vazio e acima do limite", () => {
    expect(avatarProblem({ type: "image/png", size: 0 })).toMatch(/vazio/);
    expect(avatarProblem({ type: "image/png", size: AVATAR_MAX_BYTES + 1 })).toMatch(/máximo é 2 MB/);
  });
});

describe("initials", () => {
  it("usa a primeira e a última palavra", () => {
    expect(initials("Maria da Silva")).toBe("MS");
    expect(initials("  ana  ")).toBe("A");
    expect(initials("josé")).toBe("J");
  });
  it("não quebra com nome vazio", () => expect(initials("   ")).toBe("?"));
});
