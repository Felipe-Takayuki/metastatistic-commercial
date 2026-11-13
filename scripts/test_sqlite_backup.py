import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("sqlite_backup.py")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def make(path: Path, rows: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO t (v) VALUES (?)", [(f"x{i}",) for i in range(rows)])
    con.commit()
    con.close()


def count(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        con.close()


def test_backup_verify_and_restore_roundtrip(tmp_path):
    data, bkp = tmp_path / "data", tmp_path / "bkp"
    make(data / "auth" / "auth_tenant.db", 3)
    make(data / "billing" / "billing.db", 5)

    assert run("backup", data, bkp).returncode == 0
    assert count(bkp / "auth" / "auth_tenant.db") == 3 and count(bkp / "billing" / "billing.db") == 5
    assert run("verify", bkp).returncode == 0

    # o "desastre": o banco atual muda/perde dados; a restauração devolve o estado do backup
    con = sqlite3.connect(data / "billing" / "billing.db")
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    assert run("restore", bkp, data).returncode == 0
    assert count(data / "billing" / "billing.db") == 5
    assert (data / "billing" / "billing.db.antes-da-restauracao").exists()     # nada é sobrescrito sem deixar rastro


def test_corrupt_backup_is_refused(tmp_path):
    bkp = tmp_path / "bkp"
    bkp.mkdir()
    (bkp / "x.db").write_bytes(b"isto nao e um banco sqlite" * 50)
    r = run("verify", bkp)
    assert r.returncode != 0
    assert run("restore", bkp, tmp_path / "data").returncode != 0
