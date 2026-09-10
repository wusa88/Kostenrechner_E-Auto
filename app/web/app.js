/* Kostenberechnung E-Auto — Oberfläche. Vanilla JS, keine Abhängigkeiten. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  let zustand = null;
  let sicht = "monate";
  let ort = "zuhause";
  let preisart = "tarif";      // tarif = ct/kWh | summe = Gesamtbetrag in Euro
  let preisIstVorschlag = false;   // steht im Preisfeld nur der vorgeschlagene Haustarif?

  // ------------------------------------------------------------ Formate

  const zahlFormat = (min, max) =>
    new Intl.NumberFormat("de-DE", { minimumFractionDigits: min, maximumFractionDigits: max });

  const f0 = zahlFormat(0, 0);
  const f1 = zahlFormat(1, 1);

  const leer = "–";
  const da = (w) => w !== null && w !== undefined && isFinite(w);

  const euro = (w, k = 2) => (da(w) ? zahlFormat(k, k).format(w) + " €" : leer);
  const km = (w) => (da(w) ? f0.format(w) + " km" : leer);
  const kwh = (w) => (da(w) ? f1.format(w) + " kWh" : leer);
  const liter = (w) => (da(w) ? f1.format(w) + " l" : leer);
  const zahl1 = (w) => (da(w) ? f1.format(w) : leer);
  const ct = (w) => (da(w) ? f1.format(w * 100) + " ct" : leer);   // aus EUR/kWh

  const datumDe = (iso) => {
    const t = new Date(iso + "T00:00:00");
    return isNaN(t) ? iso : t.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  };

  /* Was getippt wurde -> JJJJ-MM-TT, oder null. Nimmt 3.9.26 genauso wie 03.09.2026. */
  const datumGelesen = (text) => {
    const t = String(text ?? "").trim();
    if (!t) return null;

    const bauen = (jahr, monat, tag) => {
      const d = new Date(jahr, monat - 1, tag);
      if (d.getFullYear() !== jahr || d.getMonth() !== monat - 1 || d.getDate() !== tag) {
        return null;   // fängt den 31.02. ab
      }
      const zwei = (z) => String(z).padStart(2, "0");
      return `${jahr}-${zwei(monat)}-${zwei(tag)}`;
    };

    let m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (m) return bauen(+m[1], +m[2], +m[3]);

    m = t.match(/^(\d{1,2})[.,\/\s-]+(\d{1,2})[.,\/\s-]+(\d{2}|\d{4})\.?$/);
    if (m) return bauen(+m[3] < 100 ? 2000 + +m[3] : +m[3], +m[2], +m[1]);

    return null;
  };

  const sicher = (text) =>
    String(text ?? "").replace(/[&<>"']/g, (z) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));

  const komma = (w, k) => (da(w) ? w.toFixed(k).replace(".", ",") : "");

  /* Liest, was getippt wurde — 12,5 und 12.5 gleichermaßen, 10.000 als Zehntausend. */
  const gelesen = (text) => {
    let t = String(text ?? "").trim().replace(/[€\s]/g, "");
    if (t.includes(",") && t.includes(".")) t = t.replace(/\./g, "").replace(",", ".");
    else if (t.includes(",")) t = t.replace(",", ".");
    else if (/^[+-]?[1-9]\d{0,2}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
    const w = parseFloat(t);
    return isFinite(w) ? w : null;
  };

  const haustarif = () =>
    zustand ? gelesen(zustand.einstellungen.strompreis) : null;   // in ct/kWh

  // ------------------------------------------------------------ Netzwerk

  async function ruf(pfad, optionen = {}) {
    const antwort = await fetch(pfad, {
      headers: { "Content-Type": "application/json" },
      ...optionen,
    });
    let daten = null;
    try { daten = await antwort.json(); } catch (e) { /* leere Antwort */ }
    if (!antwort.ok) throw new Error((daten && daten.fehler) || "Der Server hat abgelehnt.");
    return daten;
  }

  function melden(text, art = "gut") {
    const feld = $("meldung");
    feld.textContent = text;
    feld.className = "meldung " + art;
    feld.hidden = !text;
    if (text && art === "gut") setTimeout(() => { feld.hidden = true; }, 4000);
  }

  // ------------------------------------------------------------- Anzeige

  function zeichnen(daten) {
    zustand = daten;
    const e = daten.einstellungen;
    const a = daten.auswertung;

    $("fahrzeugname").textContent = e.fahrzeug || "E-Auto";
    document.title = "Kostenberechnung " + (e.fahrzeug || "E-Auto");
    $("version").textContent = "v" + daten.version;

    if (!$("e_benzinpreis").matches(":focus")) $("e_benzinpreis").value = komma(gelesen(e.benzinpreis), 2);
    if (!$("e_benzinverbrauch").matches(":focus")) $("e_benzinverbrauch").value = komma(gelesen(e.benzinverbrauch), 1);
    if (!$("e_strompreis").matches(":focus")) $("e_strompreis").value = komma(gelesen(e.strompreis), 1);
    if (!$("e_kapazitaet").matches(":focus")) $("e_kapazitaet").value = komma(gelesen(e.kapazitaet), 1);
    if (!$("e_fahrzeug").matches(":focus")) $("e_fahrzeug").value = e.fahrzeug || "";

    if (!$("f_datum").value) datumSetzen(daten.heute);

    uebersicht(a);
    orte(a);
    vergleich(a, e);
    zusammenfassung(a);
    verlauf(a);
    liste(daten, a);
    warnungen(a);
    preisHinweis();
  }

  function uebersicht(a) {
    const g = a.gesamt;
    $("k_verbrauch").textContent = g ? zahl1(g.verbrauch) : leer;
    $("k_preis_kwh").textContent = g && da(g.preis_kwh) ? f1.format(g.preis_kwh * 100) : leer;
    $("k_strecke").textContent = g ? f0.format(g.strecke) : leer;
    $("k_bezahlt").textContent = euro(a.bezahlt.kosten, 2);
    $("k_bezahlt_klein").textContent =
      a.anzahl ? `${f1.format(a.bezahlt.kwh)} kWh in ${a.anzahl} Ladung${a.anzahl === 1 ? "" : "en"}` : "€";

    const z = a.zeitraum;
    $("zeitraum").textContent = z
      ? `Ausgewertet vom ${datumDe(z.von)} bis ${datumDe(z.bis)} — ${f0.format(z.tage)} Tage.`
      : a.anzahl === 1
        ? "Erst ab der zweiten Ladung entsteht eine Strecke und damit ein Verbrauch."
        : "Noch keine Auswertung möglich.";

    vorlaeufig(a);
  }

  /* Sagt, wie belastbar der Verbrauch schon ist — statt eine Zahl vorzugeben,
     die sich mit der nächsten Ladung noch halbieren kann. */
  function vorlaeufig(a) {
    const feld = $("vorlaeufig");
    const v = a.verlaesslichkeit;
    const g = a.gesamt;
    if (!g || !v) { feld.hidden = true; return; }
    feld.hidden = false;

    // 1. Ladestand vorhanden und verrechnet: der Verbrauch ist gemessen.
    if (v.gemessen) {
      const A = v.ausgleich;
      const richtung = Math.abs(A) < 0.05
        ? "Der Akku stand am Anfang und am Ende gleich — nichts auszugleichen."
        : A > 0
          ? `Der Akku war am Ende leerer als am Anfang; die fehlenden ` +
            `<strong>${kwh(A)}</strong> sind eingerechnet.`
          : `Der Akku war am Ende voller als am Anfang; die zusätzlichen ` +
            `<strong>${kwh(-A)}</strong> sind herausgerechnet.`;
      feld.innerHTML =
        `<strong>Mit dem Ladestand gerechnet.</strong> ${richtung} Der Verbrauch ist ` +
        `damit gemessen, nicht geschätzt. In den Kosten steckt diese Energie nicht — ` +
        `bezahlt wurde, was bezahlt wurde.`;
      return;
    }

    // 2. Ladestände da, aber keine Kapazität: ein Feld fehlt noch.
    const kapazitaet = zustand ? gelesen(zustand.einstellungen.kapazitaet) : null;
    if (v.mit_ladestand > 0 && !kapazitaet) {
      feld.innerHTML =
        `<strong>Fast.</strong> Du schreibst den Ladestand mit — es fehlt nur noch die ` +
        `<strong>nutzbare Akkukapazität</strong> unten in den Einstellungen. Damit wird ` +
        `aus dem geschätzten Verbrauch ein gemessener.`;
      return;
    }

    // 3. Gar nichts da: sagen, wie groß der Spielraum ist.
    if (!v.vorlaeufig || !da(v.spanne)) { feld.hidden = true; return; }
    feld.innerHTML =
      `<strong>Noch vorläufig.</strong> Der Rechner weiß nicht, wie voll der Akku ` +
      `am Anfang und am Ende war — er sieht nur, was du geladen hast. Lädst du nach ` +
      `einer Strecke weniger nach, als du verfahren hast, fällt der Verbrauch zu ` +
      `niedrig aus; lädst du mehr, zu hoch. Auf ${km(g.strecke)} macht das bis zu ` +
      `<strong>±${zahl1(v.spanne)} kWh/100 km</strong> aus. Genauer wird es von selbst ` +
      `mit jedem Kilometer — oder sofort, wenn du bei zwei Ladungen den Ladestand ` +
      `mitschreibst und unten die Akkukapazität einträgst.`;
  }

  function orte(a) {
    $("orte").innerHTML = a.orte.map((o) => `
      <div class="block">
        <h3 class="ortname"><span class="punkt ${o.ort}"></span>${sicher(o.titel)}</h3>
        <dl>
          <div><dt>Ladungen</dt><dd>${f0.format(o.ladungen)}</dd></div>
          <div><dt>Energie</dt><dd>${kwh(o.kwh)}${da(o.anteil_kwh) ?
            ` <small>(${f0.format(o.anteil_kwh)} %)</small>` : ""}</dd></div>
          ${o.ort === "pv" ? `
          <div><dt>aus der Anlage</dt><dd>${kwh(o.pv_kwh)}</dd></div>
          <div><dt>doch aus dem Netz</dt><dd>${kwh(o.netz_kwh)}</dd></div>
          <div><dt>Ø je Netz-kWh</dt><dd>${ct(o.netz_preis_kwh)}</dd></div>
          <div><dt>Ø je geladener kWh</dt><dd>${ct(o.preis_kwh)}</dd></div>`
          : `<div><dt>Ø Preis</dt><dd>${ct(o.preis_kwh)}</dd></div>`}
          <div class="hervor"><dt>Bezahlt</dt><dd>${euro(o.kosten)}</dd></div>
        </dl>
      </div>`).join("");
    pvHinweis(a.orte.find((o) => o.ort === "pv"));
  }

  /* Warum die Ersparnis mit PV so gut aussieht — und wo die Zahl hingehört. */
  function pvHinweis(pv) {
    const feld = $("pv_hinweis");
    feld.hidden = !pv;
    if (!pv) return;
    feld.innerHTML =
      `<strong>PV-Strom steht mit 0 €</strong>, weil dafür nichts bezahlt wurde — nur der ` +
      `Netzanteil kostet etwas. Die Gegenüberstellung unten fällt dadurch zugunsten des ` +
      `Autos aus. Was die ${kwh(pv.pv_kwh)} aus der eigenen Anlage wert sind, gehört in die ` +
      `Amortisation der Anlage; hier stünde dieselbe Kilowattstunde sonst ein zweites Mal.`;
  }

  function vergleich(a, e) {
    const g = a.gesamt;
    const anteil = (wert, hoechst) => (hoechst > 0 ? Math.max(2, (wert / hoechst) * 100) : 0) + "%";

    if (!g) {
      $("b_strom").style.width = $("b_benzin").style.width = "0";
      $("v_strom").textContent = $("v_benzin").textContent = leer;
      $("fazit").textContent = "";
      $("vergleich_basis").textContent = "";
      $("vergleich_umfang").hidden = true;
      ["t_strom_gesamt", "t_benzin_gesamt", "t_diff_gesamt", "t_strom_100", "t_benzin_100",
       "t_diff_100", "t_strom_menge", "t_benzin_menge", "t_strom_menge_ges", "t_benzin_menge_ges"]
        .forEach((id) => { $(id).textContent = leer; });
      return;
    }

    const hoechst = Math.max(g.strom_kosten, g.benzin_kosten);
    $("b_strom").style.width = anteil(g.strom_kosten, hoechst);
    $("b_benzin").style.width = anteil(g.benzin_kosten, hoechst);
    $("v_strom").textContent = euro(g.strom_kosten);
    $("v_benzin").textContent = euro(g.benzin_kosten);

    $("vergleich_basis").textContent =
      `${f0.format(g.strecke)} km, verglichen mit ${komma(gelesen(e.benzinverbrauch), 1)} l/100 km ` +
      `zu ${komma(gelesen(e.benzinpreis), 2)} €/l.`;

    umfang(a);

    const gespart = g.ersparnis;
    $("fazit").innerHTML = gespart >= 0
      ? `Der Strom hat <strong>${euro(gespart)}</strong> weniger gekostet als das Benzin — ` +
        `${zahl1(g.ersparnis_prozent)} % günstiger, ${euro(g.ersparnis_100)} je 100 km.`
      : `Der Strom war <strong>${euro(-gespart)}</strong> teurer als Benzin es gewesen wäre ` +
        `(${euro(-g.ersparnis_100)} je 100 km).`;

    $("t_strom_gesamt").textContent = euro(g.strom_kosten);
    $("t_benzin_gesamt").textContent = euro(g.benzin_kosten);
    $("t_diff_gesamt").innerHTML = unterschied(g.ersparnis);
    $("t_strom_100").textContent = euro(g.strom_100);
    $("t_benzin_100").textContent = euro(g.benzin_100);
    $("t_diff_100").innerHTML = unterschied(g.ersparnis_100);
    $("t_strom_menge").textContent = zahl1(g.verbrauch) + " kWh";
    $("t_benzin_menge").textContent = komma(gelesen(e.benzinverbrauch), 1) + " l";
    $("t_strom_menge_ges").textContent = kwh(g.kwh);
    $("t_benzin_menge_ges").textContent = liter(g.liter);
  }

  /* Welche Ladungen im Vergleich stecken — die erste gehört nicht dazu. */
  function umfang(a) {
    const feld = $("vergleich_umfang");
    const aus = a.aussen_vor;
    feld.hidden = !(aus && aus.anzahl > 0);
    if (feld.hidden) return;

    const gezaehlt = a.anzahl - aus.anzahl;
    feld.innerHTML =
      `Im Strom stecken <strong>${f0.format(gezaehlt)} von ${f0.format(a.anzahl)} Ladungen</strong>. ` +
      `Die erste (${kwh(aus.kwh)} für ${euro(aus.kosten)}) ist nur der Startpunkt der Strecke: ` +
      `Was vor ihr gefahren wurde, weiß der Rechner nicht, also zählt sie nicht mit. ` +
      `In „Insgesamt geladen“ oben steht sie sehr wohl — das ist dein bezahltes Geld.`;
  }

  function ersparnis(wert) {
    if (!da(wert)) return leer;
    return wert >= 0
      ? `<span class="gut">${euro(wert)}</span>`
      : `<span class="schlecht">− ${euro(-wert)}</span>`;
  }

  function unterschied(wert) {
    if (!da(wert)) return leer;
    const klasse = wert >= 0 ? "gut" : "schlecht";
    const zeichen = wert >= 0 ? "−" : "+";
    return `<span class="${klasse}">${zeichen} ${euro(Math.abs(wert))}</span>`;
  }

  function zusammenfassung(a) {
    const h = a.hochrechnung;
    const setzen = (praefix, w) => {
      $(praefix + "_km").textContent = w ? km(w.strecke) : leer;
      $(praefix + "_strom").textContent = w ? euro(w.strom_kosten) : leer;
      $(praefix + "_benzin").textContent = w ? euro(w.benzin_kosten) : leer;
      $(praefix + "_ersparnis").textContent = w ? euro(w.ersparnis) : leer;
    };
    setzen("m", h && h.monat);
    setzen("j", h && h.jahr);
  }

  function verlauf(a) {
    const reihen = sicht === "monate" ? a.monate : a.jahre;
    const koerper = $("verlauf_koerper");
    if (!reihen.length) {
      koerper.innerHTML = `<tr><td colspan="7" class="hinweis">Noch keine abgeschlossene Periode.</td></tr>`;
      return;
    }
    koerper.innerHTML = reihen.slice().reverse().map((r) => `
      <tr>
        <td>${sicher(r.titel)}</td>
        <td>${f0.format(r.strecke)}</td>
        <td>${f1.format(r.kwh)}</td>
        <td>${zahl1(r.verbrauch)}</td>
        <td>${euro(r.strom_kosten)}</td>
        <td>${euro(r.benzin_kosten)}</td>
        <td>${ersparnis(r.ersparnis)}</td>
      </tr>`).join("");
  }

  function liste(daten, a) {
    const nach = new Map(a.perioden.map((p) => [p.id, p]));
    const koerper = $("liste_koerper");
    const ladungen = daten.ladungen.slice().reverse();
    $("liste_leer").hidden = ladungen.length > 0;

    koerper.innerHTML = ladungen.map((l) => {
      const p = nach.get(l.id);
      const preis = l.kwh > 0 ? l.kosten / l.kwh : null;
      const name = { auswaerts: "auswärts", pv: "PV" }[l.ort] || "zuhause";
      return `
      <tr>
        <td>${datumDe(l.datum)}${l.notiz ? `<br><small class="hinweis">${sicher(l.notiz)}</small>` : ""}</td>
        <td><span class="marke ${l.ort}">${name}</span></td>
        <td>${f0.format(l.km)}</td>
        <td>${p && p.gueltig ? f0.format(p.strecke) + " km" : leer}</td>
        <td>${f1.format(l.kwh)}${l.soc === null || l.soc === undefined ? ""
          : ` <span class="klein">→ ${f0.format(l.soc)} %</span>`}${
          da(l.netz_kwh) && l.netz_kwh > 0
            ? `<br><span class="klein">davon ${f1.format(l.netz_kwh)} Netz</span>` : ""}</td>
        <td>${p && p.gueltig ? zahl1(p.verbrauch) : leer}</td>
        <td>${da(preis) ? f1.format(preis * 100) : leer}</td>
        <td>${euro(l.kosten)}</td>
        <td><div class="werkzeuge">
          <button type="button" data-aendern="${l.id}">Ändern</button>
          <button type="button" data-loeschen="${l.id}">Löschen</button>
        </div></td>
      </tr>`;
    }).join("");
  }

  function warnungen(a) {
    $("warnungen").innerHTML = (a.warnungen || [])
      .map((w) => `<p class="warnung">${sicher(w)}</p>`).join("");
  }

  // ------------------------------------------------- Ort und Preisart

  function ortSetzen(neu, vomBenutzer = false) {
    ort = neu;
    document.querySelectorAll("#ortwahl button")
      .forEach((k) => k.classList.toggle("aktiv", k.dataset.ort === neu));

    // Der Netzanteil ist nur beim Überschussladen eine Frage. Und dort darf das
    // Preisfeld leer bleiben: eine reine PV-Ladung hat keinen Preis.
    $("netzfeld").hidden = neu !== "pv";
    $("f_preis").required = neu !== "pv";
    if (neu !== "pv") $("f_netz").value = "";
    if (!vomBenutzer) return;

    // Zuhause kennt man den Arbeitspreis, unterwegs steht die Summe auf der
    // Quittung; beim Überschussladen zahlt der Arbeitspreis den Netzanteil.
    preisartSetzen(neu === "auswaerts" ? "summe" : "tarif", true);
    if (preisIstVorschlag || !$("f_preis").value.trim()) vorschlagSetzen();
    preisHinweis();
  }

  /* Zuhause und je kWh: der Haustarif steht schon da. Sonst bleibt das Feld leer.
     Bei PV gilt er ebenso — er bepreist dort den Netzanteil. */
  function vorschlagSetzen() {
    const tarif = haustarif();
    if (ort !== "auswaerts" && preisart === "tarif" && da(tarif)) {
      $("f_preis").value = komma(tarif, 1);
      preisIstVorschlag = true;
    } else {
      $("f_preis").value = "";
      preisIstVorschlag = false;
    }
  }

  function preisartSetzen(neu, umrechnen = false) {
    if (neu === preisart) return;
    const alt = preisart;
    preisart = neu;

    document.querySelectorAll("#preisart button")
      .forEach((k) => k.classList.toggle("aktiv", k.dataset.art === neu));
    $("preis_beschriftung").innerHTML = neu === "tarif"
      ? 'Preis je kWh <span class="einheit">ct</span>'
      : 'Kosten der Ladung <span class="einheit">€</span>';
    $("f_preis").placeholder = neu === "tarif" ? "z. B. 34,0" : "z. B. 14,00";

    if (!umrechnen) return;

    // Selbst Getipptes mitnehmen, wenn die kWh es zulassen — sonst lieber leeren,
    // als aus 34 ct stillschweigend 34 € zu machen.
    const wert = preisIstVorschlag ? null : gelesen($("f_preis").value);
    const energie = gelesen($("f_kwh").value);
    if (da(wert) && da(energie) && energie > 0) {
      $("f_preis").value = alt === "tarif"
        ? komma((wert / 100) * energie, 2)      // ct/kWh -> Summe
        : komma((wert / energie) * 100, 2);     // Summe  -> ct/kWh, cent-genau zurueck
      preisIstVorschlag = false;
    } else {
      vorschlagSetzen();
    }
    preisHinweis();
  }

  /* Zeigt live, was die andere Darstellung wäre — Rechenfehler fallen so auf. */
  function preisHinweis() {
    const wert = gelesen($("f_preis").value);
    const energie = gelesen($("f_kwh").value);
    const feld = $("preis_hinweis");

    // Beim Überschussladen bepreist der Tarif nur, was aus dem Netz kam.
    if (ort === "pv" && preisart === "tarif") {
      const netz = gelesen($("f_netz").value);
      const teil = da(netz) ? netz : 0;
      feld.textContent = !da(wert)
        ? "Der Arbeitspreis — bezahlt wird damit nur, was aus dem Netz kam."
        : teil <= 0
          ? "Nichts aus dem Netz: diese Ladung hat 0,00 € gekostet."
          : `${komma(teil, 1)} kWh aus dem Netz × ${komma(wert, 1)} ct = `
            + `${euro((wert / 100) * teil)}`;
      return;
    }

    if (!da(wert) || !da(energie) || energie <= 0) {
      feld.textContent = preisart === "tarif"
        ? "Der Preis je kWh — die Gesamtkosten rechnet der Rechner selbst aus."
        : "Der Betrag, der auf der Quittung steht — inklusive Standgebühr.";
      return;
    }
    feld.textContent = preisart === "tarif"
      ? `${komma(energie, 1)} kWh × ${komma(wert, 1)} ct = ${euro((wert / 100) * energie)}`
      : `${euro(wert)} ÷ ${komma(energie, 1)} kWh = ${komma((wert / energie) * 100, 1)} ct/kWh`;
  }

  // ------------------------------------------- Überschuss ausrechnen

  const RECHNERFELDER = ["bezug_von", "bezug_bis", "einspeisung_von", "einspeisung_bis",
                         "erzeugung_von", "erzeugung_bis", "ladung_von", "ladung_bis"];

  function rechnerEingabe() {
    const daten = {};
    RECHNERFELDER.forEach((name) => { daten[name] = $("r_" + name).value; });
    return JSON.stringify(daten);
  }

  function rechnerZeigen(r) {
    $("rechner_ergebnis").hidden = false;

    $("r_ladung").textContent = kwh(r.ladung);
    $("r_netz").textContent = kwh(r.netz_kwh);
    $("r_pv").textContent = kwh(r.pv_kwh) + (da(r.pv_anteil)
      ? ` (${f0.format(r.pv_anteil)} %)` : "");
    $("r_kosten").textContent = euro(r.kosten);

    $("r_erzeugt").textContent = kwh(r.erzeugung);
    $("r_eingespeist").textContent = kwh(r.einspeisung);
    $("r_bezogen").textContent = kwh(r.bezug);
    $("r_haus").textContent = kwh(r.hausverbrauch);
    $("r_rest").textContent = kwh(r.restlast);

    $("r_fazit").innerHTML =
      `Trag oben <strong>${kwh(r.ladung)}</strong> ein, davon ` +
      `<strong>${kwh(r.netz_kwh)}</strong> aus dem Netz — das macht ` +
      `<strong>${euro(r.kosten)}</strong> bei ${ct(r.tarif)}/kWh.`;

    // Wem der Netzbezug gehoert, sagt kein Zaehler. Also die Spanne dazu.
    const feld = $("r_spanne");
    if (!r.spanne) {
      feld.innerHTML =
        `<strong>Ohne PV-Erzeugung keine Spanne.</strong> Der Wert unterstellt, dass ` +
        `jede bezogene Kilowattstunde ins Auto ging. Trägst du die Erzeugung mit ein, ` +
        `rechnet der Rechner aus, wie viel davon das Haus gebraucht hat — und wie ` +
        `unsicher die Aufteilung noch ist.`;
    } else if (r.spanne.hoch - r.spanne.tief < 0.05) {
      feld.innerHTML =
        `<strong>Eindeutig.</strong> Haus und Auto lassen sich hier nicht anders ` +
        `aufteilen: es bleibt bei ${kwh(r.netz_kwh)} aus dem Netz.`;
    } else {
      feld.innerHTML =
        `<strong>Die Aufteilung ist eine Annahme.</strong> Während einer Wolke ziehen ` +
        `Haus und Auto gleichzeitig aus dem Netz, und kein Zähler sagt, wem welche ` +
        `Kilowattstunde gehörte. Je nach Lesart sind es zwischen ` +
        `<strong>${kwh(r.spanne.tief)}</strong> (das Haus zuerst am Netz) und ` +
        `<strong>${kwh(r.spanne.hoch)}</strong> (das Auto zuerst); anteilig gerechnet ` +
        `${kwh(r.spanne.anteilig)}. Vorgeschlagen ist der obere Wert — er passt zur ` +
        `Regelung, die aus der PV zuerst das Haus bedient, und rechnet im Zweifel zu ` +
        `Lasten des Autos.`;
    }

    $("r_warnungen").innerHTML = (r.warnungen || [])
      .map((w) => `<p class="warnung">${sicher(w)}</p>`).join("");
  }

  // ------------------------------------------------------------- Bedienung

  function formularFuellen(l) {
    $("f_id").value = l ? l.id : "";
    datumSetzen(l ? l.datum : (zustand ? zustand.heute : ""));
    $("f_km").value = l ? komma(l.km, 0) : "";
    $("f_kwh").value = l ? komma(l.kwh, 2) : "";
    $("f_netz").value = l && l.netz_kwh !== null && l.netz_kwh !== undefined
      ? komma(l.netz_kwh, 2) : "";
    $("f_soc").value = l && l.soc !== null && l.soc !== undefined ? komma(l.soc, 0) : "";
    $("f_notiz").value = l ? l.notiz : "";
    $("f_speichern").textContent = l ? "Änderung speichern" : "Eintragen";
    $("f_abbrechen").hidden = !l;

    ortSetzen(l ? l.ort : "zuhause");
    if (l) {
      // So zurückzeigen, wie es eingetragen wurde.
      preisartSetzen(l.tarif === null ? "summe" : "tarif");
      $("f_preis").value = l.tarif === null ? komma(l.kosten, 2) : komma(l.tarif * 100, 1);
      preisIstVorschlag = false;
      $("f_datum").scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      preisartSetzen("tarif");
      vorschlagSetzen();
    }
    preisHinweis();
  }

  /* Setzt beide Felder: sichtbar deutsch, im Kalender ISO. */
  function datumSetzen(iso) {
    $("f_datum").value = iso ? datumDe(iso) : "";
    $("f_kalender").value = iso || "";
  }

  function eingabe() {
    const iso = datumGelesen($("f_datum").value);
    if (!iso) throw new Error("Datum: bitte als TT.MM.JJJJ eintragen, z. B. 03.09.2026.");
    const daten = {
      datum: iso,
      km: $("f_km").value,
      kwh: $("f_kwh").value,
      soc: $("f_soc").value,
      notiz: $("f_notiz").value,
      ort: ort,
    };
    if (ort === "pv") daten.netz_kwh = $("f_netz").value;
    if (preisart === "tarif") daten.ct_kwh = $("f_preis").value;
    else daten.kosten = $("f_preis").value;
    return JSON.stringify(daten);
  }

  async function laden() {
    try {
      zeichnen(await ruf("/api/daten"));
      formularFuellen(null);
    } catch (fehler) {
      melden(fehler.message, "fehler");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    laden();

    $("formular").addEventListener("submit", async (ereignis) => {
      ereignis.preventDefault();
      const kennung = $("f_id").value;
      try {
        const daten = kennung
          ? await ruf("/api/ladungen/" + kennung, { method: "PUT", body: eingabe() })
          : await ruf("/api/ladungen", { method: "POST", body: eingabe() });
        zeichnen(daten);
        formularFuellen(null);
        melden(kennung ? "Änderung gespeichert." : "Ladung eingetragen.");
      } catch (fehler) {
        melden(fehler.message, "fehler");
      }
    });

    $("f_abbrechen").addEventListener("click", () => formularFuellen(null));

    $("rechner_formular").addEventListener("submit", async (ereignis) => {
      ereignis.preventDefault();
      try {
        rechnerZeigen(await ruf("/api/ueberschuss", { method: "POST", body: rechnerEingabe() }));
      } catch (fehler) {
        $("rechner_ergebnis").hidden = true;
        melden(fehler.message, "fehler");
      }
    });

    $("r_leeren").addEventListener("click", () => {
      RECHNERFELDER.forEach((name) => { $("r_" + name).value = ""; });
      $("rechner_ergebnis").hidden = true;
      $("r_bezug_von").focus();
    });

    // Beim Verlassen sauber ausschreiben: aus 3.9.26 wird 03.09.2026.
    $("f_datum").addEventListener("blur", () => {
      const iso = datumGelesen($("f_datum").value);
      if (iso) datumSetzen(iso);
    });
    $("f_kalenderknopf").addEventListener("click", () => {
      const kalender = $("f_kalender");
      kalender.value = datumGelesen($("f_datum").value) || (zustand ? zustand.heute : "");
      if (typeof kalender.showPicker === "function") {
        try { kalender.showPicker(); return; } catch (fehler) { /* siehe unten */ }
      }
      kalender.focus();     // ohne showPicker bleibt der Weg über die Tastatur
    });
    $("f_kalender").addEventListener("change", () => {
      if ($("f_kalender").value) datumSetzen($("f_kalender").value);
    });
    $("f_kwh").addEventListener("input", preisHinweis);
    $("f_netz").addEventListener("input", preisHinweis);
    $("f_preis").addEventListener("input", () => {
      preisIstVorschlag = false;
      preisHinweis();
    });

    document.querySelectorAll("#ortwahl button").forEach((knopf) => {
      knopf.addEventListener("click", () => ortSetzen(knopf.dataset.ort, true));
    });
    document.querySelectorAll("#preisart button").forEach((knopf) => {
      knopf.addEventListener("click", () => preisartSetzen(knopf.dataset.art, true));
    });

    $("liste_koerper").addEventListener("click", async (ereignis) => {
      const knopf = ereignis.target.closest("button");
      if (!knopf) return;

      const aendern = knopf.dataset.aendern;
      if (aendern) {
        const l = zustand.ladungen.find((x) => String(x.id) === aendern);
        if (l) formularFuellen(l);
        return;
      }
      const loeschen = knopf.dataset.loeschen;
      if (loeschen) {
        const l = zustand.ladungen.find((x) => String(x.id) === loeschen);
        if (!confirm(`Ladung vom ${datumDe(l.datum)} (${f1.format(l.kwh)} kWh) löschen?`)) return;
        try {
          const warBearbeitet = $("f_id").value === loeschen;
          zeichnen(await ruf("/api/ladungen/" + loeschen, { method: "DELETE" }));
          if (warBearbeitet) formularFuellen(null);
          melden("Eintrag gelöscht.");
        } catch (fehler) {
          melden(fehler.message, "fehler");
        }
      }
    });

    $("einstellungen_formular").addEventListener("submit", async (ereignis) => {
      ereignis.preventDefault();
      try {
        zeichnen(await ruf("/api/einstellungen", {
          method: "PUT",
          body: JSON.stringify({
            benzinpreis: $("e_benzinpreis").value,
            benzinverbrauch: $("e_benzinverbrauch").value,
            strompreis: $("e_strompreis").value,
            kapazitaet: $("e_kapazitaet").value,
            fahrzeug: $("e_fahrzeug").value,
          }),
        }));
        melden("Einstellungen gespeichert.");
      } catch (fehler) {
        melden(fehler.message, "fehler");
      }
    });

    document.querySelectorAll(".schalter button[data-sicht]").forEach((knopf) => {
      knopf.addEventListener("click", () => {
        sicht = knopf.dataset.sicht;
        document.querySelectorAll(".schalter button[data-sicht]")
          .forEach((k) => k.classList.toggle("aktiv", k === knopf));
        if (zustand) verlauf(zustand.auswertung);
      });
    });
  });
})();
