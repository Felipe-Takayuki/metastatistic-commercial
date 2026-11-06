/**
 * E2E de autenticação e papéis. Exige uma pilha NOVA (sem usuários) com AUTH_ENABLED=true — por isso não faz
 * parte do `e2e:all`, que roda contra a pilha sem autenticação:
 *   AUTH_ENABLED=true DATA_DIR=$(mktemp -d) uvicorn app.main:app --port 8010      (em apps/api)
 *   API_URL=http://127.0.0.1:8010 npm run dev &                                    (em apps/web, porta 5173)
 *   E2E_URL=http://127.0.0.1:5173 npm run e2e:auth
 */
import { BASE, session } from "./lib.mjs";

const s = await session({ allowConsole: { "status of 401": 10, "status of 403": 3, "status of 422": 1 } });
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
  const admin = await (await s.browser.newContext()).newPage();
  admin.on("dialog", (d) => d.accept()); // confirmações do administrador (a página dele não passa pelo monitor de diálogos)
  await admin.goto(BASE);
  await fillLogin(admin, "e2eadmin", PASS);
  await admin.getByRole("link", { name: "Usuários" }).click();
  await admin.locator('tr[data-user="e2eeditor"]').getByRole("button", { name: "Desativar" }).click();
  await admin.locator('tr[data-user="e2eeditor"]', { hasText: "Desativado" }).waitFor();
  await page.goto(`${BASE}/#/reports`); // dispara requisições; a API responde 401
  await page.getByRole("heading", { name: "Entrar" }).waitFor();
  check("usuário desativado cai na tela de login na próxima requisição", true);
  await fillLogin(page, "e2eeditor", PASS);
  await page.getByRole("alert").waitFor();
  check("usuário desativado não consegue entrar", (await page.getByRole("alert").innerText()).includes("invalid username or password"));

  // --- limpeza: o relatório criado pelo editor e os usuários ---
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
} finally {
  await s.finish();
}
