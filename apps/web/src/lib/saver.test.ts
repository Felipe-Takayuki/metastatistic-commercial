import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Saver, type SaveStatus } from "./saver";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const deferred = () => {
  let resolve!: () => void, reject!: (e: unknown) => void;
  const promise = new Promise<void>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const setup = (save: (p: string) => Promise<void>, classify: (e: unknown) => "retry" | "conflict" = () => "retry") => {
  const statuses: SaveStatus[] = [];
  const saver = new Saver<string>(save, (s) => statuses.push(s), classify, 800);
  return { saver, statuses };
};

describe("Saver", () => {
  it("várias edições dentro do intervalo viram um salvamento com o conteúdo mais recente", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { saver, statuses } = setup(save);
    saver.schedule("a"); saver.schedule("ab"); saver.schedule("abc");
    await vi.advanceTimersByTimeAsync(799);
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
    expect(statuses.at(-1)).toBe("saved");
    expect(saver.hasUnsaved).toBe(false);
  });

  it("edição feita DURANTE um salvamento não se perde e os salvamentos não se sobrepõem", async () => {
    const first = deferred();
    const calls: string[] = [];
    let concurrent = 0, maxConcurrent = 0;
    const save = vi.fn(async (p: string) => {
      calls.push(p);
      maxConcurrent = Math.max(maxConcurrent, ++concurrent);
      if (p === "v1") await first.promise;
      concurrent--;
    });
    const { saver, statuses } = setup(save);
    saver.schedule("v1");
    await vi.advanceTimersByTimeAsync(800);          // começa a salvar v1 (pendente)
    expect(saver.hasUnsaved).toBe(true);
    saver.schedule("v2"); saver.schedule("v3");      // usuário continua digitando
    await vi.advanceTimersByTimeAsync(800);          // o timer dispara, mas v1 ainda está em andamento
    expect(calls).toEqual(["v1"]);
    first.resolve();
    await vi.advanceTimersByTimeAsync(0);
    expect(calls).toEqual(["v1", "v3"]);             // v2 foi coalescido; v3 (o mais novo) foi salvo
    expect(maxConcurrent).toBe(1);
    expect(statuses.at(-1)).toBe("saved");
    expect(saver.hasUnsaved).toBe(false);
  });

  it("falha comum mantém o conteúdo e flush() tenta de novo", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("rede caiu")).mockResolvedValue(undefined);
    const { saver, statuses } = setup(save);
    saver.schedule("x");
    await vi.advanceTimersByTimeAsync(800);
    expect(statuses.at(-1)).toBe("error");
    expect(saver.hasUnsaved).toBe(true);             // nada foi descartado
    await saver.flush();
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith("x");
    expect(statuses.at(-1)).toBe("saved");
  });

  it("falha + edição mais nova: a nova tentativa usa a edição mais nova, nunca a velha", async () => {
    const first = deferred();
    const save = vi.fn(async (p: string) => { if (p === "velho") await first.promise; });
    const { saver, statuses } = setup(save);
    saver.schedule("velho");
    await vi.advanceTimersByTimeAsync(800);          // salvando "velho"
    saver.schedule("novo");                          // usuário edita durante o salvamento
    first.reject(new Error("falhou"));
    await vi.advanceTimersByTimeAsync(0);
    expect(statuses.at(-1)).toBe("error");           // erro é exibido; não fica insistindo sozinho
    expect(saver.hasUnsaved).toBe(true);
    await saver.flush();                             // "tentar de novo"
    expect(save.mock.calls.map((c) => c[0])).toEqual(["velho", "novo"]); // "velho" nunca é reenviado
    expect(statuses.at(-1)).toBe("saved");
  });

  it("conflito PARA tudo: nada mais é enviado, mesmo com novas edições e flush()", async () => {
    const save = vi.fn().mockRejectedValue(new Error("changed elsewhere"));
    const { saver, statuses } = setup(save, () => "conflict");
    saver.schedule("minha edição");
    await vi.advanceTimersByTimeAsync(800);
    expect(statuses.at(-1)).toBe("conflict");
    saver.schedule("mais uma");
    await vi.advanceTimersByTimeAsync(5000);
    await saver.flush();
    expect(save).toHaveBeenCalledTimes(1);           // nunca sobrescreve o trabalho da outra aba
    expect(statuses.at(-1)).toBe("conflict");
  });

  it("flush() sem nada pendente não chama a API; com pendente salva imediatamente (sair da página)", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { saver } = setup(save);
    await saver.flush();
    expect(save).not.toHaveBeenCalled();
    saver.schedule("final");
    await saver.flush();                              // sem esperar o debounce
    expect(save).toHaveBeenCalledWith("final");
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).toHaveBeenCalledTimes(1);            // o timer antigo foi cancelado, sem salvar em duplicidade
  });

  it("flush() chamado durante um salvamento espera esse salvamento terminar", async () => {
    const gate = deferred();
    const save = vi.fn(() => gate.promise);
    const { saver } = setup(save);
    saver.schedule("a");
    await vi.advanceTimersByTimeAsync(800);
    let done = false;
    const p = saver.flush().then(() => { done = true; });
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(false);
    gate.resolve();
    await p;
    expect(done).toBe(true);
    expect(save).toHaveBeenCalledTimes(1);
  });
});
