"""Bundeslebensmittelschlüssel 4.0 lesen (Max Rubner-Institut, CC BY 4.0).

Das MRI verteilt den BLS als ZIP mit einer Excel-Datei: eine Zeile je Lebensmittel,
je Nährstoff drei Spalten (Wert, Datenherkunft, Referenz). Die Wertespalte heißt
`"<CODE> <Bezeichnung> [<Einheit>/100g]"` - der Code vor dem ersten Leerzeichen ist der
stabile Schlüssel (`FE`, `VITB12`, ...). Leere Zellen bleiben weg: unbekannt ist nicht
null.

Der Download-Link trägt ein `?token=`, das sich ändern kann. Darum gilt: liegt schon eine
ZIP oder Excel in `data/catalog/bls/`, wird die genommen; sonst wird geladen.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

LOG = logging.getLogger(__name__)

BLS_URL = (
    "https://www.blsdb.de/assets/uploads/BLS_4_0_2025_DE.zip"
    "?token=QASB-T38P-4272-SXCB-NII4-PW6G-J9E9-W33D"
)
ZIP_NAME = "BLS_4_0_2025_DE.zip"
DATA_SUFFIX = "_Daten_2025_DE.xlsx"

ATTRIBUTION = (
    "Max Rubner-Institut (2025): Bundeslebensmittelschlüssel (BLS), Version 4.0 – "
    "Deutsche Nährstoffdatenbank. Karlsruhe. DOI: 10.25826/Data20251217-134202-0 "
    "(CC BY 4.0)"
)


@dataclass(frozen=True, slots=True)
class BlsRow:
    code: str
    name: str
    name_en: str | None
    nutrients: dict[str, float]


class BlsSourceMissing(RuntimeError):
    pass


def bls_dir(catalog_dir: Path) -> Path:
    return catalog_dir / "bls"


def locate_or_download(catalog_dir: Path, *, url: str = BLS_URL) -> Path:
    """Vorhandene Datei in `data/catalog/bls/` - oder einmal laden."""
    folder = bls_dir(catalog_dir)
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob("*.zip")) + sorted(folder.glob(f"*{DATA_SUFFIX}"))
    if existing:
        return existing[-1]
    target = folder / ZIP_NAME
    LOG.info("BLS laden: %s", url.split("?")[0])
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    except httpx.HTTPError as error:
        target.unlink(missing_ok=True)
        raise BlsSourceMissing(
            f"BLS-Download fehlgeschlagen ({error}). Die ZIP von https://blsdb.de/download "
            f"nach {folder} legen und den Befehl wiederholen."
        ) from error
    return target


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path, codes: Iterable[str]) -> Iterator[BlsRow]:
    """Die Lebensmittel aus ZIP oder Excel, beschränkt auf `codes`."""
    from openpyxl import load_workbook

    wanted = set(codes)
    if path.suffix == ".zip":
        archive = zipfile.ZipFile(path)
        member = next(
            (name for name in archive.namelist() if name.endswith(DATA_SUFFIX)), None
        )
        if member is None:
            raise BlsSourceMissing(f"In {path.name} fehlt die Datei *{DATA_SUFFIX}")
        handle = archive.open(member)
    else:
        archive = None
        handle = path.open("rb")

    try:
        workbook = load_workbook(handle, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows)
        columns = _value_columns(header, wanted)
        missing = wanted - set(columns.values())
        if missing:
            raise BlsSourceMissing(f"Spalten fehlen im BLS: {sorted(missing)}")
        for row in rows:
            code = row[0]
            if not code or not row[1]:
                continue
            nutrients: dict[str, float] = {}
            for index, nutrient in columns.items():
                value = row[index] if index < len(row) else None
                if isinstance(value, int | float) and not isinstance(value, bool):
                    nutrients[nutrient] = float(value)
            yield BlsRow(
                code=str(code).strip(),
                name=str(row[1]).strip(),
                name_en=str(row[2]).strip() if row[2] else None,
                nutrients=nutrients,
            )
        workbook.close()
    finally:
        handle.close()
        if archive is not None:
            archive.close()


def _value_columns(header: tuple, wanted: set[str]) -> dict[int, str]:
    """`{Spaltenindex: Code}` für die Wertespalten der gewünschten Nährstoffe."""
    out: dict[int, str] = {}
    for index, title in enumerate(header):
        if not isinstance(title, str) or "/100g]" not in title:
            continue
        code = title.split(" ", 1)[0]
        if code in wanted:
            out[index] = code
    return out
