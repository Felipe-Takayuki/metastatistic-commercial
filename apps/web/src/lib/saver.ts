export type SaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";
export type FailureKind = "retry" | "conflict";

/**
 * Autosave com debounce. Garantias:
 *  - várias edições dentro do intervalo viram UM salvamento, com o conteúdo mais recente;
 *  - salvamentos nunca se sobrepõem (cada um usa a versão que o anterior devolveu);
 *  - edição feita DURANTE um salvamento não se perde: é salva em seguida;
 *  - falha comum mantém o conteúdo pendente para nova tentativa; conflito (outra aba salvou) PARA tudo,
 *    para nunca sobrescrever o trabalho alheio em silêncio.
 */
export class Saver<P> {
  private pending: P | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running: Promise<void> | null = null;
  private stopped = false;

  constructor(
    private save: (payload: P) => Promise<void>,
    private onStatus: (status: SaveStatus, message?: string) => void,
    private classify: (error: unknown) => FailureKind,
    private delayMs = 800,
  ) {}

  schedule(payload: P): void {
    if (this.stopped) return;
    this.pending = payload;
    this.onStatus("dirty");
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.flush(), this.delayMs);
  }

  /** Salva já (ao sair da página, ou "tentar de novo"). Resolve quando não há mais nada pendente. */
  flush(): Promise<void> {
    clearTimeout(this.timer);
    if (this.running) return this.running; // o laço em andamento pega o que estiver pendente
    if (this.pending === undefined || this.stopped) return Promise.resolve();
    this.running = this.loop().finally(() => { this.running = null; });
    return this.running;
  }

  get hasUnsaved(): boolean {
    return this.pending !== undefined || this.running !== null;
  }

  private async loop(): Promise<void> {
    while (this.pending !== undefined && !this.stopped) {
      const payload = this.pending;
      this.pending = undefined;
      this.onStatus("saving");
      try {
        await this.save(payload);
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        if (this.classify(e) === "conflict") {
          this.stopped = true;
          this.onStatus("conflict", message);
          return;
        }
        if (this.pending === undefined) this.pending = payload; // mantém para tentar de novo (a menos que haja edição mais nova)
        this.onStatus("error", message);
        return;
      }
    }
    if (this.pending === undefined) this.onStatus("saved");
  }
}
