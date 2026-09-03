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
    if (!$("e_fahrzeug").matches(":focus")) $("e_fahrzeug").value = e.fahrzeug || "";

    if (!$("f_datum").value) $("f_datum").value = daten.heute;

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
  }

  function orte(a) {
    $("orte").innerHTML = a.orte.map((o) => `
      <div class="block">
        <h3 class="ortname"><span class="punkt ${o.ort}"></span>${sicher(o.titel)}</h3>
        <dl>
          <div><dt>Ladungen</dt><dd>${f0.format(o.ladungen)}</dd></div>
          <div><dt>Energie</dt><dd>${kwh(o.kwh)}${da(o.anteil_kwh) ?
            ` <small>(${f0.format(o.anteil_kwh)} %)</small>` : ""}</dd></div>
          <div><dt>Ø Preis</dt><dd>${ct(o.preis_kwh)}</dd></div>
          <div class="hervor"><dt>Bezahlt</dt><dd>${euro(o.kosten)}</dd></div>
        </dl>
      </div>`).join("");
  }

  function vergleich(a, e) {
    const g = a.gesamt;
    const anteil = (wert, hoechst) => (hoechst > 0 ? Math.max(2, (wert / hoechst) * 100) : 0) + "%";

    if (!g) {
      $("b_strom").style.width = $("b_benzin").style.width = "0";
      $("v_strom").textContent = $("v_benzin").textContent = leer;
      $("fazit").textContent = "";
      $("vergleich_basis").textContent = "";
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
      const name = l.ort === "auswaerts" ? "auswärts" : "zuhause";
      return `
      <tr>
        <td>${datumDe(l.datum)}${l.notiz ? `<br><small class="hinweis">${sicher(l.notiz)}</small>` : ""}</td>
        <td><span class="marke ${l.ort}">${name}</span></td>
        <td>${f0.format(l.km)}</td>
        <td>${p && p.gueltig ? f0.format(p.strecke) + " km" : leer}</td>
        <td>${f1.format(l.kwh)}</td>
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
    if (!vomBenutzer) return;

    // Zuhause kennt man den Arbeitspreis, unterwegs steht die Summe auf der Quittung.
    preisartSetzen(neu === "zuhause" ? "tarif" : "summe", true);
    if (preisIstVorschlag || !$("f_preis").value.trim()) vorschlagSetzen();
    preisHinweis();
  }

  /* Zuhause und je kWh: der Haustarif steht schon da. Sonst bleibt das Feld leer. */
  function vorschlagSetzen() {
    const tarif = haustarif();
    if (ort === "zuhause" && preisart === "tarif" && da(tarif)) {
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

  // ------------------------------------------------------------- Bedienung

  function formularFuellen(l) {
    $("f_id").value = l ? l.id : "";
    $("f_datum").value = l ? l.datum : (zustand ? zustand.heute : "");
    $("f_km").value = l ? komma(l.km, 0) : "";
    $("f_kwh").value = l ? komma(l.kwh, 2) : "";
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

  function eingabe() {
    const daten = {
      datum: $("f_datum").value,
      km: $("f_km").value,
      kwh: $("f_kwh").value,
      notiz: $("f_notiz").value,
      ort: ort,
    };
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
    $("f_kwh").addEventListener("input", preisHinweis);
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
