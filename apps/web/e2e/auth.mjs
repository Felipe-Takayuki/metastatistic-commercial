/**
 * E2E de autenticação e papéis. Exige uma pilha NOVA (sem usuários) com AUTH_ENABLED=true — por isso não faz
 * parte do `e2e:all`, que roda contra a pilha sem autenticação:
 *   AUTH_ENABLED=true DATA_DIR=$(mktemp -d) uvicorn app.main:app --port 8010      (em apps/api)
 *   API_URL=http://127.0.0.1:8010 npm run dev &                                    (em apps/web, porta 5173)
 *   E2E_URL=http://127.0.0.1:5173 npm run e2e:auth
 */
import { BASE, session } from "./lib.mjs";

const s = await session({ allowConsole: { "status of 401": 10, "status of 403": 3, "status of 422": 1, "status of 404": 2 } });
const { page, check, shot } = s;
const PASS = "senha-forte-1";

const fillLogin = async (p, user, pass) => {
  await p.getByLabel("Usuário", { exact: true }).fill(user);
  await p.getByLabel("Senha", { exact: true }).fill(pass);
  await p.getByRole("button", { name: "Entrar" }).click();
};
const logout = async () => { await page.getByRole("button", { name: "Sair" }).click(); await page.getByRole("heading", { name: "Entrar" }).waitFor(); };
const loginAs = async (user, pass = PASS) => { await fillLogin(page, user, pass); await page.locator(".topbar").waitFor(); };
const has = async (loc) => (await loc.count()) > 0;

try {
  // --- primeiro acesso ---
  await page.goto(BASE);
  await page.getByRole("heading", { name: "Criar o administrador" }).waitFor();
  check("sem usuários: pede para criar o administrador (e não mostra o app)", !(await has(page.locator(".topbar"))));
  await page.getByLabel("Usuário", { exact: true }).fill("e2eadmin");
  await page.getByLabel("Senha", { exact: true }).fill(PASS);
  await page.getByLabel("Repita a senha").fill("outra-senha-9");
  await page.getByRole("button", { name: "Criar e entrar" }).click();
  check("senhas diferentes: recusa com aviso", (await page.getByRole("alert").innerText()).includes("não são iguais"));
  await page.getByLabel("Repita a senha").fill(PASS);
  await page.getByRole("button", { name: "Criar e entrar" }).click();
  await page.locator(".topbar").waitFor();
  check("administrador criado já entra no app", (await page.locator(".user-chip").innerText()).includes("Administrador"));
  check("administrador vê o link Usuários", await has(page.getByRole("link", { name: "Usuários" })));
  await shot("auth-admin");

  // --- gestão de usuários ---
  await page.getByRole("link", { name: "Usuários" }).click();
  await page.getByRole("heading", { name: "Usuários" }).waitFor();
  const create = async (name, role) => {
    const form = page.locator("form.new-user");
    await form.getByLabel("Usuário", { exact: true }).fill(name);
    await form.getByLabel("Senha inicial").fill(PASS);
    await form.getByLabel("Papel").selectOption(role);
    await form.getByRole("button", { name: "Criar usuário" }).click();
    await page.locator(`tr[data-user="${name}"]`).waitFor();
  };
  await create("e2eeditor", "editor");
  await create("e2eleitor", "viewer");
  await create("e2eeditor2", "editor");
  check("4 usuários listados", (await page.locator(".users-table tbody tr").count()) === 4);
  await page.getByLabel("Papel de e2eadmin").selectOption("viewer");
  await page.getByRole("alert").waitFor();
  check("não deixa rebaixar o último administrador", (await page.getByRole("alert").innerText()).includes("last active administrator"));
  check("o papel do último administrador continua Administrador", (await page.getByLabel("Papel de e2eadmin").inputValue()) === "admin");

  // --- sair e entrar ---
  await logout();
  await fillLogin(page, "e2eadmin", "senha-errada-9");
  await page.getByRole("alert").waitFor();
  check("senha errada: mensagem genérica, continua na tela de login", (await page.getByRole("alert").innerText()).includes("invalid username or password"));

  // --- leitor: só leitura ---
  await loginAs("e2eleitor");
  check("leitor não vê o link Usuários", !(await has(page.getByRole("link", { name: "Usuários" }))));
  check("leitor não vê a área de envio de CSV", !(await has(page.locator(".dropzone"))));
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("heading", { name: "Relatórios" }).waitFor();
  check("leitor não vê 'Novo relatório'", !(await has(page.getByRole("button", { name: "Novo relatório" }))));
  await page.getByRole("link", { name: "Dashboards" }).click();
  await page.getByRole("heading", { name: "Dashboards" }).waitFor();
  check("leitor não vê 'Novo dashboard'", !(await has(page.getByRole("button", { name: "Novo dashboard" }))));
  await page.goto(`${BASE}/#/users`);
  await page.getByRole("heading", { name: "Sem permissão" }).waitFor();
  check("leitor em #/users: 'Sem permissão'", true);
  const forbidden = await page.evaluate(async () => (await fetch("/api/reports", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "x", blocks: [] }) })).status);
  check("e a API recusa a escrita do leitor (403)", forbidden === 403, String(forbidden));
  await shot("auth-viewer");
  await logout();

  // --- editor: cria conteúdo, mas não gerencia usuários ---
  await loginAs("e2eeditor");
  await page.goto(`${BASE}/#/`);
  await page.locator(".sidebar").waitFor();
  check("editor vê a área de envio de CSV", await has(page.locator(".dropzone")));
  check("editor não vê o link Usuários", !(await has(page.getByRole("link", { name: "Usuários" }))));
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("button", { name: "Novo relatório" }).click();
  await page.waitForURL(/#\/reports\/[0-9a-f]{32}/);
  const reportId = page.url().match(/#\/reports\/([0-9a-f]{32})/)[1];
  check("editor cria um relatório", !!reportId);

  // --- coleções: o editor cria uma e move o relatório para ela ---
  await page.goto(`${BASE}/#/reports`);
  await page.getByRole("button", { name: "+ Nova coleção" }).waitFor();
  s.onNextDialog((d) => d.accept("E2E Coleção"));
  await page.getByRole("button", { name: "+ Nova coleção" }).click();
  await page.locator(".coll-chip", { hasText: "E2E Coleção" }).waitFor();
  check("coleção criada já fica selecionada (e vazia)", (await page.locator(".coll-chip[aria-pressed=true]").innerText()).includes("E2E Coleção") && (await page.getByText("Nenhum relatório nesta coleção.").count()) === 1);
  await page.locator(".coll-chip", { hasText: "Todos" }).click();
  await page.locator(".report-row").first().getByLabel(/^Coleção de/).selectOption({ label: "E2E Coleção" });
  await page.locator(".coll-chip", { hasText: "E2E Coleção" }).filter({ hasText: "1" }).waitFor();
  await page.locator(".coll-chip", { hasText: "Sem coleção" }).click();
  await page.getByText("Nenhum relatório nesta coleção.").waitFor();
  check("filtro 'Sem coleção' não mostra o relatório movido", (await page.locator(".report-row").count()) === 0);
  await page.locator(".coll-chip", { hasText: "E2E Coleção" }).click();
  check("filtro da coleção mostra o relatório", (await page.locator(".report-row").count()) === 1);
  await shot("auth-collections");

  // --- dataset: acesso restrito + filtro de linhas por atributo ---
  const admin = await (await s.browser.newContext()).newPage();
  let adminPrompt = "";
  admin.on("dialog", (d) => (d.type() === "prompt" ? d.accept(adminPrompt) : d.accept())); // a página do administrador não passa pelo monitor de diálogos
  await admin.goto(BASE);
  await fillLogin(admin, "e2eadmin", PASS);
  await admin.getByRole("link", { name: "Usuários" }).waitFor();

  await page.goto(`${BASE}/#/`);
  await page.locator(".sidebar").waitFor();
  const csv = "id,regiao,valor\n1,Sul,10\n2,Sul,20\n3,Norte,30\n4,Leste,40\n5,Norte,50\n";
  const uploaded = page.waitForResponse((r) => r.url().endsWith("/api/datasets") && r.request().method() === "POST");
  await page.locator(".dropzone input[type=file]").setInputFiles({ name: "e2e_regioes.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  const dsId = (await (await uploaded).json()).id;
  await page.getByRole("heading", { name: "e2e_regioes.csv" }).waitFor();
  await page.getByRole("button", { name: "Acesso…" }).click();
  const dlg = page.getByRole("dialog", { name: /^Acesso a/ });
  await dlg.getByLabel("Restringir a leitura").check();
  await dlg.getByRole("group", { name: "Quem pode ler" }).getByLabel(/e2eeditor2/).check();
  await dlg.getByLabel("Filtrar linhas por atributo do usuário").check();
  await dlg.locator("select").selectOption("regiao");
  await dlg.getByPlaceholder("ex.: regiao").fill("regiao");
  await dlg.getByRole("button", { name: "Salvar" }).click();
  await dlg.waitFor({ state: "detached" });
  check("dono vê o chip 'acesso restrito' e todas as linhas dele", (await has(page.getByText("acesso restrito"))) && !(await has(page.getByText("linhas filtradas para você"))));
  await shot("auth-access");

  // o administrador dá ao outro editor o atributo regiao=Sul
  await admin.getByRole("link", { name: "Usuários" }).click();
  await admin.locator('tr[data-user="e2eeditor2"]').waitFor();
  adminPrompt = "regiao=Sul";
  await admin.getByRole("button", { name: "Atributos de e2eeditor2" }).click();
  await admin.locator('tr[data-user="e2eeditor2"]', { hasText: "regiao=Sul" }).waitFor();
  check("administrador define o atributo regiao=Sul do usuário", true);
  await logout();

  // quem está na lista e tem o atributo: só as linhas do Sul
  await loginAs("e2eeditor2");
  await page.goto(`${BASE}/#/`);
  await page.locator(".ds-item", { hasText: "e2e_regioes.csv" }).click();
  await page.getByText("linhas filtradas para você").waitFor();
  const seen = (await page.locator("table").first().innerText());
  check("usuário com atributo vê só as linhas do Sul na tabela", seen.includes("Sul") && !seen.includes("Norte") && !seen.includes("Leste"), seen);
  const cnt = await page.evaluate(async () => (await (await fetch("/api/queries/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sql: 'SELECT COUNT(*) FROM "e2e_regioes"' }) })).json()).rows[0][0]);
  check("e o SQL dele também conta só 2 linhas (de 5)", cnt === 2, String(cnt));
  check("quem só lê com acesso não vê o botão 'Acesso…' (não é dono)", !(await has(page.getByRole("button", { name: "Acesso…" }))));
  await logout();

  // quem NÃO está na lista: o dataset some (lista, API e SQL)
  await loginAs("e2eleitor");
  await page.goto(`${BASE}/#/`);
  await page.locator(".sidebar").waitFor();
  check("leitor fora da lista não vê o dataset restrito na barra lateral", !(await has(page.locator(".ds-item", { hasText: "e2e_regioes.csv" }))));
  const status = await page.evaluate(async (id) => (await fetch(`/api/datasets/${id}`)).status, dsId);
  check("e a API responde 404 para ele (nem confirma que existe)", status === 404, String(status));
  await logout();

  // --- outro editor: vê, mas não altera o que é do primeiro ---
  await loginAs("e2eeditor2");
  await page.goto(`${BASE}/#/reports`);
  await page.locator(".report-row").first().waitFor();
  const row = page.locator(".report-row").first();
  check("outro editor vê o relatório com o nome do dono", (await row.innerText()).includes("por e2eeditor"));
  check("outro editor não vê Excluir nem 'Coleção de'", !(await has(row.getByRole("button", { name: /^Excluir/ }))) && !(await has(row.getByLabel(/^Coleção de/))));
  await page.locator(".coll-chip", { hasText: "E2E Coleção" }).click();
  check("outro editor não renomeia nem exclui a coleção alheia", !(await has(page.getByRole("button", { name: "Renomear" }))) && !(await has(page.getByRole("button", { name: "Excluir coleção" }))));
  await row.getByRole("link").click();
  await page.locator(".report-toolbar").waitFor();
  check("outro editor não vê o botão Editar do relatório alheio", !(await has(page.getByRole("button", { name: "Editar", exact: true }))));
  const putStatus = await page.evaluate(async (id) => (await fetch(`/api/reports/${id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "x", blocks: [], version: 1 }) })).status, reportId);
  check("e a API recusa o PUT do outro editor (403)", putStatus === 403, String(putStatus));
  await logout();
  await loginAs("e2eeditor");

  // --- sessão derrubada pelo administrador enquanto o editor está com a página aberta ---
  await admin.getByRole("link", { name: "Usuários" }).click();
  await admin.locator('tr[data-user="e2eeditor"]').getByRole("button", { name: "Desativar" }).click();
  await admin.locator('tr[data-user="e2eeditor"]', { hasText: "Desativado" }).waitFor();
  await page.goto(`${BASE}/#/reports`); // dispara requisições; a API responde 401
  await page.getByRole("heading", { name: "Entrar" }).waitFor();
  check("usuário desativado cai na tela de login na próxima requisição", true);
  await fillLogin(page, "e2eeditor", PASS);
  await page.getByRole("alert").waitFor();
  check("usuário desativado não consegue entrar", (await page.getByRole("alert").innerText()).includes("invalid username or password"));

  // --- auditoria: o administrador vê o que aconteceu ---
  await admin.goto(`${BASE}/#/users`);
  await admin.getByRole("tab", { name: "Auditoria" }).click();
  await admin.locator('tr[data-action="set_access"]').first().waitFor();
  const alerts = await admin.locator("tr.audit-alert").count();
  check("auditoria registra a mudança de acesso, o login falho e o acesso negado (estes destacados)",
    (await has(admin.locator('tr[data-action="set_access"]'))) && (await has(admin.locator('tr[data-action="login_failed"]'))) && (await has(admin.locator('tr[data-action="denied"]'))) && alerts >= 2);
  const auditText = await admin.locator(".audit-table").innerText();
  check("auditoria nunca mostra senhas", !auditText.includes(PASS) && !auditText.includes("senha-errada"));
  await admin.getByLabel("Filtrar por ação").selectOption("denied");
  await admin.waitForFunction(() => [...document.querySelectorAll(".audit-table tbody tr")].every((r) => r.getAttribute("data-action") === "denied"));
  check("filtro por ação mostra só 'Acesso negado'", (await admin.locator(".audit-table tbody tr").count()) > 0);
  await shot("auth-audit", admin);

  // --- limpeza: o dataset e o relatório criados pelos editores ---
  const delDs = await admin.evaluate(async (id) => (await fetch(`/api/datasets/${id}`, { method: "DELETE" })).status, dsId);
  check("limpeza do dataset de teste", delDs === 204, String(delDs));
  await admin.goto(`${BASE}/#/reports`);
  const arow = admin.locator(".report-row").first();
  await arow.waitFor();
  check("administrador altera o que é de outro (vê Excluir e mover)", (await has(arow.getByRole("button", { name: /^Excluir/ }))) && (await has(arow.getByLabel(/^Coleção de/))));
  await admin.locator(".coll-chip", { hasText: "E2E Coleção" }).click();
  check("administrador renomeia/exclui a coleção de outro", (await has(admin.getByRole("button", { name: "Renomear" }))) && (await has(admin.getByRole("button", { name: "Excluir coleção" }))));
  await admin.getByRole("button", { name: "Excluir coleção" }).click();
  await admin.locator(".coll-chip", { hasText: "E2E Coleção" }).waitFor({ state: "detached" });
  check("excluir a coleção devolve o relatório à raiz (não o apaga)", (await admin.locator(".report-row").count()) === 1);
  const del = await admin.evaluate(async (id) => (await fetch(`/api/reports/${id}`, { method: "DELETE" })).status, reportId);
  check("limpeza do relatório de teste", del === 204, String(del));
} catch (e) {
  s.check(`exceção no teste: ${String(e?.message ?? e).split("\n")[0]}`, false); // sem isto o finish() sairia com sucesso e esconderia o erro
  console.error(e);
} finally {
  await s.finish();
}
