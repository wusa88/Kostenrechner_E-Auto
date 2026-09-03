"""Rechenkern: aus Ladungen werden Verbrauch, Kosten und der Benzinvergleich.

Reine Rechnung, kein Speicher und kein HTTP. Damit ist sie einzeln pruefbar —
siehe tests/test_rechnung.py.

Konvention: Eine Ladung ist das Nachfuellen dessen, was seit der letzten Ladung
verbraucht wurde. Die Strecke zwischen zwei Kilometerstaenden wird also mit der
Energie der *spaeteren* Ladung bewertet. Die allererste Ladung hat noch keine
zugehoerige Strecke und zaehlt darum nicht in den Verbrauch — ihr Geld taucht
nur in "gesamt bezahlt" auf.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

TAGE_MONAT = 365.25 / 12
TAGE_JAHR = 365.25

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


ORTE = ("zuhause", "auswaerts")

ORTSNAMEN = {"zuhause": "zuhause", "auswaerts": "auswärts"}


@dataclass
class Ladung:
    id: int
    datum: date
    km: float
    kwh: float
    kosten: float          # was die Ladung insgesamt gekostet hat, in Euro
    notiz: str = ""
    ort: str = "zuhause"   # zuhause | auswaerts
    tarif: float | None = None   # EUR/kWh, falls je kWh statt als Summe eingetragen


def datum_lesen(wert) -> date:
    """Nimmt date, datetime oder 'JJJJ-MM-TT' und gibt ein date zurueck."""
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    return datetime.strptime(str(wert)[:10], "%Y-%m-%d").date()


def _teilen(zaehler: float, nenner: float):
    """Division, die bei Nenner 0 lieber None sagt als abzustuerzen."""
    if not nenner:
        return None
    return zaehler / nenner


def perioden(ladungen: list[Ladung]) -> tuple[list[dict], list[str]]:
    """Bildet die Strecken zwischen aufeinanderfolgenden Ladungen.

    Gibt die Perioden und eine Liste von Warnungen zurueck. Gewarnt wird bei
    fallendem Kilometerstand und bei Ladungen ohne gefahrene Strecke — beides
    wird gemeldet statt still verrechnet.
    """
    sortiert = sorted(ladungen, key=lambda l: (l.datum, l.km, l.id))
    ergebnis: list[dict] = []
    warnungen: list[str] = []

    for vorher, jetzt in zip(sortiert, sortiert[1:]):
        strecke = jetzt.km - vorher.km
        tage = (jetzt.datum - vorher.datum).days

        if strecke < 0:
            warnungen.append(
                f"{jetzt.datum:%d.%m.%Y}: Kilometerstand {jetzt.km:.0f} km liegt unter dem "
                f"vorherigen ({vorher.km:.0f} km) — diese Periode bleibt unberücksichtigt."
            )
        elif strecke == 0:
            warnungen.append(
                f"{jetzt.datum:%d.%m.%Y}: kein Kilometer gefahren seit der letzten Ladung — "
                f"die Energie zählt, ein Verbrauch lässt sich daraus nicht bilden."
            )

        ergebnis.append({
            "id": jetzt.id,
            "ort": jetzt.ort,
            "von": vorher.datum,
            "bis": jetzt.datum,
            "tage": tage,
            "km_von": vorher.km,
            "km_bis": jetzt.km,
            "strecke": strecke,
            "kwh": jetzt.kwh,
            "kosten": jetzt.kosten,
            "gueltig": strecke > 0,
            "verbrauch": _teilen(jetzt.kwh * 100.0, strecke) if strecke > 0 else None,
            "preis_kwh": _teilen(jetzt.kosten, jetzt.kwh),
            "kosten_100": _teilen(jetzt.kosten * 100.0, strecke) if strecke > 0 else None,
        })

    return ergebnis, warnungen


def _benzin(strecke: float, benzinpreis: float, benzinverbrauch: float) -> dict:
    liter = strecke * benzinverbrauch / 100.0
    return {
        "liter": liter,
        "kosten": liter * benzinpreis,
        "kosten_100": benzinverbrauch * benzinpreis,
    }


def _block(strecke: float, kwh: float, strom: float,
           benzinpreis: float, benzinverbrauch: float) -> dict:
    """Ein Satz Kennzahlen fuer eine Strecke: Strom, Benzin, Differenz."""
    benzin = _benzin(strecke, benzinpreis, benzinverbrauch)
    return {
        "strecke": strecke,
        "kwh": kwh,
        "verbrauch": _teilen(kwh * 100.0, strecke),
        "strom_kosten": strom,
        "strom_100": _teilen(strom * 100.0, strecke),
        "preis_kwh": _teilen(strom, kwh),
        "liter": benzin["liter"],
        "benzin_kosten": benzin["kosten"],
        "benzin_100": benzin["kosten_100"],
        "ersparnis": benzin["kosten"] - strom,
        "ersparnis_100": _teilen((benzin["kosten"] - strom) * 100.0, strecke),
        "ersparnis_prozent": _teilen((benzin["kosten"] - strom) * 100.0, benzin["kosten"]),
    }


def _zeitraeume(gueltige: list[dict], schluessel, beschriftung,
                benzinpreis: float, benzinverbrauch: float) -> list[dict]:
    """Fasst Perioden zu Kalendermonaten oder -jahren zusammen.

    Eine Ladung zaehlt in den Zeitraum ihres Datums — nicht anteilig ueber den
    Monatswechsel verteilt. Das ist erklaerbar und erfindet keine Genauigkeit.
    """
    eimer: dict[str, dict] = {}
    for p in gueltige:
        k = schluessel(p["bis"])
        eintrag = eimer.setdefault(k, {"schluessel": k, "titel": beschriftung(p["bis"]),
                                       "strecke": 0.0, "kwh": 0.0, "strom": 0.0, "ladungen": 0})
        eintrag["strecke"] += p["strecke"]
        eintrag["kwh"] += p["kwh"]
        eintrag["strom"] += p["kosten"]
        eintrag["ladungen"] += 1

    reihen = []
    for e in sorted(eimer.values(), key=lambda e: e["schluessel"]):
        werte = _block(e["strecke"], e["kwh"], e["strom"], benzinpreis, benzinverbrauch)
        werte.update(schluessel=e["schluessel"], titel=e["titel"], ladungen=e["ladungen"])
        reihen.append(werte)
    return reihen


def nach_orten(ladungen: list[Ladung]) -> list[dict]:
    """Trennt zuhause und auswaerts — zwei ganz verschiedene Strompreise.

    Gerechnet ueber alle Ladungen, auch die erste: hier geht es um bezahltes
    Geld, nicht um Verbrauch.
    """
    reihen = []
    for ort in ORTE:
        eigene = [l for l in ladungen if l.ort == ort]
        kwh = sum(l.kwh for l in eigene)
        kosten = sum(l.kosten for l in eigene)
        reihen.append({
            "ort": ort,
            "titel": ORTSNAMEN[ort],
            "ladungen": len(eigene),
            "kwh": kwh,
            "kosten": kosten,
            "preis_kwh": _teilen(kosten, kwh),
            "anteil_kwh": _teilen(kwh * 100.0, sum(l.kwh for l in ladungen)),
        })
    return reihen


def auswerten(ladungen: list[Ladung], benzinpreis: float, benzinverbrauch: float) -> dict:
    """Die vollstaendige Auswertung, fertig fuer die Oberflaeche."""
    liste, warnungen = perioden(ladungen)
    gueltige = [p for p in liste if p["gueltig"]]

    gesamt_kwh = sum(l.kwh for l in ladungen)
    gesamt_kosten = sum(l.kosten for l in ladungen)

    strecke = sum(p["strecke"] for p in gueltige)
    kwh = sum(p["kwh"] for p in gueltige)
    strom = sum(p["kosten"] for p in gueltige)

    ergebnis: dict = {
        "anzahl": len(ladungen),
        "benzinpreis": benzinpreis,
        "benzinverbrauch": benzinverbrauch,
        "bezahlt": {
            "kwh": gesamt_kwh,
            "kosten": gesamt_kosten,
            "preis_kwh": _teilen(gesamt_kosten, gesamt_kwh),
        },
        "orte": nach_orten(ladungen),
        "auswertbar": bool(gueltige),
        "warnungen": warnungen,
        "perioden": [
            {**p, "von": p["von"].isoformat(), "bis": p["bis"].isoformat()} for p in liste
        ][::-1],
        "monate": [],
        "jahre": [],
    }

    if not gueltige:
        ergebnis["gesamt"] = None
        ergebnis["hochrechnung"] = None
        ergebnis["zeitraum"] = None
        return ergebnis

    ergebnis["gesamt"] = _block(strecke, kwh, strom, benzinpreis, benzinverbrauch)

    von = min(p["von"] for p in gueltige)
    bis = max(p["bis"] for p in gueltige)
    tage = (bis - von).days
    ergebnis["zeitraum"] = {"von": von.isoformat(), "bis": bis.isoformat(), "tage": tage}

    # Hochrechnung: gemessener Tagesschnitt, hochgerechnet auf Monat und Jahr.
    if tage > 0:
        ergebnis["hochrechnung"] = {
            "monat": _block(strecke / tage * TAGE_MONAT, kwh / tage * TAGE_MONAT,
                            strom / tage * TAGE_MONAT, benzinpreis, benzinverbrauch),
            "jahr": _block(strecke / tage * TAGE_JAHR, kwh / tage * TAGE_JAHR,
                           strom / tage * TAGE_JAHR, benzinpreis, benzinverbrauch),
        }
    else:
        ergebnis["hochrechnung"] = None

    ergebnis["monate"] = _zeitraeume(
        gueltige, lambda d: f"{d.year:04d}-{d.month:02d}",
        lambda d: f"{MONATSNAMEN[d.month - 1]} {d.year}", benzinpreis, benzinverbrauch)
    ergebnis["jahre"] = _zeitraeume(
        gueltige, lambda d: f"{d.year:04d}", lambda d: str(d.year),
        benzinpreis, benzinverbrauch)

    return ergebnis
