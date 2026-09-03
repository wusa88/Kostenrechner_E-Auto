# Kostenberechnung E-Auto

Trägt man nach jeder Ladung Kilometerstand, geladene kWh und den bezahlten
Betrag ein, rechnet diese Oberfläche daraus den Durchschnittsverbrauch, die
Stromkosten je 100 km und stellt daneben, was dieselbe Strecke als Benziner
gekostet hätte — pro Monat und pro Jahr.

Läuft als Docker-Container im Heimnetz und ist damit von Handy, Tablet und
Rechner gleichzeitig bedienbar. Keine Abhängigkeiten, kein CDN, keine
Verbindung nach draußen: nur Python-Standardbibliothek und eine JSON-Datei.

## Schnellstart

```bash
docker compose up -d
```

Danach `http://<adresse-des-servers>:8385` im Browser öffnen.

### Als Portainer-Stack aus GitHub

1. In Portainer **Stacks → Add stack → Repository**.
2. Repository-URL dieses Projekts eintragen, Compose-Pfad `docker-compose.yml`.
3. **Deploy**. Portainer baut das Abbild selbst — es muss nichts vorbereitet sein.

Wer nicht bei jedem Update neu bauen will, lässt den Workflow
`.github/workflows/abbild.yml` das Abbild nach `ghcr.io` schieben und ersetzt in
der `docker-compose.yml` das `build: .` durch

```yaml
image: ghcr.io/<benutzer>/kostenberechnung:latest
```

### Ohne Docker

```bash
python3 -m app.server --port 8385
```

Python 3.10 oder neuer, sonst nichts.

## Bedienung

**Eintragen.** Datum, Kilometerstand, geladene Energie — und der Preis. Punkt und
Komma dürfen beide getippt werden: `41,2` und `41.2` sind dasselbe, `26.240` sind
sechsundzwanzigtausendzweihundertvierzig.

Das **Datum** steht als `TT.MM.JJJJ` da — unabhängig davon, welche Sprache im
Browser eingestellt ist. (Ein natives `<input type="date">` richtet sich nach der
Browsersprache und zeigt bei englischer Einstellung `MM/DD/YYYY`; deshalb ist es
hier ein Textfeld.) Getippt werden darf großzügig: `3.9.26`, `3/9/2026` und
`2026-09-03` landen alle auf dem 3. September 2026, und beim Verlassen des Feldes
wird sauber ausgeschrieben. Der Knopf daneben öffnet den Kalender des Browsers —
am Handy der bequemere Weg.

**Zwei Schalter für den Preis**, weil man je nach Ladeort etwas anderes weiß:

| Schalter | Wahl | wofür |
|---|---|---|
| Ladeort | *Zuhause* / *Auswärts* | Zuhause füllt den Haustarif vor. Außerdem trennt die Übersicht danach: wie viel kam aus der eigenen Steckdose, zu welchem Preis. |
| Eingabeart | *ct/kWh* / *Summe €* | Zuhause kennt man den Arbeitspreis, unterwegs steht der Betrag auf der Quittung. |

Die beiden hängen nicht aneinander: Auch auswärts darf man den Preis je kWh
eintragen — viele Säulen rechnen genau so ab. Nur wenn eine Standgebühr oder ein
Sessionpreis dazukommt, ist der Betrag von der Quittung die Wahrheit, denn den
kann man aus dem kWh-Preis nicht mehr zurückrechnen.

Der **Ladestand danach** ist optional — was er bringt, steht weiter unten unter
*Genau statt geschätzt*.

Unter dem Feld steht immer live die andere Darstellung — `41,2 kWh × 34,0 ct =
14,01 €` beziehungsweise `27,84 € ÷ 41,2 kWh = 67,6 ct/kWh`. Ein Vertipper fällt
so sofort auf. Wer die Eingabeart umschaltet, nachdem er schon etwas eingetragen
hat, bekommt den Wert umgerechnet statt gelöscht.

Gespeichert wird immer der Gesamtbetrag; bei Eingabe je kWh zusätzlich der Tarif,
damit ein Eintrag beim späteren Ändern so zurückkommt, wie er eingetippt wurde.
Gerechnet wird ausschließlich mit dem Betrag — der Ladeort sortiert nur.

**Die erste Ladung ist nur der Startpunkt.** Ab der zweiten entsteht eine
Strecke — und damit ein Verbrauch.

**Ändern und Löschen** direkt in der Tabelle. **CSV herunterladen** gibt alle
Einträge als Semikolon-Datei heraus — mit Betrag, ct/kWh und Ladeort —, die Excel
und LibreOffice ohne Nachfrage öffnen.

## Wie gerechnet wird

Eine Ladung füllt nach, was seit der letzten Ladung verbraucht wurde. Die
Strecke zwischen zwei Kilometerständen wird deshalb mit der Energie der
**späteren** Ladung bewertet:

```
Verbrauch (kWh/100 km) = kWh dieser Ladung / gefahrene km seit der letzten Ladung × 100
```

Über den Gesamtzeitraum summiert sich das zu allen gefahrenen Kilometern gegen
alle Ladungen ab der zweiten.

### Warum der Verbrauch am Anfang schwankt

Der Rechner sieht nur, was geladen wurde — **nicht, wie voll der Akku ist**. Genau
das fehlt aber zur Rechnung. Ein Beispiel:

| | |
|---|---|
| 1. Eintrag | 34 962 km, 27,9 kWh geladen |
| 2. Eintrag | 35 096 km, 12,0 kWh geladen |

134 km gefahren, danach 12 kWh nachgeladen — macht 9,0 kWh/100 km. Gefahren
wurden aber eher 23 kWh; der Rest kam aus dem Akku, der jetzt entsprechend leerer
ist. Die 27,9 kWh der ersten Ladung sind dabei **nicht** mitgerechnet (sonst kämen
29,8 heraus): Was vor der ersten Ladung gefahren wurde, weiß der Rechner nicht,
also ist sie nur der Startpunkt der Strecke.

Der Fehler ist immer derselbe: der Unterschied im Ladestand zwischen der ersten
und der letzten Ladung. Er wächst nicht mit — der Akku bleibt gleich groß, die
Strecke wird länger. Nach 134 km sind das ±20,8 kWh/100 km, nach 14 000 km noch
±0,4. Deshalb schreibt die Übersicht dazu, **wie groß dieser Spielraum gerade
ist**, solange er ins Gewicht fällt, statt eine Zahl als gesichert auszugeben.

Als Maß für den möglichen Ladehub nimmt der Rechner die größte je eingetragene
Ladung — der beste Anhaltspunkt, den die Daten selbst hergeben.

Nebenbei: Es geht **nicht um „voll"**, sondern um „gleich". Beim Verbrenner sagt
man volltanken, weil das der einzige Füllstand ist, den man zuverlässig
wiedertrifft — nötig ist aber nur derselbe Stand am Anfang und am Ende. Beim
E-Auto trifft das selten zu, und genau deshalb gibt es den nächsten Abschnitt.

### Genau statt geschätzt: der Ladestand

Trägst du zu einer Ladung den **Ladestand in Prozent nach dem Laden** ein und
hinterlegst unter *Einstellungen* die **nutzbare Akkukapazität**, wird aus der
Schätzung eine Messung:

```
verbrauchte Energie = geladene Energie + (Ladestand vorher − nachher) × Kapazität
```

Das Feld ist optional; leer bleibt es bei der bisherigen Rechnung. Und es genügt,
es **selten** auszufüllen: Über eine Kette von Ladungen kürzen sich die
Zwischenwerte weg, für eine Spanne zählen nur der Ladestand ihrer ersten und
ihrer letzten Ladung. Wer nur zweimal im Jahr hinsieht, bekommt für das Jahr
trotzdem den exakten Wert — nur die einzelnen Perioden dazwischen bleiben
geschätzt.

Beispiel, gegengerechnet an einem simulierten Auto mit 18,50 kWh/100 km und
völlig unregelmäßigen Teilladungen zwischen 8 und 50 kWh:

| | Ergebnis |
|---|---|
| ohne Ladestand | 11,32 kWh/100 km |
| mit erstem und letztem Prozentwert | **18,50 kWh/100 km** (exakt) |

Ausgeglichen wird nur die **Energie**, nicht das Geld: Bezahlt wurde, was bezahlt
wurde. Wer am Ende wenig nachlädt, hat für die gefahrene Strecke scheinbar wenig
bezahlt — auf die Kostenseite schlägt der Ladestand also weiterhin nur über die
Zeit durch. Bei Monats- und Jahressummen fällt das kaum ins Gewicht.

Noch eine Einordnung: Der Verbrauch dieser Rechnung ist der **ab Steckdose**,
inklusive Ladeverlusten. Er liegt naturgemäß rund 10 % über dem, was der
Bordcomputer anzeigt — das ist kein Fehler, sondern genau das, wofür du bezahlst.

Der Benzinvergleich nimmt dieselbe Strecke:

```
Liter    = Strecke × Verbrauch des Benziners / 100
Benzin € = Liter × Benzinpreis
Ersparnis = Benzinkosten − Stromkosten
```

**Monatlich und jährlich** ist eine Hochrechnung aus dem gemessenen Zeitraum:
gefahrene Kilometer geteilt durch die Tage zwischen erster und letzter Ladung,
mal 30,44 beziehungsweise 365,25. Sie sagt, was bei gleichbleibender
Fahrleistung zusammenkommt — sie ist keine Prognose über Preise.

Die Tabelle **Verlauf** zeigt daneben die tatsächlichen Kalendermonate und
-jahre. Eine Ladung zählt dabei in den Monat ihres Datums; sie wird nicht
anteilig über den Monatswechsel verteilt.

**Was im Vergleich steckt:** alle Ladungen ab der zweiten. Die Übersicht schreibt
dazu, wie viele das sind und was die erste gekostet hat. In *Insgesamt geladen*
steht dagegen jede Ladung — das ist das Geld, das tatsächlich weg ist.

**Was gemeldet statt still verrechnet wird:** ein Kilometerstand, der unter dem
vorherigen liegt (Tippfehler — die Periode bleibt draußen), und eine Ladung ohne
gefahrene Kilometer (die Energie zählt, ein Verbrauch entsteht daraus nicht).
Was insgesamt bezahlt wurde, steht unabhängig davon in der Übersicht: dort
zählen alle Ladungen, auch die erste.

## Vorbelegungen

| Wert | Vorbelegt mit | Wofür |
|---|---|---|
| Benzinpreis | 1,75 €/l | die Gegenüberstellung |
| Verbrauch Benziner | 7,2 l/100 km | die Gegenüberstellung |
| Haustarif | 34 ct/kWh | füllt das Preisfeld vor, wenn *Zuhause* gewählt ist |
| Nutzbare Akkukapazität | 0 (= unbekannt) | nur nötig, wenn du den Ladestand mitschreibst |

Alle drei sind in der Oberfläche unter **Einstellungen** änderbar und stehen in
der Datendatei. Die Gegenüberstellung rechnet immer mit dem *aktuell*
eingestellten Benzinpreis — auch rückwirkend. Wer den Preis ändert, ändert damit
auch, was der Vergleich für vergangene Monate ausweist.

## Daten

Alles steht in **einer JSON-Datei** — im Container unter `/daten/kosten.json`,
das Volume heißt `kosten-daten`. Ohne Docker liegt sie unter `daten/kosten.json`,
oder wo `KOSTEN_DATEI` hinzeigt.

```json
{
  "format": 1,
  "einstellungen": {
    "benzinpreis": 1.75,
    "benzinverbrauch": 7.2,
    "strompreis": 34.0,
    "kapazitaet": 0,
    "fahrzeug": "Mein E-Auto"
  },
  "ladungen": [
    {
      "id": 1,
      "datum": "2026-05-02",
      "km": 24100,
      "kwh": 38.4,
      "kosten": 11.9,
      "tarif": 0.31,
      "soc": 80,
      "ort": "zuhause",
      "notiz": "",
      "angelegt": "2026-05-02T18:20:11+00:00"
    }
  ]
}
```

`kosten` ist immer der Gesamtbetrag in Euro, `tarif` der Preis in **Euro** je kWh
(oder `null`, wenn als Summe eingetragen), `soc` der Ladestand in Prozent nach dem
Laden (oder `null`). Sichern heißt: diese Datei kopieren.

```bash
docker compose cp kostenberechnung:/daten/kosten.json ./sicherung.json
```

**Von Hand bearbeiten** ist ausdrücklich vorgesehen — für eine Korrektur, einen
Import aus einer alten Liste oder das Nachtragen von Hand. Fehlende Felder werden
mit Standardwerten aufgefüllt, `1,89` genauso verstanden wie `1.89`, und ein
unbekannter Ort fällt auf `zuhause` zurück. Zwei Dinge dabei:

- **Container vorher anhalten** (`docker compose stop`). Der Server hält den Stand
  nicht im Speicher, aber sein nächstes Schreiben würde deine Änderung überholen.
- Ist die Datei kaputt, sagt der Rechner das und rührt sie **nicht** an, statt mit
  leerem Bestand weiterzumachen.

Geschrieben wird atomar: erst vollständig in eine Nebendatei, dann per
`os.replace` an ihren Platz. Ein Stromausfall mitten im Speichern kann die Datei
damit nicht halb beschrieben zurücklassen.

Wer noch die erste Fassung mit `kosten.db` laufen hatte: die wird beim ersten
Start einmalig eingelesen und nach `kosten.json` übernommen. Die alte Datei bleibt
unangetastet liegen und darf gelöscht werden, sobald alles da ist.

## Einstellbar über die Umgebung

| Variable | Standard | Bedeutung |
|---|---|---|
| `KOSTEN_DATEI` | `/daten/kosten.json` | Pfad der Datendatei |
| `KOSTEN_HOST` | `0.0.0.0` | Adresse, auf der gelauscht wird |
| `KOSTEN_PORT` | `8080` | Port im Container |

## Schnittstelle

Für ein Skript, das später einmal automatisch einträgt:

| Weg | Zweck |
|---|---|
| `GET /api/daten` | Ladungen, Einstellungen und die komplette Auswertung |
| `POST /api/ladungen` | `{"datum","km","kwh","notiz","ort","soc"}` plus **entweder** `kosten` (€) **oder** `ct_kwh` |
| `PUT /api/ladungen/<id>` | dasselbe, ändert einen Eintrag |
| `DELETE /api/ladungen/<id>` | löscht einen Eintrag |
| `PUT /api/einstellungen` | `{"benzinpreis","benzinverbrauch","strompreis","kapazitaet","fahrzeug"}` |
| `GET /api/export.csv` | alle Einträge als CSV |
| `GET /gesundheit` | für den Healthcheck |

`ort` ist `zuhause` (Standard) oder `auswaerts`, `soc` der Ladestand in Prozent
(0–100, weglassbar). Wird `ct_kwh` mitgeschickt, ergibt
sich `kosten` daraus; sonst gilt der übergebene Betrag.

```bash
# zuhause, Preis je kWh
curl -X POST http://127.0.0.1:8385/api/ladungen \
  -H 'Content-Type: application/json' \
  -d '{"datum":"2026-09-03","km":26240,"kwh":72.4,"ct_kwh":34,"ort":"zuhause"}'

# unterwegs, Betrag von der Quittung
curl -X POST http://127.0.0.1:8385/api/ladungen \
  -H 'Content-Type: application/json' \
  -d '{"datum":"2026-09-03","km":26240,"kwh":72.4,"kosten":43.90,"ort":"auswaerts"}'
```

Jede schreibende Antwort enthält den vollständigen neuen Zustand — die Oberfläche
muss nach dem Speichern nichts nachladen.

## Kein Login

Der Server fragt nicht nach einem Passwort. Er gehört ins eigene Netz. Soll er
von außen erreichbar sein, dann hinter einen Reverse-Proxy mit Authentifizierung
(Caddy, Traefik, Nginx Proxy Manager) — nicht per Portweiterleitung ins Internet.

## Prüfen

```bash
python3 -m unittest discover -s tests -v
```

63 Tests: der Rechenkern gegen von Hand nachgerechnete Beispiele, die
Datenhaltung samt Handarbeit an der Datei und kaputtem JSON, und die
Weboberfläche von außen — alles gegen ein Temporärverzeichnis.

## Dateien

| Datei | Zweck |
|---|---|
| `app/rechnung.py` | der Rechenkern — Verbrauch, Kosten, Vergleich, Hochrechnung |
| `app/speicher.py` | die JSON-Datei: lesen, atomar schreiben, prüfen |
| `app/server.py` | HTTP-Server, Schnittstelle, Eingabeprüfung |
| `app/web/` | Seite, Stil, Skript — je eine Datei |
| `tests/` | Rechenkern, Datenhaltung und Oberfläche |
| `Dockerfile`, `docker-compose.yml` | der Container |
| `.github/workflows/` | Tests bei jedem Push, Abbild nach ghcr.io |

## Lizenz

MIT — siehe [LICENSE](LICENSE).
