"""Datenhaltung: eine JSON-Datei, sonst nichts.

Der Pfad kommt aus der Umgebungsvariablen KOSTEN_DATEI (im Container
/daten/kosten.json). Die Datei ist das einzige, was gesichert werden muss —
und sie laesst sich mit jedem Editor oeffnen, lesen und notfalls von Hand
reparieren.

Geschrieben wird immer atomar: erst vollstaendig in eine Nebendatei, dann per
os.replace an ihren Platz. Ein Absturz mitten im Schreiben kann die Datei damit
nicht halb beschrieben zuruecklassen.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from .rechnung import ORTE, Ladung, datum_lesen

FORMAT = 1

STANDARD_EINSTELLUNGEN: dict[str, object] = {
    # Was ein Liter kostet — Vorbelegung, jederzeit in der Oberflaeche aenderbar.
    "benzinpreis": 1.75,
    # Realverbrauch des Vergleichsfahrzeugs in l/100km.
    "benzinverbrauch": 7.2,
    # Haustarif in ct/kWh — Vorbelegung fuer Ladungen zuhause.
    "strompreis": 34.0,
    # Beschriftung der Oberflaeche.
    "fahrzeug": "Mein E-Auto",
}

ZAHLENFELDER = ("benzinpreis", "benzinverbrauch", "strompreis")

# Reihenfolge der Schluessel je Ladung — so steht es auch in der Datei.
FELDER = ("id", "datum", "km", "kwh", "kosten", "tarif", "ort", "notiz", "angelegt")

_lock = threading.RLock()


class SpeicherFehler(RuntimeError):
    """Die Datei ist da, ergibt aber keinen Sinn — lieber melden als überschreiben."""


def pfad() -> Path:
    return Path(os.environ.get("KOSTEN_DATEI", "daten/kosten.json"))


# ------------------------------------------------------------ Lesen, Schreiben

def _leer() -> dict:
    return {"format": FORMAT, "einstellungen": dict(STANDARD_EINSTELLUNGEN), "ladungen": []}


def _lesen() -> dict:
    """Liest die Datei. Fehlt sie, ist der Bestand leer — das ist kein Fehler."""
    ziel = pfad()
    if not ziel.is_file():
        return _leer()
    try:
        inhalt = json.loads(ziel.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        raise SpeicherFehler(
            f"{ziel} lässt sich nicht lesen: {fehler}. "
            "Die Datei wurde nicht angerührt — bitte von Hand prüfen."
        ) from None
    if not isinstance(inhalt, dict):
        raise SpeicherFehler(f"{ziel} enthält kein JSON-Objekt.")

    daten = _leer()
    werte = inhalt.get("einstellungen")
    if isinstance(werte, dict):
        daten["einstellungen"].update(_einstellungen_pruefen(werte))
    liste = inhalt.get("ladungen")
    if isinstance(liste, list):
        daten["ladungen"] = [_ladung_pruefen(e) for e in liste if isinstance(e, dict)]
    return daten


def _knapp(wert, stellen: int):
    """Raeumt Fliesskomma-Rauschen weg: 15.437999999999999 wird 15.438, 24100.0 wird 24100."""
    if wert is None:
        return None
    gerundet = round(float(wert), stellen)
    return int(gerundet) if gerundet == int(gerundet) else gerundet


def _schreiben(daten: dict) -> None:
    """Erst daneben schreiben, dann umhaengen — nie in die echte Datei hinein."""
    ziel = pfad()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    daten["ladungen"].sort(key=lambda e: (e["datum"], e["km"], e["id"]))

    # Damit die Datei lesbar bleibt — Cent-Bruchteile gehen dabei nicht verloren.
    for eintrag in daten["ladungen"]:
        for feld, stellen in (("km", 3), ("kwh", 3), ("kosten", 6), ("tarif", 6)):
            eintrag[feld] = _knapp(eintrag[feld], stellen)
    for feld in ZAHLENFELDER:
        daten["einstellungen"][feld] = _knapp(daten["einstellungen"][feld], 4)

    text = json.dumps(daten, ensure_ascii=False, indent=2) + "\n"

    daneben = ziel.with_name(ziel.name + ".neu")
    with open(daneben, "w", encoding="utf-8") as datei:
        datei.write(text)
        datei.flush()
        os.fsync(datei.fileno())
    os.replace(daneben, ziel)


def _zahl(wert, ersatz: float) -> float:
    try:
        return float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        return ersatz


def _einstellungen_pruefen(werte: dict) -> dict:
    """Nimmt nur bekannte Schluessel und macht aus '1,75' wieder eine Zahl."""
    sauber: dict[str, object] = {}
    for schluessel, standard in STANDARD_EINSTELLUNGEN.items():
        if schluessel not in werte:
            continue
        wert = werte[schluessel]
        if schluessel in ZAHLENFELDER:
            sauber[schluessel] = _zahl(wert, float(standard))
        else:
            sauber[schluessel] = str(wert).strip()[:60] or standard
    return sauber


def _ladung_pruefen(eintrag: dict) -> dict:
    """Macht aus einem Eintrag der Datei einen mit allen Feldern."""
    tarif = eintrag.get("tarif")
    ort = str(eintrag.get("ort") or "zuhause")
    return {
        "id": int(_zahl(eintrag.get("id"), 0)),
        "datum": str(eintrag.get("datum") or "")[:10],
        "km": _zahl(eintrag.get("km"), 0.0),
        "kwh": _zahl(eintrag.get("kwh"), 0.0),
        "kosten": _zahl(eintrag.get("kosten"), 0.0),
        "tarif": None if tarif in (None, "") else _zahl(tarif, 0.0),
        "ort": ort if ort in ORTE else "zuhause",
        "notiz": str(eintrag.get("notiz") or ""),
        "angelegt": str(eintrag.get("angelegt") or ""),
    }


def anlegen() -> None:
    """Sorgt dafuer, dass die Datei existiert. Mehrfach aufrufbar."""
    with _lock:
        if pfad().is_file():
            _lesen()          # frueh melden, wenn die Datei kaputt ist
            return
        alt = _sqlite_gefunden()
        _schreiben(_aus_sqlite(alt) if alt else _leer())
        if alt:
            print(f"Alte Datenbank {alt} übernommen nach {pfad()}.", flush=True)


# ----------------------------------------------------------------- Ladungen

def _zu_ladung(eintrag: dict) -> Ladung:
    return Ladung(
        id=eintrag["id"],
        datum=datum_lesen(eintrag["datum"]),
        km=eintrag["km"],
        kwh=eintrag["kwh"],
        kosten=eintrag["kosten"],
        notiz=eintrag["notiz"],
        ort=eintrag["ort"],
        tarif=eintrag["tarif"],
    )


def ladungen() -> list[Ladung]:
    with _lock:
        daten = _lesen()
    eintraege = sorted(daten["ladungen"], key=lambda e: (e["datum"], e["km"], e["id"]))
    return [_zu_ladung(e) for e in eintraege]


def ladung_anlegen(datum: date, km: float, kwh: float, kosten: float, notiz: str = "",
                   ort: str = "zuhause", tarif: float | None = None) -> int:
    with _lock:
        daten = _lesen()
        kennung = max((e["id"] for e in daten["ladungen"]), default=0) + 1
        daten["ladungen"].append({
            "id": kennung,
            "datum": datum.isoformat(),
            "km": km,
            "kwh": kwh,
            "kosten": kosten,
            "tarif": tarif,
            "ort": ort,
            "notiz": notiz,
            "angelegt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _schreiben(daten)
    return kennung


def ladung_aendern(kennung: int, datum: date, km: float, kwh: float,
                   kosten: float, notiz: str = "", ort: str = "zuhause",
                   tarif: float | None = None) -> bool:
    with _lock:
        daten = _lesen()
        for eintrag in daten["ladungen"]:
            if eintrag["id"] != kennung:
                continue
            eintrag.update(datum=datum.isoformat(), km=km, kwh=kwh, kosten=kosten,
                           tarif=tarif, ort=ort, notiz=notiz)
            _schreiben(daten)
            return True
    return False


def ladung_loeschen(kennung: int) -> bool:
    with _lock:
        daten = _lesen()
        bleibt = [e for e in daten["ladungen"] if e["id"] != kennung]
        if len(bleibt) == len(daten["ladungen"]):
            return False
        daten["ladungen"] = bleibt
        _schreiben(daten)
    return True


# ------------------------------------------------------------ Einstellungen

def einstellungen() -> dict[str, object]:
    with _lock:
        return _lesen()["einstellungen"]


def einstellungen_setzen(werte: dict) -> None:
    sauber = _einstellungen_pruefen(werte)
    if not sauber:
        return
    with _lock:
        daten = _lesen()
        daten["einstellungen"].update(sauber)
        _schreiben(daten)


# ------------------------------------------- Einmalige Übernahme aus SQLite

def _sqlite_gefunden() -> Path | None:
    """Fassung 1.0 legte eine SQLite-Datei an — die soll nicht verloren gehen."""
    kandidaten = [Path(os.environ["KOSTEN_DB"])] if os.environ.get("KOSTEN_DB") else []
    kandidaten.append(pfad().with_suffix(".db"))
    for kandidat in kandidaten:
        if kandidat.is_file():
            return kandidat
    return None


def _aus_sqlite(quelle: Path) -> dict:
    import sqlite3

    daten = _leer()
    verbindung = sqlite3.connect(quelle)
    verbindung.row_factory = sqlite3.Row
    try:
        spalten = {z["name"] for z in verbindung.execute("PRAGMA table_info(ladungen)")}
        if not spalten:
            return daten
        for zeile in verbindung.execute("SELECT * FROM ladungen ORDER BY id"):
            eintrag = dict(zeile)
            daten["ladungen"].append(_ladung_pruefen(eintrag))
        for zeile in verbindung.execute("SELECT schluessel, wert FROM einstellungen"):
            daten["einstellungen"].update(
                _einstellungen_pruefen({zeile["schluessel"]: zeile["wert"]}))
    except sqlite3.DatabaseError as fehler:
        raise SpeicherFehler(f"{quelle} lässt sich nicht übernehmen: {fehler}") from None
    finally:
        verbindung.close()
    return daten
