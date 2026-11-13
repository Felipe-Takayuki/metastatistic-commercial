#!/usr/bin/env python3
"""Backup e restauração consistentes dos bancos SQLite do Metastatistic (um por serviço).

Usa a API de backup do SQLite (cópia consistente mesmo com o serviço escrevendo) e confere `PRAGMA integrity_check`
na cópia. Não depende de nada além do Python 3.

    # dentro do volume/diretório de dados (ex.: /srv/data do platform, /data da api):
    python3 scripts/sqlite_backup.py backup  /srv/data  /backups/2026-11-13
    python3 scripts/sqlite_backup.py verify  /backups/2026-11-13
    python3 scripts/sqlite_backup.py restore /backups/2026-11-13 /srv/data     # com o serviço PARADO

Com Docker:  docker compose cp scripts/sqlite_backup.py platform:/tmp/ && docker compose exec platform python3 /tmp/sqlite_backup.py backup /srv/data /tmp/bkp
"""
import sqlite3
import sys
from pathlib import Path


def databases(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.db") if p.is_file())


def backup(src_root: Path, dest_root: Path) -> list[Path]:
    out = []
    for db in databases(src_root):
        target = dest_root / db.relative_to(src_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        check(target)
        out.append(target)
    return out


def check(db: Path) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    if result != "ok":
        raise SystemExit(f"{db}: integrity_check falhou: {result}")


def restore(backup_root: Path, dest_root: Path) -> list[Path]:
    """Copia de volta (serviço parado). O banco atual, se existir, vira `<nome>.db.antes-da-restauracao`."""
    out = []
    for db in databases(backup_root):
        check(db)
        target = dest_root / db.relative_to(backup_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.rename(target.with_name(target.name + ".antes-da-restauracao"))
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        out.append(target)
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "backup":
        done = backup(Path(argv[1]), Path(argv[2]))
    elif len(argv) >= 2 and argv[0] == "verify":
        done = databases(Path(argv[1]))
        for d in done:
            check(d)
    elif len(argv) >= 3 and argv[0] == "restore":
        done = restore(Path(argv[1]), Path(argv[2]))
    else:
        print(__doc__)
        return 2
    for d in done:
        print(f"ok  {d}")
    print(f"{len(done)} banco(s) {argv[0]}")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
