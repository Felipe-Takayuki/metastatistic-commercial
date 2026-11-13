/**
 * Gera os prints de evidência das atividades 10 e 11 (e o manifesto com data e hora de cada captura) contra a pilha no ar.
 *
 *   E2E_URL=http://127.0.0.1:8080 EVIDENCE_DIR=docs/evidencias node e2e/evidencias.mjs
 *
 * Os prints são capturas REAIS do navegador (Chromium headless). Cada um leva, no rodapé da própria página, o horário em
 * que foi tirado e a URL; o manifesto repete isso. Nada é editado depois. Requer um banco VAZIO (o script faz o primeiro
 * acesso: cria o administrador) e a pilha com AUTH_ENABLED=true e DATASETS_PRIVATE_BY_DEFAULT=true.
 * Com STRIPE_MOCK_MODE=true os eventos do Stripe são simulados por POSTs ao webhook (e o painel avisa "Stripe simulado").
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, session } from "./lib.mjs";

const OUT = process.env.EVIDENCE_DIR ?? "docs/evidencias";
mkdirSync(OUT, { recursive: true });
const manifest = [];
const CSV = "id,grupo,glicemia\n1,controle,92\n2,tratado,88\n3,controle,95\n4,tratado,85\n5,controle,99\n6,tratado,82\n";
const PASS = "senha-forte-1";

const stamp = () => new Date().toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "medium" });

async function shot(page, file, atividade, descricao) {
  const when = stamp();
  await page.evaluate(([text]) => {
    document.getElementById("__evidence")?.remove();
    const bar = document.createElement("div");
    bar.id = "__evidence";
    bar.textContent = text;
    bar.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#111;color:#fff;font:12px/1.4 monospace;padding:6px 12px;";
    document.body.appendChild(bar);
  }, [`Captura em ${when} (America/Sao_Paulo) · ${page.url()}`]);
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(OUT, file) });
  manifest.push({ arquivo: file, atividade, descricao, capturado_em: new Date().toISOString(), horario_local: when, url: page.url() });
  console.log(`  print ${file}  (${when})`);
}

async function call(ctx, method, path, { json, headers, multipart, expect } = {}) {
  const res = await ctx.request.fetch(`${BASE}${path}`, { method, data: json, headers, multipart });
  if (expect && res.status() !== expect) throw new Error(`${method} ${path} -> ${res.status()} ${await res.text()}`);
  return res;
}

const hook = (ctx, id, type, object) =>
  call(ctx, "POST", "/api/billing/webhook", { json: { id, type, data: { object } }, headers: { "Stripe-Signature": "t=1,v1=simulado" }, expect: 200 });

const s = await session();
const { browser } = s;
const newCtx = async () => browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: "light", locale: "pt-BR", timezoneId: "America/Sao_Paulo" });

// ---------------------------------------------------------------- Atividade 10
console.log("Atividade 10 — negócio no ar");
const anon = await newCtx();
const landing = await anon.newPage();
await landing.goto(BASE);
await landing.waitForSelector("text=Metastatistic");
await shot(landing, "10-01-landing-publica.png", 10, "Landing page pública, sem login");

const adminCtx = await newCtx();
await call(adminCtx, "POST", "/api/auth/setup", { json: { username: "admin", password: PASS, display_name: "Administrador" }, expect: 201 });
const adminMe = await (await call(adminCtx, "GET", "/api/auth/me")).json();

const camilaCtx = await newCtx();
await call(camilaCtx, "POST", "/api/auth/register", { json: { username: "camila", password: PASS, display_name: "Dra. Camila Valente" }, expect: 201 });
const camilaMe = await (await call(camilaCtx, "GET", "/api/auth/me")).json();

const rafaelCtx = await newCtx();
await call(rafaelCtx, "POST", "/api/auth/register", { json: { username: "rafael", password: PASS, display_name: "Rafael Souza" }, expect: 201 });

// organização Free da Camila e organização Pro do admin (assinada pelo webhook simulado)
const freeOrg = await (await call(camilaCtx, "POST", "/api/v1/tenants", { json: { name: "Laboratório de Glicemia", tier: "community", owner_id: camilaMe.id }, expect: 201 })).json();
const proOrg = await (await call(adminCtx, "POST", "/api/v1/tenants", { json: { name: "Centro Oncológico", tier: "community", owner_id: adminMe.id }, expect: 201 })).json();

const upload = (ctx, tenant, name) =>
  call(ctx, "POST", "/api/datasets", { headers: { "X-Tenant-ID": tenant }, multipart: { file: { name, mimeType: "text/csv", buffer: Buffer.from(CSV) } } });

// dados privados: a Camila sobe um dataset; o Rafael não o enxerga
await upload(camilaCtx, freeOrg.id, "ensaio_glicemia.csv");

const withTenant = async (ctx, tenant) => {
  await ctx.addInitScript(([t]) => localStorage.setItem("ms:active_tenant", JSON.stringify(t)), [tenant]);
};
await withTenant(camilaCtx, { id: freeOrg.id, name: freeOrg.name, slug: freeOrg.slug, tier: "community" });
const camilaPage = await camilaCtx.newPage();
await camilaPage.goto(BASE);
await camilaPage.waitForSelector("text=ensaio_glicemia");
await shot(camilaPage, "10-02-dados-do-usuario-camila.png", 10, "Camila (editora) vê o dataset que ela enviou");

const rafaelPage = await rafaelCtx.newPage();
await rafaelPage.goto(BASE);
await rafaelPage.waitForSelector("text=Comece com um conjunto de dados");
await shot(rafaelPage, "10-03-dados-isolados-rafael.png", 10, "Rafael, outro usuário, não vê o dataset da Camila (privado ao dono)");
const rafaelDirect = await call(rafaelCtx, "GET", "/api/datasets");
console.log("  rafael lista de datasets:", JSON.stringify(await rafaelDirect.json()));

// papéis e auditoria (eventos de negócio)
const adminPage = await adminCtx.newPage();
await adminPage.goto(`${BASE}/#/users`);
await adminPage.waitForSelector("text=camila");
await shot(adminPage, "10-04-papeis-usuarios.png", 10, "Administração de usuários e papéis (viewer, editor, admin)");
await adminPage.click("role=tab[name='Auditoria']");
await adminPage.waitForSelector("text=ensaio_glicemia");
await shot(adminPage, "10-05-eventos-de-negocio.png", 10, "Trilha de eventos de negócio: cadastros, logins e upload de dataset");

// ---------------------------------------------------------------- Atividade 11
console.log("Atividade 11 — SaaS com Stripe");
const pricing = await camilaCtx.newPage();
await pricing.goto(BASE);
await pricing.waitForSelector("text=ensaio_glicemia");
await pricing.click("button:has-text('Planos')");
await pricing.waitForSelector("[data-testid=plan-pro]");
await shot(pricing, "11-01-planos-free-pro.png", 11, "Tela de planos: Free (atual) e Pro, R$ 249,00/mês");
await pricing.keyboard.press("Escape");
await pricing.click("button:has-text('Fechar')").catch(() => {});

// estourando o limite do Free (5 datasets): quatro por API (já há um) e o sexto pela interface
for (let i = 2; i <= 5; i++) await upload(camilaCtx, freeOrg.id, `ensaio_${i}.csv`);
await pricing.reload();
await pricing.waitForSelector("text=ensaio_glicemia");
await pricing.setInputFiles("input[type=file]", { name: "ensaio_6.csv", mimeType: "text/csv", buffer: Buffer.from(CSV) });
await pricing.waitForSelector("text=Limite do plano Free");
await shot(pricing, "11-02-limite-do-plano-na-api.png", 11, "Sexto dataset barrado pela API (402) com o limite e como liberar");

// assinatura Pro pelo webhook (simulado) e a mesma ação passando
const checkout = await (await call(adminCtx, "POST", "/api/billing/checkout", { headers: { "X-Tenant-ID": proOrg.id }, json: { plan_id: "pro", billing_cycle: "monthly" }, expect: 200 })).json();
console.log("  checkout:", checkout.session_id, checkout.url);
await hook(adminCtx, "evt_demo_checkout", "checkout.session.completed", { client_reference_id: proOrg.id, customer: "cus_demo_1", subscription: "sub_demo_1", metadata: { tenant_id: proOrg.id, plan_id: "pro" } });
const dup = await (await hook(adminCtx, "evt_demo_checkout", "checkout.session.completed", { client_reference_id: proOrg.id, customer: "cus_demo_1", subscription: "sub_demo_1", metadata: { tenant_id: proOrg.id, plan_id: "pro" } })).json();
console.log("  reentrega do mesmo evento:", JSON.stringify(dup));

// segunda organização Pro que depois falha o pagamento
const clinic = await (await call(rafaelCtx, "POST", "/api/v1/tenants", { json: { name: "Clínica Aurora", tier: "community", owner_id: (await (await call(rafaelCtx, "GET", "/api/auth/me")).json()).id }, expect: 201 })).json();
await hook(adminCtx, "evt_demo_checkout_2", "checkout.session.completed", { client_reference_id: clinic.id, customer: "cus_demo_2", subscription: "sub_demo_2", metadata: { tenant_id: clinic.id, plan_id: "pro" } });
await hook(adminCtx, "evt_demo_failed_2", "invoice.payment_failed", { id: "in_demo_2", customer: "cus_demo_2", subscription: "sub_demo_2", amount_due: 24900, amount_paid: 0, currency: "brl" });
await hook(adminCtx, "evt_demo_updated_1", "customer.subscription.updated", { id: "sub_demo_1", customer: "cus_demo_1", status: "active", cancel_at_period_end: false });

await withTenant(adminCtx, { id: proOrg.id, name: proOrg.name, slug: proOrg.slug, tier: "team" });
const adminPricing = await adminCtx.newPage();
await adminPricing.goto(BASE);
await adminPricing.click("button:has-text('Planos')");
await adminPricing.waitForSelector("[data-testid=current-plan]");
await shot(adminPricing, "11-03-plano-pro-ativo.png", 11, "Organização com o Pro ativo: botão Gerenciar assinatura (portal do cliente)");

const adminPanel = await adminCtx.newPage();
await adminPanel.goto(`${BASE}/#/admin`);
await adminPanel.waitForSelector("[data-testid=events]");
await adminPanel.waitForSelector("text=Pagamento falhou");
await shot(adminPanel, "11-04-painel-admin.png", 11, "Painel admin: usuários por plano, assinaturas ativas, MRR de teste e últimos eventos");

const forbidden = await call(camilaCtx, "GET", "/api/billing/admin/summary");
console.log("  camila (não admin) no painel:", forbidden.status());

writeFileSync(join(OUT, "manifesto.json"), JSON.stringify({ gerado_em: new Date().toISOString(), base: BASE, prints: manifest }, null, 2));
await browser.close();
console.log(`\n${manifest.length} prints em ${OUT}`);
