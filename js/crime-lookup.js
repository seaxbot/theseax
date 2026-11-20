/* The Seax: "Look up your neighbourhood" for our police data stories (owner's idea, 20 Nov 2026).
   Any element with class "seax-lookup" and data-src="/data/crime/....json" becomes a selector for the 56 Essex Police
   neighbourhoods, showing that neighbourhood's records by type. Used on story pages and in the front page's reader. */
(function () {
  "use strict";
  var CSS = ".seax-lookup{margin:26px 0;border:1px solid #e6dcc0;border-top:5px solid #d79f2b;border-radius:6px;background:#fffdf6;padding:18px 18px 14px;font-size:15px;line-height:1.45;color:#1a1a1a}" +
    ".seax-lookup h3{margin:0 0 4px;font-size:21px;line-height:1.2}" +
    ".seax-lookup .sl-intro{margin:0 0 12px;color:#555;font-size:14px}" +
    ".seax-lookup select{width:100%;font:inherit;font-size:16px;padding:10px 12px;border:2px solid #d79f2b;border-radius:6px;background:#fff;color:#111;cursor:pointer}" +
    ".seax-lookup .sl-out{margin-top:14px}" +
    ".seax-lookup .sl-name{font-size:19px;font-weight:800;margin:0 0 2px}" +
    ".seax-lookup .sl-sub{color:#666;font-size:13px;margin:0 0 12px}" +
    ".seax-lookup .sl-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 12px}" +
    ".seax-lookup .sl-tile{background:#fff;border:1px solid #ece4cf;border-radius:6px;padding:10px 10px 8px}" +
    ".seax-lookup .sl-tile b{display:block;font-size:24px;line-height:1.1}" +
    ".seax-lookup .sl-tile span{display:block;font-size:12.5px;color:#555}" +
    ".seax-lookup .up{color:#c8102e}.seax-lookup .down{color:#2a6fd1}.seax-lookup .same{color:#666}" +
    ".seax-lookup .sl-facts{margin:0 0 12px;padding-left:18px;font-size:14px}.seax-lookup .sl-facts li{margin:2px 0}" +
    ".seax-lookup table{width:100%;border-collapse:collapse;font-size:14px}" +
    ".seax-lookup th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:#777;font-weight:700;padding:4px 6px 6px 0;border-bottom:1px solid #e6dcc0}" +
    ".seax-lookup td{padding:6px 6px 6px 0;border-bottom:1px solid #f1ead8;vertical-align:middle}" +
    ".seax-lookup td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}" +
    ".seax-lookup .bar{display:block;height:6px;border-radius:3px;background:#d79f2b;margin-top:4px;min-width:2px}" +
    ".seax-lookup .sl-note{margin:10px 0 0;color:#666;font-size:12.5px}" +
    "@media(max-width:560px){.seax-lookup .sl-tiles{grid-template-columns:1fr 1fr}.seax-lookup .sl-tile:first-child{grid-column:1/-1}.seax-lookup .hide-s{display:none}}";

  function addCss() {
    if (document.getElementById("seax-lookup-css")) return;
    var s = document.createElement("style"); s.id = "seax-lookup-css"; s.textContent = CSS; document.head.appendChild(s);
  }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function n(x) { return Number(x || 0).toLocaleString("en-GB"); }
  function sum(o) { var t = 0; for (var k in o) t += o[k] || 0; return t; }
  function crimeOnly(o) { var t = 0; for (var k in o) if (k !== "anti-social-behaviour") t += o[k] || 0; return t; }
  function chg(a, b) { /* change from a to b, with a percentage only when the base is big enough to mean something */
    var d = b - a, cls = d > 0 ? "up" : d < 0 ? "down" : "same";
    var txt = d === 0 ? "no change" : (d > 0 ? "up " : "down ") + n(Math.abs(d));
    if (a >= 20 && d !== 0) txt += " (" + (d > 0 ? "+" : "-") + Math.round(Math.abs(d) / a * 100) + "%)";
    return '<span class="' + cls + '">' + txt + "</span>";
  }
  function ord(k) { var s = ["th", "st", "nd", "rd"], v = k % 100; return k + (s[(v - 20) % 10] || s[v] || s[0]); }
  function rank(names, f, h) { /* 1 = highest; ties share a rank */
    var v = f(h), r = 1; names.forEach(function (x) { if (f(x) > v) r++; }); return r;
  }

  function render(box, D, h) {
    var out = box.querySelector(".sl-out");
    if (!h) { out.innerHTML = ""; return; }
    var names = Object.keys(D.hoods), a = D.hoods[h]["2025-09"], m = D.hoods[h]["2026-08"], b = D.hoods[h]["2026-09"];
    var all25 = sum(a), all26 = sum(b), allAug = sum(m), asb25 = a["anti-social-behaviour"] || 0, asb26 = b["anti-social-behaviour"] || 0;
    var cr25 = crimeOnly(a), cr26 = crimeOnly(b);
    var rTot = rank(names, function (x) { return sum(D.hoods[x]["2026-09"]); }, h);
    var rAsb = rank(names, function (x) { return D.hoods[x]["2026-09"]["anti-social-behaviour"] || 0; }, h);
    var cats = Object.keys(D.labels).filter(function (k) { return (a[k] || 0) + (b[k] || 0) > 0; })
      .sort(function (x, y) { return (b[y] || 0) - (b[x] || 0) || (a[y] || 0) - (a[x] || 0); });
    var max = Math.max.apply(null, cats.map(function (k) { return b[k] || 0; }).concat([1]));
    var diffs = cats.map(function (k) { return [k, (b[k] || 0) - (a[k] || 0)]; });
    var up = diffs.filter(function (x) { return x[1] > 0; }).sort(function (x, y) { return y[1] - x[1]; })[0];
    var dn = diffs.filter(function (x) { return x[1] < 0; }).sort(function (x, y) { return x[1] - y[1]; })[0];
    var top = cats[0];
    var facts = [];
    facts.push((rTot === 1 ? "The most police records of any of Essex's " : ord(rTot) + " most police records of Essex's ") + names.length + " neighbourhoods in September 2026");
    facts.push(rAsb === 1 ? "The most anti-social behaviour reports of any neighbourhood" : ord(rAsb) + " most anti-social behaviour reports");
    if (top) facts.push("Most common: " + esc(D.labels[top]).toLowerCase() + " (" + n(b[top]) + ")");
    if (up) facts.push("Biggest rise: " + esc(D.labels[up[0]]).toLowerCase() + ", up " + n(up[1]));
    if (dn) facts.push("Biggest fall: " + esc(D.labels[dn[0]]).toLowerCase() + ", down " + n(-dn[1]));
    facts.push("All records against August 2026: " + chg(allAug, all26));
    out.innerHTML =
      '<p class="sl-name">' + esc(h) + "</p>" +
      '<p class="sl-sub">September 2026 against September 2025</p>' +
      '<div class="sl-tiles">' +
        '<div class="sl-tile"><b>' + n(all26) + "</b><span>all police records</span><span>" + chg(all25, all26) + "</span></div>" +
        '<div class="sl-tile"><b>' + n(cr26) + "</b><span>crimes</span><span>" + chg(cr25, cr26) + "</span></div>" +
        '<div class="sl-tile"><b>' + n(asb26) + "</b><span>anti-social behaviour</span><span>" + chg(asb25, asb26) + "</span></div>" +
      "</div>" +
      '<ul class="sl-facts">' + facts.map(function (f) { return "<li>" + f + "</li>"; }).join("") + "</ul>" +
      '<table><thead><tr><th>Type</th><th class="n hide-s">Sep 2025</th><th class="n">Sep 2026</th><th class="n">Change</th></tr></thead><tbody>' +
      cats.map(function (k) {
        var x = a[k] || 0, y = b[k] || 0;
        return "<tr><td>" + esc(D.labels[k]) + '<span class="bar" style="width:' + Math.round(y / max * 100) + '%"></span></td>' +
          '<td class="n hide-s">' + n(x) + '</td><td class="n"><b>' + n(y) + '</b></td><td class="n">' + chg(x, y) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="sl-note">Small numbers can swing a lot from one month to the next. ' + esc((D.notes || []).join(" ")) + " Source: " + esc(D.source) + ".</p>";
  }

  function mount(box) {
    if (!box || box.getAttribute("data-mounted")) return;
    box.setAttribute("data-mounted", "1"); addCss();
    var src = box.getAttribute("data-src");
    box.innerHTML = "<h3>Look up your neighbourhood</h3>" +
      '<p class="sl-intro">Choose any of the 56 Essex Police neighbourhood areas to see its police records by type, against a year earlier.</p>' +
      '<select aria-label="Choose a neighbourhood"><option value="">Loading the 56 neighbourhoods…</option></select><div class="sl-out" aria-live="polite"></div>';
    var sel = box.querySelector("select");
    fetch(src, { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (D) {
      var names = Object.keys(D.hoods).sort(function (x, y) { return x.localeCompare(y, "en-GB"); });
      sel.innerHTML = '<option value="">Choose your neighbourhood</option>' + names.map(function (h) { return '<option value="' + esc(h) + '">' + esc(h) + "</option>"; }).join("");
      sel.addEventListener("change", function () {
        render(box, D, sel.value);
        try { localStorage.setItem("seax-hood", sel.value); } catch (e) {}
      });
      var last = ""; try { last = localStorage.getItem("seax-hood") || ""; } catch (e) {}
      if (last && D.hoods[last]) { sel.value = last; render(box, D, last); }
    }).catch(function () {
      sel.innerHTML = '<option value="">Could not load the figures. Please refresh the page.</option>';
    });
  }

  function mountAll(root) { Array.prototype.forEach.call((root || document).querySelectorAll(".seax-lookup"), mount); }
  window.SeaxLookup = { mount: mount, mountAll: mountAll };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { mountAll(); }); else mountAll();
})();
