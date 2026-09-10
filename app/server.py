"""Weboberflaeche: kleiner HTTP-Server aus der Standardbibliothek.

Keine Abhaengigkeiten, kein CDN, keine Verbindung nach draussen. Start:

    python3 -m app.server            # http://0.0.0.0:8080
    python3 -m app.server --port 8385
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import socket
import sys
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, speicher
from .rechnung import ORTE, ORTSNAMEN, auswerten, datum_lesen, ueberschuss

WEB = Path(__file__).resolve().parent / "web"

TYPEN = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
    ".ico": "image/x-icon",
}


class Eingabefehler(ValueError):
    """Was der Benutzer geschickt hat, ergibt keinen Sinn — mit Klartext sagen."""


# ------------------------------------------------------------------ Lesen

TAUSENDER = re.compile(r"[+-]?[1-9]\d{0,2}(?:\.\d{3})+")


def _text_zu_zahl(text: str) -> float:
    """Liest 12,5 und 12.5 gleichermassen — und 10.000 als Zehntausend.

    Getippt wird auf dem Handy am Zaehler, nicht in einer Tabellenkalkulation:
    Punkt und Komma kommen beide vor, mal als Dezimal-, mal als Tausendertrenner.
    """
    text = text.strip()
    for weg in ("€", "EUR", "kWh", "km", "l", "\u00a0", " ", "\u202f"):
        text = text.replace(weg, "")
    if "," in text and "." in text:            # 1.234,56 — Punkt trennt Tausender
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:                          # 12,5
        text = text.replace(",", ".")
    elif TAUSENDER.fullmatch(text):            # 10.000, aber nicht 12.5 oder 0.500
        text = text.replace(".", "")
    return float(text)


def zahl(wert, feld: str, *, minimum: float | None = 0.0,
         hoechstens: float | None = None,
         pflicht: bool = True, standard: float = 0.0) -> float:
    """Nimmt 12,5 genauso wie 12.5 und raeumt Einheiten weg."""
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        if pflicht:
            raise Eingabefehler(f"{feld} fehlt.")
        return standard
    if isinstance(wert, (int, float)):
        gelesen = float(wert)
    else:
        try:
            gelesen = _text_zu_zahl(str(wert))
        except ValueError:
            raise Eingabefehler(f"{feld}: „{wert}“ ist keine Zahl.") from None
    if gelesen != gelesen or gelesen in (float("inf"), float("-inf")):
        raise Eingabefehler(f"{feld}: keine gültige Zahl.")
    if minimum is not None and gelesen < minimum:
        raise Eingabefehler(f"{feld} darf nicht kleiner als {minimum:g} sein.")
    if hoechstens is not None and gelesen > hoechstens:
        raise Eingabefehler(f"{feld} darf nicht größer als {hoechstens:g} sein.")
    return gelesen


DATUMSFORMATE = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y")


def datum_aus(wert, feld: str = "Datum") -> date:
    """Nimmt JJJJ-MM-TT und TT.MM.JJJJ — die Oberflaeche schickt ersteres."""
    if not wert:
        return date.today()
    if isinstance(wert, (date, datetime)):
        return datum_lesen(wert)
    text = str(wert).strip()
    for format in DATUMSFORMATE:
        try:
            return datetime.strptime(text, format).date()
        except ValueError:
            continue
    raise Eingabefehler(f"{feld}: „{wert}“ ist kein Datum (erwartet TT.MM.JJJJ).")


def ort_aus(wert) -> str:
    ort = str(wert or "zuhause").strip().lower()
    if ort not in ORTE:
        raise Eingabefehler(
            f"Ort: „{wert}“ kenne ich nicht (zuhause, auswaerts oder pv).")
    return ort


def ladung_aus_daten(daten: dict) -> dict:
    """Liest einen Eintrag — der Preis darf als ct/kWh oder als Summe kommen.

    Zuhause weiss man den Arbeitspreis, unterwegs steht der Betrag auf der
    Quittung. Beides ist zulaessig; gespeichert wird immer die Summe, und bei
    Eingabe je kWh zusaetzlich der Tarif, damit die Eingabe unveraendert
    zurueckkommt, wenn der Eintrag spaeter geaendert wird.

    Beim Ueberschussladen (ort "pv") gilt der Arbeitspreis nur fuer den Teil,
    der doch aus dem Netz kam — zieht eine Wolke auf, bevor die Regelung
    nachkommt. Ohne Angabe ist dieser Teil 0 und die Ladung hat nichts gekostet.
    """
    kwh = zahl(daten.get("kwh"), "Geladene Energie", minimum=0.0)
    ort = ort_aus(daten.get("ort"))

    netz = daten.get("netz_kwh")
    hat_netz = ort == "pv" and netz is not None and str(netz).strip() != ""
    netz_kwh = zahl(netz, "Netzbezug", minimum=0.0) if hat_netz else None
    if netz_kwh is not None and netz_kwh > kwh:
        raise Eingabefehler(
            f"Netzbezug: {netz_kwh:g} kWh sind mehr, als überhaupt geladen wurde "
            f"({kwh:g} kWh).")

    ct = daten.get("ct_kwh")
    hat_ct = ct is not None and str(ct).strip() != ""

    if hat_ct:
        tarif = zahl(ct, "Preis je kWh", minimum=0.0) / 100.0
        # Bezahlt wird nur, was aus dem Netz kam — bei PV also der Netzanteil.
        kosten = ((netz_kwh or 0.0) if ort == "pv" else kwh) * tarif
    else:
        tarif = None
        kosten = zahl(daten.get("kosten"), "Kosten der Ladung", minimum=0.0,
                      pflicht=ort != "pv")

    soc = daten.get("soc")
    hat_soc = soc is not None and str(soc).strip() != ""

    return {
        "datum": datum_aus(daten.get("datum")),
        "km": zahl(daten.get("km"), "Kilometerstand"),
        "kwh": kwh,
        "netz_kwh": netz_kwh,
        "kosten": kosten,
        "notiz": str(daten.get("notiz") or "").strip()[:200],
        "ort": ort,
        "tarif": tarif,
        "soc": zahl(soc, "Ladestand", minimum=0.0, hoechstens=100.0) if hat_soc else None,
    }


def _differenz(daten: dict, name: str, feld: str, pflicht: bool = True) -> float | None:
    """Aus Start- und Endstand eines Zaehlers die Menge im Fenster.

    Ein leerer Startstand heisst: da steht schon die Differenz. So kann man
    ablesen (zwei Staende) oder rechnen lassen, was die Automation spaeter liefert.
    """
    ende = daten.get(f"{name}_bis")
    if ende is None or str(ende).strip() == "":
        if pflicht:
            raise Eingabefehler(f"{feld}: der Endstand fehlt.")
        return None
    bis = zahl(ende, f"{feld} (Ende)", minimum=0.0)
    von = zahl(daten.get(f"{name}_von"), f"{feld} (Start)", minimum=0.0, pflicht=False)
    if bis < von:
        raise Eingabefehler(
            f"{feld}: der Endstand {bis:g} liegt unter dem Startstand {von:g} — "
            f"ein Zähler läuft nicht rückwärts.")
    return bis - von


def ueberschuss_aus_daten(daten: dict, tarif: float) -> dict:
    """Rechnet eine Ladung aus Zaehlerstaenden auf — und speichert nichts."""
    return ueberschuss(
        bezug=_differenz(daten, "bezug", "Netzbezug 1.8.0"),
        einspeisung=_differenz(daten, "einspeisung", "Einspeisung 2.8.0"),
        ladung=_differenz(daten, "ladung", "Ins Auto geladen"),
        erzeugung=_differenz(daten, "erzeugung", "PV-Erzeugung", pflicht=False),
        tarif=tarif,
    )


def zustand() -> dict:
    """Alles, was die Oberflaeche braucht — in einer Antwort."""
    werte = speicher.einstellungen()
    liste = speicher.ladungen()
    ergebnis = auswerten(
        liste,
        benzinpreis=float(werte["benzinpreis"]),
        benzinverbrauch=float(werte["benzinverbrauch"]),
        kapazitaet=float(werte.get("kapazitaet") or 0.0),
    )
    return {
        "version": __version__,
        "heute": date.today().isoformat(),
        "einstellungen": werte,
        "ladungen": [
            {
                "id": l.id,
                "datum": l.datum.isoformat(),
                "km": l.km,
                "kwh": l.kwh,
                "netz_kwh": l.netz_kwh,
                "kosten": l.kosten,
                "notiz": l.notiz,
                "ort": l.ort,
                "tarif": l.tarif,
                "soc": l.soc,
            }
            for l in liste
        ],
        "auswertung": ergebnis,
    }


def csv_export() -> bytes:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(
        ["Datum", "Kilometerstand", "kWh", "davon Netz kWh", "Kosten EUR", "ct/kWh",
         "Ladestand %", "Ort", "Notiz"])
    for l in speicher.ladungen():
        schreiber.writerow([
            l.datum.isoformat(),
            f"{l.km:.1f}".replace(".", ","),
            f"{l.kwh:.3f}".replace(".", ","),
            "" if l.netz_kwh is None else f"{l.netz_kwh:.3f}".replace(".", ","),
            f"{l.kosten:.2f}".replace(".", ","),
            f"{l.kosten / l.kwh * 100:.2f}".replace(".", ",") if l.kwh else "",
            "" if l.soc is None else f"{l.soc:.0f}",
            ORTSNAMEN[l.ort],
            l.notiz,
        ])
    return puffer.getvalue().encode("utf-8-sig")


# ----------------------------------------------------------------- Server

class Weg(BaseHTTPRequestHandler):
    server_version = f"Kostenberechnung/{__version__}"
    protocol_version = "HTTP/1.1"

    # --- Antworten

    def _senden(self, status: int, koerper: bytes, typ: str, kopf: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        for name, wert in (kopf or {}).items():
            self.send_header(name, wert)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def _json(self, daten, status: int = HTTPStatus.OK) -> None:
        koerper = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self._senden(status, koerper, "application/json; charset=utf-8",
                     {"Cache-Control": "no-store"})

    def _fehler(self, status: int, text: str) -> None:
        self._json({"fehler": text}, status)

    def _datei(self, name: str) -> None:
        ziel = (WEB / name).resolve()
        if not ziel.is_file() or WEB not in ziel.parents:
            self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden.")
            return
        typ = TYPEN.get(ziel.suffix, "application/octet-stream")
        kopf = {"Cache-Control": "no-cache"}
        self._senden(HTTPStatus.OK, ziel.read_bytes(), typ, kopf)

    def _koerper(self) -> dict:
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge <= 0:
            return {}
        if laenge > 1_000_000:
            raise Eingabefehler("Anfrage zu groß.")
        roh = self.rfile.read(laenge)
        try:
            daten = json.loads(roh.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Eingabefehler("Ungültige Daten geschickt.") from None
        if not isinstance(daten, dict):
            raise Eingabefehler("Ungültige Daten geschickt.")
        return daten

    # --- Verteiler

    def do_GET(self) -> None:  # noqa: N802
        self._bearbeiten("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._bearbeiten("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._bearbeiten("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._bearbeiten("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._bearbeiten("DELETE")

    def _bearbeiten(self, verb: str) -> None:
        pfad = urlparse(self.path).path.rstrip("/") or "/"
        try:
            self._route(verb, pfad)
        except Eingabefehler as fehler:
            self._fehler(HTTPStatus.BAD_REQUEST, str(fehler))
        except speicher.SpeicherFehler as fehler:
            self.log_error("Speicher: %s", fehler)
            self._fehler(HTTPStatus.INTERNAL_SERVER_ERROR, str(fehler))
        except BrokenPipeError:
            pass
        except Exception as fehler:  # pragma: no cover - letzte Rettung
            self.log_error("Fehler bei %s %s: %r", verb, pfad, fehler)
            self._fehler(HTTPStatus.INTERNAL_SERVER_ERROR, "Interner Fehler.")

    def _route(self, verb: str, pfad: str) -> None:
        if verb == "GET":
            if pfad == "/":
                return self._datei("index.html")
            if pfad == "/gesundheit":
                return self._json({"status": "ok", "version": __version__})
            if pfad == "/api/daten":
                return self._json(zustand())
            if pfad == "/api/export.csv":
                return self._senden(
                    HTTPStatus.OK, csv_export(), "text/csv; charset=utf-8",
                    {"Content-Disposition":
                     f'attachment; filename="ladungen-{date.today():%Y-%m-%d}.csv"'},
                )
            if pfad.count("/") == 1 and "." in pfad:
                return self._datei(pfad.lstrip("/"))
            return self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden.")

        if verb == "POST" and pfad == "/api/ueberschuss":
            # Reiner Rechner: er liest die Einstellungen und ruehrt sonst nichts an.
            werte = speicher.einstellungen()
            return self._json(ueberschuss_aus_daten(
                self._koerper(), float(werte["strompreis"]) / 100.0))

        if verb == "POST" and pfad == "/api/ladungen":
            speicher.ladung_anlegen(**ladung_aus_daten(self._koerper()))
            return self._json(zustand(), HTTPStatus.CREATED)

        if verb == "PUT" and pfad == "/api/einstellungen":
            daten = self._koerper()
            neu = {}
            if "benzinpreis" in daten:
                neu["benzinpreis"] = zahl(daten["benzinpreis"], "Benzinpreis", minimum=0.0)
            if "benzinverbrauch" in daten:
                neu["benzinverbrauch"] = zahl(
                    daten["benzinverbrauch"], "Benzinverbrauch", minimum=0.0)
            if "strompreis" in daten:
                neu["strompreis"] = zahl(daten["strompreis"], "Strompreis", minimum=0.0)
            if "kapazitaet" in daten:
                neu["kapazitaet"] = zahl(
                    daten["kapazitaet"], "Akkukapazität", minimum=0.0, hoechstens=500.0,
                    pflicht=False)
            if "fahrzeug" in daten:
                neu["fahrzeug"] = str(daten["fahrzeug"]).strip()[:60] or "Mein E-Auto"
            speicher.einstellungen_setzen(neu)
            return self._json(zustand())

        if pfad.startswith("/api/ladungen/") and verb in ("PUT", "DELETE"):
            rest = pfad[len("/api/ladungen/"):]
            if not rest.isdigit():
                raise Eingabefehler("Unbekannter Eintrag.")
            kennung = int(rest)
            if verb == "DELETE":
                if not speicher.ladung_loeschen(kennung):
                    return self._fehler(HTTPStatus.NOT_FOUND, "Eintrag gibt es nicht (mehr).")
                return self._json(zustand())
            if not speicher.ladung_aendern(kennung, **ladung_aus_daten(self._koerper())):
                return self._fehler(HTTPStatus.NOT_FOUND, "Eintrag gibt es nicht (mehr).")
            return self._json(zustand())

        self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden.")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        sys.stderr.write("%s  %s\n" % (
            datetime.now().strftime("%H:%M:%S"), format % args))


def eigene_adresse() -> str:
    """Die Adresse, unter der das Handy den Rechner findet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # geht nirgends hin, verraet nur das Interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description="Kostenberechnung E-Auto")
    zerleger.add_argument("--host", default=os.environ.get("KOSTEN_HOST", "0.0.0.0"))
    zerleger.add_argument("--port", type=int, default=int(os.environ.get("KOSTEN_PORT", "8080")))
    argumente = zerleger.parse_args(argv)

    try:
        speicher.anlegen()
    except speicher.SpeicherFehler as fehler:
        print(f"Abbruch: {fehler}", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((argumente.host, argumente.port), Weg)
    server.daemon_threads = True

    print(f"Kostenberechnung {__version__} — Daten in {speicher.pfad()}", flush=True)
    print(f"  lokal:    http://127.0.0.1:{argumente.port}", flush=True)
    if argumente.host in ("0.0.0.0", "::"):
        print(f"  im Netz:  http://{eigene_adresse()}:{argumente.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
