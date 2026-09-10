"""Rechenkern: aus Ladungen werden Verbrauch, Kosten und der Benzinvergleich.

Reine Rechnung, kein Speicher und kein HTTP. Damit ist sie einzeln pruefbar —
siehe tests/test_rechnung.py.

Konvention: Eine Ladung ist das Nachfuellen dessen, was seit der letzten Ladung
verbraucht wurde. Die Strecke zwischen zwei Kilometerstaenden wird also mit der
Energie der *spaeteren* Ladung bewertet. Die allererste Ladung hat noch keine
zugehoerige Strecke und zaehlt darum nicht in den Verbrauch — ihr Geld taucht
nur in "gesamt bezahlt" auf.

Das ist genau dann exakt, wenn der Akku am Anfang und am Ende gleich voll ist —
nicht "voll", sondern *gleich*. Weil das beim E-Auto selten zutrifft, darf zu
jeder Ladung der Ladestand in Prozent mitgeschrieben werden. Zusammen mit der
nutzbaren Akkukapazitaet wird daraus die fehlende Groesse:

    verbrauchte Energie = geladene Energie + (Ladestand vorher - nachher) * Kapazitaet

Ueber eine Kette von Ladungen kuerzen sich die Zwischenwerte weg: fuer eine
Spanne zaehlen nur der Ladestand ihrer ersten und ihrer letzten Ladung. Wer nur
diese beiden eintraegt, bekommt die Spanne trotzdem exakt.
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


ORTE = ("zuhause", "auswaerts", "pv")

ORTSNAMEN = {"zuhause": "zuhause", "auswaerts": "auswärts", "pv": "PV-Überschuss"}


@dataclass
class Ladung:
    id: int
    datum: date
    km: float
    kwh: float
    kosten: float          # was die Ladung insgesamt gekostet hat, in Euro
    notiz: str = ""
    ort: str = "zuhause"   # zuhause | auswaerts | pv (Ueberschuss der eigenen Anlage)
    tarif: float | None = None   # EUR/kWh, falls je kWh statt als Summe eingetragen
    soc: float | None = None     # Ladestand in Prozent NACH dieser Ladung
    netz_kwh: float | None = None  # bei PV-Ladung: der Teil, der doch aus dem Netz kam


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
            "von_id": vorher.id,
            "ort": jetzt.ort,
            "soc_von": vorher.soc,
            "soc_bis": jetzt.soc,
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


def korrektur(spanne: list[dict], kapazitaet: float) -> float | None:
    """Die Energie, die der Akku ueber diese Spanne mehr abgegeben als aufgenommen hat.

    Verlangt den Ladestand der ersten und der letzten Ladung der Spanne, eine
    Kapazitaet und eine luekenlose Kette dazwischen. Fehlt eines davon, gibt es
    keine Korrektur — dann bleibt es bei der Schaetzung.
    """
    if not spanne or kapazitaet <= 0:
        return None
    for vorher, jetzt in zip(spanne, spanne[1:]):
        if vorher["id"] != jetzt["von_id"]:
            return None          # eine unbrauchbare Periode dazwischen: Kette gerissen
    anfang, ende = spanne[0]["soc_von"], spanne[-1]["soc_bis"]
    if anfang is None or ende is None:
        return None
    return (anfang - ende) / 100.0 * kapazitaet


def _benzin(strecke: float, benzinpreis: float, benzinverbrauch: float) -> dict:
    liter = strecke * benzinverbrauch / 100.0
    return {
        "liter": liter,
        "kosten": liter * benzinpreis,
        "kosten_100": benzinverbrauch * benzinpreis,
    }


def _block(strecke: float, kwh: float, strom: float,
           benzinpreis: float, benzinverbrauch: float,
           ausgleich: float | None = None) -> dict:
    """Ein Satz Kennzahlen fuer eine Strecke: Strom, Benzin, Differenz.

    `ausgleich` ist die aus dem Ladestand errechnete Energie: positiv, wenn der
    Akku am Ende leerer war als am Anfang. Sie geht in den Verbrauch ein, nicht
    in die Kosten — bezahlt wurde, was bezahlt wurde.
    """
    benzin = _benzin(strecke, benzinpreis, benzinverbrauch)
    verbraucht = kwh + (ausgleich or 0.0)
    return {
        "strecke": strecke,
        "kwh": kwh,
        "ausgleich": ausgleich,
        "gemessen": ausgleich is not None,
        "kwh_verbraucht": verbraucht,
        "verbrauch": _teilen(verbraucht * 100.0, strecke),
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
                benzinpreis: float, benzinverbrauch: float,
                kapazitaet: float = 0.0) -> list[dict]:
    """Fasst Perioden zu Kalendermonaten oder -jahren zusammen.

    Eine Ladung zaehlt in den Zeitraum ihres Datums — nicht anteilig ueber den
    Monatswechsel verteilt. Das ist erklaerbar und erfindet keine Genauigkeit.
    """
    eimer: dict[str, dict] = {}
    for p in gueltige:
        k = schluessel(p["bis"])
        eintrag = eimer.setdefault(k, {"schluessel": k, "titel": beschriftung(p["bis"]),
                                       "strecke": 0.0, "kwh": 0.0, "strom": 0.0,
                                       "ladungen": 0, "spanne": []})
        eintrag["strecke"] += p["strecke"]
        eintrag["kwh"] += p["kwh"]
        eintrag["strom"] += p["kosten"]
        eintrag["ladungen"] += 1
        eintrag["spanne"].append(p)

    reihen = []
    for e in sorted(eimer.values(), key=lambda e: e["schluessel"]):
        werte = _block(e["strecke"], e["kwh"], e["strom"], benzinpreis, benzinverbrauch,
                       korrektur(e["spanne"], kapazitaet))
        werte.update(schluessel=e["schluessel"], titel=e["titel"], ladungen=e["ladungen"])
        reihen.append(werte)
    return reihen


def nach_orten(ladungen: list[Ladung]) -> list[dict]:
    """Trennt zuhause, auswaerts und PV-Ueberschuss — drei ganz verschiedene Preise.

    Gerechnet ueber alle Ladungen, auch die erste: hier geht es um bezahltes
    Geld, nicht um Verbrauch.

    Bei der PV-Zeile steht zusaetzlich, wieviel davon doch aus dem Netz kam
    (`netz_kwh`, aus der Ladung selbst) und wieviel aus der eigenen Anlage
    (`pv_kwh`). Nur der Netzanteil ist bezahlt worden, und darum gibt es dort
    zwei Preise, die man nicht verwechseln darf:

    - `netz_preis_kwh` = Kosten / Netzanteil: was jede *gekaufte* kWh gekostet
      hat. Das ist der Arbeitspreis, den man auch bezahlt hat.
    - `preis_kwh` = Kosten / geladene Energie: was eine geladene kWh im Schnitt
      gekostet hat, die Gratis-Sonne eingerechnet. Immer kleiner, und kein Preis,
      zu dem irgendjemand irgendetwas gekauft haette.

    Die PV-Zeile erscheint erst, wenn es eine PV-Ladung gibt — wer keine Anlage
    hat, soll auch keine leere Zeile sehen.
    """
    reihen = []
    for ort in ORTE:
        eigene = [l for l in ladungen if l.ort == ort]
        if ort == "pv" and not eigene:
            continue
        kwh = sum(l.kwh for l in eigene)
        kosten = sum(l.kosten for l in eigene)
        # Ein von Hand verdrehter Netzanteil wird gemeldet (siehe auswerten) und
        # hier gedeckelt, damit die PV-Menge nicht negativ wird.
        netz = sum(min(l.netz_kwh or 0.0, l.kwh) for l in eigene) if ort == "pv" else None
        reihen.append({
            "ort": ort,
            "titel": ORTSNAMEN[ort],
            "ladungen": len(eigene),
            "kwh": kwh,
            "kosten": kosten,
            "netz_kwh": netz,
            "pv_kwh": None if netz is None else kwh - netz,
            "preis_kwh": _teilen(kosten, kwh),
            "netz_preis_kwh": None if netz is None else _teilen(kosten, netz),
            "anteil_kwh": _teilen(kwh * 100.0, sum(l.kwh for l in ladungen)),
        })
    return reihen


def ueberschuss(bezug: float, einspeisung: float, ladung: float,
                erzeugung: float | None = None, tarif: float = 0.0) -> dict:
    """Teilt eine Ladung in Netz- und PV-Anteil — aus abgelesenen Zaehlerstaenden.

    Erwartet die *Differenzen* ueber das Ladefenster: `bezug` aus 1.8.0,
    `einspeisung` aus 2.8.0, `erzeugung` vom Wechselrichter, `ladung` aus der
    Wallbox. Damit stehen die uebrigen Groessen fest:

        Eigenverbrauch = Erzeugung - Einspeisung
        Hausverbrauch  = Eigenverbrauch + Bezug
        Restlast       = Hausverbrauch - Ladung        (alles ausser dem Auto)

    Offen bleibt die eine Frage, die kein Zaehler beantwortet: **wem gehoert der
    Netzbezug?** Strom ist nicht markiert; waehrend einer Wolke ziehen Haus und
    Auto gleichzeitig. Es gibt darum nicht eine Zahl, sondern eine Spanne:

        hoch      = min(Bezug, Ladung)          das Auto zuerst am Netz
        tief      = max(0, Bezug - Restlast)    das Haus zuerst am Netz
        anteilig  = Bezug * Ladung / Hausverbrauch

    Vorgeschlagen wird `hoch`. Das passt zur Regelung — die bedient aus der PV
    zuerst das Haus und gibt dem Auto den Ueberschuss, also faellt der Fehlbetrag
    dem Auto zu — und es ist die konservative Wahl: sie macht das Laden teurer,
    nie billiger.

    Ohne `erzeugung` bleibt der Vorschlag, aber es gibt keine Spanne: ohne sie
    ist die Restlast unbekannt. Gerechnet wird trotzdem, nur ungenauer — und das
    steht dann auch so da.
    """
    warnungen: list[str] = []
    ergebnis: dict = {
        "bezug": bezug,
        "einspeisung": einspeisung,
        "erzeugung": erzeugung,
        "ladung": ladung,
        "eigenverbrauch": None,
        "hausverbrauch": None,
        "restlast": None,
        "spanne": None,
        "warnungen": warnungen,
    }

    if erzeugung is not None:
        eigen = erzeugung - einspeisung
        haus = eigen + bezug
        rest = haus - ladung
        ergebnis.update(eigenverbrauch=eigen, hausverbrauch=haus, restlast=rest)

        if eigen < 0:
            warnungen.append(
                f"Es wurden {einspeisung:.1f} kWh eingespeist, aber nur {erzeugung:.1f} kWh "
                f"erzeugt — da fehlt Erzeugung. Speist noch etwas anderes hinter dem "
                f"Zähler ein, oder ist der Ablesezeitraum nicht derselbe?"
            )
        if rest < 0:
            warnungen.append(
                f"Ins Auto gingen {ladung:.1f} kWh, im ganzen Haus verbraucht wurden aber nur "
                f"{haus:.1f} kWh. Das kann nicht sein: entweder liegt das Ladefenster nicht "
                f"in den abgelesenen Ständen, oder eine Erzeugung fehlt in der Bilanz."
            )

    hoch = min(bezug, ladung)
    if erzeugung is not None and ergebnis["restlast"] is not None:
        tief = max(0.0, bezug - max(0.0, ergebnis["restlast"]))
        anteilig = _teilen(bezug * ladung, ergebnis["hausverbrauch"])
        ergebnis["spanne"] = {
            "tief": min(tief, hoch),
            "hoch": hoch,
            "anteilig": None if anteilig is None else min(anteilig, hoch),
        }

    netz = hoch
    ergebnis.update(
        netz_kwh=netz,
        pv_kwh=ladung - netz,
        pv_anteil=_teilen((ladung - netz) * 100.0, ladung),
        kosten=netz * tarif,
        tarif=tarif,
    )
    return ergebnis


# Ab dieser Groesse gilt die Unsicherheit als klein genug, um sie nicht mehr
# eigens zu erwaehnen: ein Sechstel des Verbrauchs.
GRENZE_VORLAEUFIG = 1 / 6


def verlaesslichkeit(ladungen: list[Ladung], gueltige: list[dict],
                     strecke: float, verbrauch: float | None,
                     ausgleich: float | None = None) -> dict:
    """Wie belastbar ist der Verbrauch schon?

    Der Rechner weiss nicht, wie voll der Akku beim ersten und beim letzten
    Eintrag war — er sieht nur, was geladen wurde. Wer nach 134 km bloss 12 kWh
    nachlaedt, hat den Rest aus dem Akku gefahren; der Verbrauch faellt dann zu
    niedrig aus. Der Fehler ist durch den Ladehub begrenzt, und die groesste je
    eingetragene Ladung ist dafuer der beste Anhaltspunkt, den die Daten hergeben.
    Er waechst nicht mit — die Strecke schon. Deshalb mittelt sich das heraus.
    """
    groesste = max((l.kwh for l in ladungen), default=0.0)
    spanne = _teilen(groesste * 100.0, strecke)
    mit_soc = sum(1 for l in ladungen if l.soc is not None)
    return {
        "perioden": len(gueltige),
        "spanne": spanne,
        "gemessen": ausgleich is not None,
        "ausgleich": ausgleich,
        "ausgleich_100": _teilen((ausgleich or 0.0) * 100.0, strecke) if ausgleich is not None else None,
        "mit_ladestand": mit_soc,
        "vorlaeufig": bool(
            ausgleich is None and spanne is not None
            and verbrauch and spanne > verbrauch * GRENZE_VORLAEUFIG),
    }


def auswerten(ladungen: list[Ladung], benzinpreis: float, benzinverbrauch: float,
              kapazitaet: float = 0.0) -> dict:
    """Die vollstaendige Auswertung, fertig fuer die Oberflaeche."""
    liste, warnungen = perioden(ladungen)
    gueltige = [p for p in liste if p["gueltig"]]

    for eintrag in sorted(ladungen, key=lambda l: (l.datum, l.km, l.id)):
        if eintrag.netz_kwh is not None and eintrag.netz_kwh > eintrag.kwh + 1e-9:
            warnungen.append(
                f"{eintrag.datum:%d.%m.%Y}: Netzanteil {eintrag.netz_kwh:.1f} kWh ist größer "
                f"als die geladene Energie ({eintrag.kwh:.1f} kWh) — bitte nachsehen."
            )

    # Je Periode: steht der Ladestand an beiden Enden, ist ihr Verbrauch gemessen.
    for p in liste:
        eigen = korrektur([p], kapazitaet) if p["gueltig"] else None
        p["ausgleich"] = eigen
        p["gemessen"] = eigen is not None
        p["kwh_verbraucht"] = None if not p["gueltig"] else p["kwh"] + (eigen or 0.0)
        if p["gueltig"]:
            p["verbrauch"] = p["kwh_verbraucht"] * 100.0 / p["strecke"]

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
        "aussen_vor": {
            "anzahl": len(ladungen) - len(gueltige),
            "kwh": gesamt_kwh - kwh,
            "kosten": gesamt_kosten - strom,
        },
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
        ergebnis["verlaesslichkeit"] = verlaesslichkeit(ladungen, gueltige, 0.0, None)
        return ergebnis

    ausgleich = korrektur(gueltige, kapazitaet)
    ergebnis["gesamt"] = _block(strecke, kwh, strom, benzinpreis, benzinverbrauch, ausgleich)
    ergebnis["verlaesslichkeit"] = verlaesslichkeit(
        ladungen, gueltige, strecke, ergebnis["gesamt"]["verbrauch"], ausgleich)

    von = min(p["von"] for p in gueltige)
    bis = max(p["bis"] for p in gueltige)
    tage = (bis - von).days
    ergebnis["zeitraum"] = {"von": von.isoformat(), "bis": bis.isoformat(), "tage": tage}

    # Hochrechnung: gemessener Tagesschnitt, hochgerechnet auf Monat und Jahr.
    if tage > 0:
        def hoch(faktor: float) -> dict:
            anteil = faktor / tage
            return _block(strecke * anteil, kwh * anteil, strom * anteil,
                          benzinpreis, benzinverbrauch,
                          None if ausgleich is None else ausgleich * anteil)

        ergebnis["hochrechnung"] = {"monat": hoch(TAGE_MONAT), "jahr": hoch(TAGE_JAHR)}
    else:
        ergebnis["hochrechnung"] = None

    ergebnis["monate"] = _zeitraeume(
        gueltige, lambda d: f"{d.year:04d}-{d.month:02d}",
        lambda d: f"{MONATSNAMEN[d.month - 1]} {d.year}",
        benzinpreis, benzinverbrauch, kapazitaet)
    ergebnis["jahre"] = _zeitraeume(
        gueltige, lambda d: f"{d.year:04d}", lambda d: str(d.year),
        benzinpreis, benzinverbrauch, kapazitaet)

    return ergebnis
