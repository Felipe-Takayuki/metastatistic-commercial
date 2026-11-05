import pytest

BLOCKS = [
    {"type": "text", "id": "t1", "markdown": "# Vendas\n\nResumo **executivo**."},
    {"type": "chart", "id": "c1", "title": "Receita por região", "sql": "SELECT 1 AS a",
     "chart": {"type": "bar", "x": "regiao", "ys": ["receita"], "slots": {"receita": 0}}},
    {"type": "analysis", "id": "a1", "analysis": "TTestIndependentSamples", "dataset_id": "0" * 32,
     "options": {"dependent": ["receita"], "group": "grupo", "student": True}},
]


async def create(client, title="Relatório", blocks=None):
    r = await client.post("/reports", json={"title": title, "blocks": BLOCKS if blocks is None else blocks})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_get_roundtrip_preserves_blocks_exactly(client):
    rep = await create(client)
    assert rep["version"] == 1 and len(rep["id"]) == 32
    got = (await client.get(f"/reports/{rep['id']}")).json()
    assert got["blocks"] == BLOCKS  # nada é perdido ou reordenado na ida e volta (ordem importa num documento)
    assert got["title"] == "Relatório"


async def test_list_is_a_summary_without_blocks(client):
    a = await create(client, "A")
    await create(client, "B", blocks=[])
    rows = (await client.get("/reports")).json()
    assert {r["title"] for r in rows} == {"A", "B"}
    assert all("blocks" not in r for r in rows)
    assert {r["id"]: r["n_blocks"] for r in rows}[a["id"]] == 3


async def test_update_replaces_content_and_bumps_version(client):
    rep = await create(client)
    new_blocks = [BLOCKS[2], BLOCKS[0]]  # reordenado e com um bloco a menos
    r = await client.put(f"/reports/{rep['id']}", json={"title": "  Novo título  ", "blocks": new_blocks, "version": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["title"] == "Novo título"  # título é aparado
    assert [b["id"] for b in body["blocks"]] == ["a1", "t1"]


async def test_stale_version_is_409_and_does_not_overwrite(client):
    """Duas abas abrem a v1; a primeira salva; a segunda NÃO pode sobrescrever em silêncio."""
    rep = await create(client)
    tab_a = await client.put(f"/reports/{rep['id']}", json={"title": "da aba A", "blocks": [], "version": 1})
    assert tab_a.status_code == 200
    tab_b = await client.put(f"/reports/{rep['id']}", json={"title": "da aba B", "blocks": [], "version": 1})
    assert tab_b.status_code == 409 and "changed elsewhere" in tab_b.json()["detail"]
    assert (await client.get(f"/reports/{rep['id']}")).json()["title"] == "da aba A"  # a edição da aba A sobreviveu
    # com a versão atual, a aba B consegue salvar
    assert (await client.put(f"/reports/{rep['id']}", json={"title": "da aba B", "blocks": [], "version": 2})).status_code == 200


async def test_unknown_report_is_404(client):
    missing = "f" * 32
    assert (await client.get(f"/reports/{missing}")).status_code == 404
    assert (await client.put(f"/reports/{missing}", json={"title": "x", "blocks": [], "version": 1})).status_code == 404
    assert (await client.delete(f"/reports/{missing}")).status_code == 404


async def test_delete(client):
    rep = await create(client)
    assert (await client.delete(f"/reports/{rep['id']}")).status_code == 204
    assert (await client.get(f"/reports/{rep['id']}")).status_code == 404
    assert (await client.get("/reports")).json() == []


@pytest.mark.parametrize("payload,why", [
    ({"title": "", "blocks": []}, "título vazio"),
    ({"title": "   ", "blocks": []}, "título só com espaços"),
    ({"title": "x", "blocks": [{"type": "video", "id": "v1"}]}, "tipo de bloco desconhecido"),
    ({"title": "x", "blocks": [{"type": "text", "id": "a b", "markdown": ""}]}, "id com espaço"),
    ({"title": "x", "blocks": [{"type": "text", "id": "../x", "markdown": ""}]}, "id com caracteres de caminho"),
    ({"title": "x", "blocks": [{"type": "text", "id": "d", "markdown": ""}, {"type": "text", "id": "d", "markdown": ""}]}, "ids duplicados"),
    ({"title": "x", "blocks": [{"type": "text", "id": f"t{i}", "markdown": ""} for i in range(101)]}, "mais de 100 blocos"),
    ({"title": "x", "blocks": [{"type": "text", "id": "t", "markdown": "a" * 50_001}]}, "markdown gigante"),
    ({"title": "x", "blocks": [{"type": "chart", "id": "c", "chart": {"type": "pizza", "x": "a", "ys": []}}]}, "tipo de gráfico inválido"),
    ({"title": "x", "blocks": [{"type": "chart", "id": "c", "chart": {"type": "line", "x": "a", "ys": ["1", "2", "3", "4"]}}]}, "mais de 3 séries"),
    ({"title": "x" * 201, "blocks": []}, "título gigante"),
])
async def test_invalid_reports_are_rejected(client, payload, why):
    r = await client.post("/reports", json=payload)
    assert r.status_code == 422, why
    assert (await client.get("/reports")).json() == []  # nada foi gravado


async def test_invalid_update_does_not_change_report(client):
    rep = await create(client)
    r = await client.put(f"/reports/{rep['id']}", json={"title": "ok", "blocks": [{"type": "video", "id": "v"}], "version": 1})
    assert r.status_code == 422
    got = (await client.get(f"/reports/{rep['id']}")).json()
    assert got["version"] == 1 and got["blocks"] == BLOCKS


async def test_unicode_and_markup_in_content_roundtrip_untouched(client):
    """O servidor guarda como dado; quem renderiza é responsável por escapar (testado no front)."""
    weird = [{"type": "text", "id": "t", "markdown": '<script>alert(1)</script> ação — 日本語 "aspas" \\ barra'}]
    rep = await create(client, "Ação <b>ótima</b>", blocks=weird)
    got = (await client.get(f"/reports/{rep['id']}")).json()
    assert got["blocks"] == weird and got["title"] == "Ação <b>ótima</b>"


async def test_missing_version_on_update_is_422(client):
    rep = await create(client)
    assert (await client.put(f"/reports/{rep['id']}", json={"title": "x", "blocks": []})).status_code == 422
