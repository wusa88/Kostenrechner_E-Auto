# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Weboberfläche zum Mitschreiben von Ladungen eines E-Autos: Kilometerstand, geladene
kWh, bezahlter Preis. Daraus entstehen Durchschnittsverbrauch, Stromkosten und eine
Gegenüberstellung mit den Kosten derselben Strecke als Benziner — monatlich und
jährlich. Läuft als Docker-Container im Heimnetz, bedienbar von mehreren Geräten.

## Befehle

```bash
python3 -m app.server --port 8385      # lokal starten, Daten in daten/kosten.json
python3 -m unittest discover -s tests  # alle Tests (aktuell 88)
python3 -m unittest tests.test_rechnung.Ladestand.test_gleicher_ladestand_aendert_nichts
python3 -m unittest discover -s tests -k ladestand     # nach Muster
docker compose up -d                   # Container, http://localhost:8385
```

Es gibt keinen Build-Schritt, keinen Linter und keine Abhängigkeiten. Änderungen an
`app/web/` wirken beim nächsten Neuladen der Seite; Änderungen an `app/*.py`
brauchen einen Neustart des Servers.

## Harte Regeln dieses Projekts

- **Nur Standardbibliothek.** Kein pip, kein CDN, keine externe Schrift, kein
  Framework — weder im Python noch im Frontend. Das hält das Abbild klein und den
  Portainer-Build vom Netz unabhängig. Wer eine Abhängigkeit braucht, hat das
  falsche Problem gelöst.
- **Deutsch als Sprache des Codes.** Module, Funktionen, Variablen, Kommentare und
  Oberfläche sind deutsch (`rechnung`, `speicher`, `ladung_anlegen`, `auswerten`).
  In Kommentaren und Bezeichnern stehen Umlaute als `ae/oe/ue` (`pruefbar`,
  `Abhaengigkeit`), in benutzersichtbaren Texten als echte Umlaute.
- **Geld wird nie modelliert.** Gerechnet wird ausschließlich mit dem, was
  tatsächlich bezahlt wurde. Energie darf korrigiert werden (siehe Ladestand und
  PV-Überschuss), Euro-Beträge nicht.
- **Unsinn wird gemeldet, nicht still verrechnet.** Fallende Kilometerstände,
  Ladungen ohne Strecke, kaputte Datei — jeweils eine Warnung im Klartext, statt
  weiterzurechnen oder Daten zu überschreiben.
- Version in `app/__init__.py` bei fachlichen Änderungen hochzählen.

## Aufbau

Drei Schichten, klar getrennt — das ist der Grund, warum der Rechenkern einzeln
prüfbar ist:

| Datei | Rolle |
|---|---|
| `app/rechnung.py` | reine Rechnung, kein I/O. Kennt nur `Ladung`-Objekte und gibt fertige Dicts zurück |
| `app/speicher.py` | die JSON-Datei: lesen, atomar schreiben, Werte prüfen |
| `app/server.py` | HTTP, Routen, Eingabeprüfung. Wandelt Benutzereingaben in saubere Werte |
| `app/web/` | eine HTML-, eine CSS-, eine JS-Datei, vanilla |

Der Server liefert bei **jeder** schreibenden Antwort den vollständigen neuen
Zustand (`zustand()` in `server.py`) — Ladungen, Einstellungen und die komplette
Auswertung. Die Oberfläche lädt darum nach dem Speichern nichts nach; sie ruft
`zeichnen(daten)` und zeichnet alles neu.

### Die Rechnung (der eigentliche Kern)

Alles hängt an einer Konvention, die man kennen muss, bevor man `rechnung.py`
anfasst:

**Eine Ladung füllt nach, was seit der letzten Ladung verbraucht wurde.** Die
Strecke zwischen zwei Kilometerständen wird also mit der Energie der *späteren*
Ladung bewertet. Daraus folgt:

- Die erste Ladung hat keine zugehörige Strecke und zählt **nicht** in Verbrauch
  und Vergleich. Ihr Geld erscheint nur in „Insgesamt geladen" (`bezahlt`) und in
  `aussen_vor`. Diese Doppelung ist Absicht und wird in der Oberfläche erklärt —
  sie sieht sonst wie ein Fehler aus.
- Exakt ist die Rechnung nur, wenn der Akku am Anfang und am Ende **gleich voll**
  ist (nicht „voll", sondern „gleich"). Beim E-Auto trifft das selten zu.

**Der Ladestand schließt genau diese Lücke.** Steht zu einer Ladung `soc`
(Prozent nach dem Laden) und in den Einstellungen die nutzbare `kapazitaet`:

```
verbrauchte Energie = geladene Energie + (Ladestand vorher − nachher) × Kapazität
```

Über eine Kette von Ladungen kürzen sich die Zwischenwerte weg — `korrektur()`
braucht deshalb nur den Ladestand der **ersten und letzten** Ladung einer Spanne,
und prüft dabei über `von_id`, dass die Kette lückenlos ist. Dieselbe Funktion
läuft über die Gesamtspanne, über jeden Monat, jedes Jahr und jede einzelne
Periode. Fehlt etwas davon, gibt es keine Korrektur und das Ergebnis bleibt als
`gemessen: false` markiert.

### PV-Überschuss

Ein dritter Ladeort neben `zuhause` und `auswaerts`: `pv`. Er sagt nichts über den
Ort, sondern über die **Herkunft** des Stroms, und er hat ein eigenes Feld,
`netz_kwh` — der Teil der Ladung, der doch aus dem Netz kam, weil eine Wolke
schneller war als die Regelung. Nur dieser Teil wird bepreist (`server.py`:
`kosten = netz_kwh × tarif`), der Rest ist mit 0 € genau das, was er war: nicht
bezahlt.

`nach_orten()` gibt für diese Zeile zusätzlich `pv_kwh` und `netz_kwh` aus. Damit

- bleibt der Ø-Preis unter `zuhause` der echte Arbeitspreis statt eines Mischwerts,
- steht die selbst geladene Energie als Zahl da — genau die, die die
  Amortisationsrechnung der Anlage als Eigenverbrauch braucht.

Die PV-Zeile trägt **zwei** Preise, und die dürfen nie zu einem verschmelzen:
`netz_preis_kwh` (Kosten ÷ Netzanteil) ist der Arbeitspreis, zu dem tatsächlich
gekauft wurde; `preis_kwh` (Kosten ÷ geladene Energie) ist der Schnitt über alles,
Gratis-Sonne eingerechnet. Nur der erste ist ein Preis, zu dem jemand etwas
gekauft hat — genau daran hat sich der Nutzer gestoßen, als die Oberfläche nur den
zweiten unter „Ø Preis" zeigte.

Die Energie zählt ganz normal in Strecke, Verbrauch und Vergleich; nur das Geld
fehlt. Die Gegenüberstellung fällt dadurch zugunsten des Autos aus, und die
Oberfläche sagt das unter „Wo geladen wurde" auch hin: der Wert dieser
Kilowattstunden gehört in die Amortisation der Anlage, sonst wird dieselbe kWh
zweimal gutgeschrieben.

### Der Überschussrechner

`ueberschuss()` in `rechnung.py` ist ein **Nebenwerkzeug ohne Speicher**: aus den
Zählerdifferenzen eines Ladefensters (1.8.0 Bezug, 2.8.0 Einspeisung, Erzeugung,
geladene kWh) fällt der Netzanteil, den man oben von Hand einträgt. Route
`POST /api/ueberschuss` — sie liest die Einstellungen und schreibt nichts.

Der Grund für die eigene Funktion ist die eine Frage, die kein Zähler beantwortet:
**wem gehört der Netzbezug?** Während einer Wolke ziehen Haus und Auto
gleichzeitig. Also gibt es keine Zahl, sondern eine Spanne — `min(Bezug, Ladung)`
oben, `max(0, Bezug − Restlast)` unten, dazu die anteilige Rechnung. Vorgeschlagen
wird die Obergrenze: sie passt zur Regelung (die PV bedient zuerst das Haus, das
Auto bekommt den Überschuss, also fällt der Fehlbetrag dem Auto zu) und ist die
konservative Wahl. Ohne Erzeugung bleibt der Vorschlag, aber die Spanne entfällt —
dieselbe Logik wie beim Ladestand: lieber ungenau und gekennzeichnet als falsch
genau.

Er rechnet nur richtig, wenn die abgelesenen Stände das **Ladefenster** einrahmen.
Steht der Abend mit drin, wird dem Auto der Netzbezug des Hauses zugeschrieben;
die Oberfläche sagt das dazu.

`verlaesslichkeit()` beziffert, wie groß der Spielraum ohne Ladestand noch ist:
größte je eingetragene Ladung ÷ Strecke. Solange der über einem Sechstel des
Verbrauchs liegt, meldet die Oberfläche „vorläufig", statt eine wackelige Zahl
als gesichert auszugeben.

### Datenhaltung

Eine JSON-Datei, Pfad aus `KOSTEN_DATEI` (Container: `/daten/kosten.json`). Sie ist
ausdrücklich von Hand bearbeitbar: `_lesen()` füllt fehlende Felder mit Standards
auf, versteht `1,89` wie `1.89` und fängt unbekannte Werte ab. `_schreiben()`
schreibt erst in eine Nebendatei und hängt sie per `os.replace` um; außerdem
rundet es Fließkomma-Rauschen weg, damit die Datei lesbar bleibt. Kaputtes JSON
wirft `SpeicherFehler` — die Datei wird dann **nicht** angefasst.

Eine `kosten.db` aus Fassung 1.0 wird beim ersten Start einmalig übernommen
(`_aus_sqlite`), die alte Datei bleibt liegen.

### Eingaben aus der Oberfläche

`server.py` ist die einzige Stelle, die mit unsauberen Werten rechnet, und nimmt
sie großzügig entgegen: `_text_zu_zahl()` liest `12,5` wie `12.5` und `10.000` als
Zehntausend; `datum_aus()` nimmt `TT.MM.JJJJ` wie `JJJJ-MM-TT`. Der Preis kommt
entweder als `kosten` (Summe) oder als `ct_kwh` — im zweiten Fall wird `kosten`
daraus gerechnet und `tarif` (EUR/kWh) zusätzlich gespeichert, damit ein Eintrag
beim Ändern so zurückkommt, wie er eingetippt wurde.

Das Datumsfeld ist bewusst ein Textfeld: ein natives `<input type="date">` zeigt
das Format der Browsersprache, was bei englischer Einstellung `MM/DD/YYYY` ergibt.
Der Knopf daneben öffnet über `showPicker()` trotzdem den Kalender.

## Tests

`tests/test_rechnung.py` prüft die Zusagen der Methodik gegen von Hand
nachgerechnete Beispiele — inklusive der Fälle, die aus echten Rückfragen
entstanden sind (kurze Strecke, Teilladung, gerissene Kette). `tests/test_speicher.py`
prüft Datei, Handarbeit und kaputtes JSON, `tests/test_server.py` fährt den echten
Server auf einem freien Port hoch. Alle drei arbeiten gegen ein
Temporärverzeichnis; die eigenen Daten bleiben unberührt.

Wer an der Rechnung etwas ändert, ändert eine Zusage — die Tests sind dort die
Dokumentation dieser Zusagen, nicht bloß Absicherung.

## Nicht vorhanden, mit Absicht

Kein Login (der Server gehört ins Heimnetz, sonst hinter einen Reverse-Proxy),
keine Preishistorie (der eingestellte Benzinpreis gilt auch rückwirkend), keine
Prognose über Preisentwicklungen.
