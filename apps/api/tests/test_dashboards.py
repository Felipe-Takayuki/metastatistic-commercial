import pytest

L = lambda x, y, w=4, h=3: {"x": x, "y": y, "w": w, "h": h}  # noqa: E731
TILES = [
    {"type": "kpi", "id": "k1", "title": "Receita", "sql": "SELECT 1 AS a", "decimals": 2, "prefix": "R$ ", "suffix": "", "layout": L(0, 0, 3, 2)},
    {"type": "chart", "id": "c1", "title": "Por região", "sql": "SELECT 1 AS a",
     "chart": {"type": "bar", "x": "regiao", "ys": ["receita"], "slots": {"receita": 0}}, "layout": L(3, 0, 9, 4)},
    {"type": "text", "id": "t1", "markdown": "## Notas\n\nTexto.", "layout": L(0, 4, 12, 2)},
]


async def create(client, title="Painel", tiles=None):
    r = await client.post("/dashboards", json={"title": title, "tiles": TILES if tiles is None else tiles})
    assert r.status_code == 201, r.text
    return r.json()


async def test_roundtrip_preserves_tiles_and_layout_exactly(client):
    d = await create(client)
    assert d["version"] == 1 and len(d["id"]) == 32
    got = (await client.get(f"/dashboards/{d['id']}")).json()
    assert got["tiles"] == TILES


async def test_list_is_a_summary_without_tiles(client):
    a = await create(client, "A")
    await create(client, "B", tiles=[])
    rows = (await client.get("/dashboards")).json()
    assert {r["title"] for r in rows} == {"A", "B"} and all("tiles" not in r for r in rows)
    assert {r["id"]: r["n_tiles"] for r in rows}[a["id"]] == 3


async def test_update_moves_a_tile_and_bumps_version(client):
    d = await create(client)
    moved = [{**TILES[0], "layout": L(9, 7, 3, 2)}, *TILES[1:]]
    r = await client.put(f"/dashboards/{d['id']}", json={"title": " Novo ", "tiles": moved, "version": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["title"] == "Novo" and body["tiles"][0]["layout"] == L(9, 7, 3, 2)


async def test_stale_version_is_409_and_does_not_overwrite(client):
    d = await create(client)
    assert (await client.put(f"/dashboards/{d['id']}", json={"title": "aba A", "tiles": [], "version": 1})).status_code == 200
    stale = await client.put(f"/dashboards/{d['id']}", json={"title": "aba B", "tiles": [], "version": 1})
    assert stale.status_code == 409 and "changed elsewhere" in stale.json()["detail"]
    assert (await client.get(f"/dashboards/{d['id']}")).json()["title"] == "aba A"


async def test_unknown_dashboard_is_404(client):
    missing = "f" * 32
    assert (await client.get(f"/dashboards/{missing}")).status_code == 404
    assert (await client.put(f"/dashboards/{missing}", json={"title": "x", "tiles": [], "version": 1})).status_code == 404
    assert (await client.delete(f"/dashboards/{missing}")).status_code == 404


async def test_delete(client):
    d = await create(client)
    assert (await client.delete(f"/dashboards/{d['id']}")).status_code == 204
    assert (await client.get(f"/dashboards/{d['id']}")).status_code == 404


@pytest.mark.parametrize("layout", [
    {"x": 10, "y": 0, "w": 4, "h": 2},    # estoura a grade (10 + 4 > 12)
    {"x": 12, "y": 0, "w": 1, "h": 1},    # coluna fora da grade
    {"x": -1, "y": 0, "w": 1, "h": 1},
    {"x": 0, "y": 0, "w": 0, "h": 1},
    {"x": 0, "y": 0, "w": 1, "h": 41},
    {"x": 0, "y": 0, "w": 1},             # falta h
])
async def test_invalid_layout_is_422(client, layout):
    r = await client.post("/dashboards", json={"title": "x", "tiles": [{**TILES[2], "layout": layout}]})
    assert r.status_code == 422


async def test_duplicate_tile_ids_blank_title_and_missing_layout_are_422(client):
    assert (await client.post("/dashboards", json={"title": "x", "tiles": [TILES[2], {**TILES[2]}]})).status_code == 422
    assert (await client.post("/dashboards", json={"title": "   ", "tiles": []})).status_code == 422
    no_layout = {k: v for k, v in TILES[2].items() if k != "layout"}
    assert (await client.post("/dashboards", json={"title": "x", "tiles": [no_layout]})).status_code == 422
    assert (await client.post("/dashboards", json={"title": "x", "tiles": [{**TILES[0], "decimals": 9}]})).status_code == 422
    assert (await client.post("/dashboards", json={"title": "x", "tiles": [{**TILES[2], "type": "analysis"}]})).status_code == 422


async def test_too_many_tiles_is_422(client):
    many = [{**TILES[2], "id": f"t{i}"} for i in range(61)]
    assert (await client.post("/dashboards", json={"title": "x", "tiles": many})).status_code == 422
