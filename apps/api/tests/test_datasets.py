from pathlib import Path

from app.config import settings
from conftest import SALES_CSV, upload


async def test_upload_infers_schema_and_measurement(client):
    ds = await upload(client, SALES_CSV)
    assert ds["n_rows"] == 4 and ds["table_name"] == "vendas" and ds["name"] == "vendas.csv"
    cols = {c["name"]: c for c in ds["columns"]}
    assert cols["id"]["dtype"] == "BIGINT" and cols["id"]["measurement"] == "ordinal"  # poucos valores distintos
    assert cols["regiao"]["measurement"] == "nominal"
    assert cols["receita"]["dtype"] == "DOUBLE" and cols["receita"]["measurement"] == "scale"
    assert cols["dia"]["dtype"] == "DATE"
    # n_distinct existe para texto/inteiro/data (a UI usa para achar variáveis de 2 grupos), não para ponto flutuante
    assert (cols["regiao"]["n_distinct"], cols["id"]["n_distinct"], cols["dia"]["n_distinct"]) == (2, 4, 4)
    assert cols["receita"]["n_distinct"] is None
    assert (settings.data_dir / "datasets" / f"{ds['id']}.parquet").exists()


async def test_many_distinct_integers_are_scale(client):
    csv = "x\n" + "\n".join(str(i) for i in range(50))
    ds = await upload(client, csv, "nums.csv")
    assert ds["columns"][0]["measurement"] == "scale"


async def test_duplicate_names_get_unique_table_names(client):
    a = await upload(client, SALES_CSV, "Vendas 2024.csv")
    b = await upload(client, SALES_CSV, "Vendas 2024.csv")
    assert a["table_name"] == "vendas_2024" and b["table_name"] == "vendas_2024_2"


async def test_digit_leading_name_is_made_sql_safe(client):
    ds = await upload(client, SALES_CSV, "2024.csv")
    assert ds["table_name"] == "d_2024"


async def test_malformed_and_empty_csv_are_422(client):
    for body in ["", "a,b,c\n", "\x00\x01\x02"]:
        r = await client.post("/datasets", files={"file": ("bad.csv", body.encode(), "text/csv")})
        assert r.status_code == 422, (body, r.text)
    assert not list((settings.data_dir / "datasets").glob("*.parquet"))  # nada órfão


async def test_oversize_upload_is_413(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    r = await client.post("/datasets", files={"file": ("big.csv", b"a\n1\n", "text/csv")})
    assert r.status_code == 413
    assert not list((settings.data_dir / "tmp").glob("*"))  # temporário removido


async def test_filename_is_never_used_as_a_path(client, tmp_path):
    ds = await upload(client, SALES_CSV, "../../../evil.csv")
    assert ds["table_name"] == "evil"
    assert not (tmp_path / "evil.csv").exists()
    stored = {p.name for p in (settings.data_dir / "datasets").iterdir()}
    assert stored == {f"{ds['id']}.parquet"}


async def test_patch_measurement_persists_and_validates(client):
    ds = await upload(client, SALES_CSV)
    r = await client.patch(f"/datasets/{ds['id']}", json={"measurement": {"id": "nominal"}})
    assert r.status_code == 200
    got = (await client.get(f"/datasets/{ds['id']}")).json()
    assert {c["name"]: c["measurement"] for c in got["columns"]}["id"] == "nominal"
    assert (await client.patch(f"/datasets/{ds['id']}", json={"measurement": {"nope": "scale"}})).status_code == 422
    assert (await client.patch(f"/datasets/{ds['id']}", json={"measurement": {"id": "weird"}})).status_code == 422


async def test_list_preview_delete(client):
    ds = await upload(client, SALES_CSV)
    assert [d["id"] for d in (await client.get("/datasets")).json()] == [ds["id"]]
    prev = (await client.get(f"/datasets/{ds['id']}/preview?limit=2")).json()
    assert prev["row_count"] == 2 and prev["truncated"] is True and [c["name"] for c in prev["columns"]][0] == "id"
    assert (await client.delete(f"/datasets/{ds['id']}")).status_code == 204
    assert (await client.get(f"/datasets/{ds['id']}")).status_code == 404
    assert not Path(settings.data_dir / "datasets" / f"{ds['id']}.parquet").exists()
    assert (await client.delete(f"/datasets/{ds['id']}")).status_code == 404
