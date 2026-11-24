/* The Seax: "Check prices in your area" for our house price data stories (owner, 24 Nov 2026: "a dropdown to select
   your area"). Any element with class "seax-plookup" and data-src="/data/prices/....json" becomes a selector for the
   14 Essex council areas, showing that area's average prices, its change over the year and month, where it ranks in
   Essex, and how it compares with Essex and England. Used on story pages and in the front page's reader. */
(function () {
  "use strict";
  var CSS = ".seax-plookup{margin:26px 0;border:1px solid #e6dcc0;border-top:5px solid #d79f2b;border-radius:6px;background:#fffdf6;padding:18px 18px 14px;font-size:15px;line-height:1.45;color:#1a1a1a}" +
    ".seax-plookup h3{margin:0 0 4px;font-size:21px;line-height:1.2}" +
    ".seax-plookup .pl-intro{margin:0 0 12px;color:#555;font-size:14px}" +
    ".seax-plookup select{width:100%;font:inherit;font-size:16px;padding:10px 12px;border:2px solid #d79f2b;border-radius:6px;background:#fff;color:#111;cursor:pointer}" +
    ".seax-plookup .pl-out{margin-top:14px}" +
    ".seax-plookup .pl-name{font-size:19px;font-weight:800;margin:0 0 2px}" +
    ".seax-plookup .pl-sub{color:#666;font-size:13px;margin:0 0 12px}" +
    ".seax-plookup .pl-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 12px}" +
    ".seax-plookup .pl-tile{background:#fff;border:1px solid #ece4cf;border-radius:6px;padding:10px 10px 8px}" +
    ".seax-plookup .pl-tile b{display:block;font-size:24px;line-height:1.1;font-variant-numeric:tabular-nums}" +
    ".seax-plookup .pl-tile span{display:block;font-size:12.5px;color:#555}" +
    ".seax-plookup .up{color:#c8102e}.seax-plookup .down{color:#2a6fd1}.seax-plookup .same{color:#666}" +
    ".seax-plookup .pl-facts{margin:0 0 12px;padding-left:18px;font-size:14px}.seax-plookup .pl-facts li{margin:3px 0}" +
    ".seax-plookup table{width:100%;border-collapse:collapse;font-size:14px}" +
    ".seax-plookup th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:#777;font-weight:700;padding:4px 6px 6px 0;border-bottom:1px solid #e6dcc0}" +
    ".seax-plookup td{padding:6px 6px 6px 0;border-bottom:1px solid #f1ead8;vertical-align:middle}" +
    ".seax-plookup td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}" +
    ".seax-plookup .bar{display:block;height:6px;border-radius:3px;background:#d79f2b;margin-top:4px;min-width:2px}" +
    ".seax-plookup .bar.eng{background:#bdb6a4}" +
    ".seax-plookup .pl-note{margin:10px 0 0;color:#666;font-size:12.5px}" +
    "@media(max-width:560px){.seax-plookup .pl-tiles{grid-template-columns:1fr 1fr}.seax-plookup .pl-tile:first-child{grid-column:1/-1}}";
  function addCss() {
    if (document.getElementById("seax-plookup-css")) return;
    var s = document.createElement("style"); s.id = "seax-plookup-css"; s.textContent = CSS; document.head.appendChild(s);
  }
  function esc(t) { return String(t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function gbp(v) { return "£" + Math.round(v).toLocaleString("en-GB"); }
  function pct(v) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%"; }
  function cls(v) { return v > 0 ? "up" : v < 0 ? "down" : "same"; }
  function ord(n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function rank(D, name, key, desc) {
    var list = Object.keys(D.areas).sort(function (a, b) { return desc ? D.areas[b][key] - D.areas[a][key] : D.areas[a][key] - D.areas[b][key]; });
    return list.indexOf(name) + 1;
  }
  function render(box, D, name) {
    var out = box.querySelector(".pl-out"), a = D.areas[name];
    if (!a) { out.innerHTML = ""; return; }
    var n = Object.keys(D.areas).length, E = D.england, X = D.essex;
    var prev = a.price / (1 + a.annual / 100), diff = Math.round((a.price - prev) / 100) * 100;
    var growth = rank(D, name, "annual", true), fall = rank(D, name, "annual", false), dear = rank(D, name, "price", true);
    var vsEng = Math.round((a.price / E.price - 1) * 100);
    var change = a.annual > 0 ? "up " + Math.abs(a.annual).toFixed(1) + "%, about " + gbp(Math.abs(diff)) + " more than a year earlier"
      : a.annual < 0 ? "down " + Math.abs(a.annual).toFixed(1) + "%, about " + gbp(Math.abs(diff)) + " less than a year earlier" : "unchanged on a year earlier";
    var facts = [
      "The average home in " + esc(name) + " cost " + gbp(a.price) + " in " + esc(D.monthLabel) + ", " + change + ".",
      (a.annual > 0 ? "That is the " + (growth === 1 ? "biggest rise" : ord(growth) + " biggest rise") + " of Essex's " + n + " council areas"
        : a.annual < 0 ? "That is the " + (fall === 1 ? "biggest fall" : ord(fall) + " biggest fall") + " of Essex's " + n + " council areas"
        : "Prices held steady, unlike most of Essex's " + n + " council areas") + ", and the " + (dear === 1 ? "highest" : dear === n ? "lowest" : ord(dear) + " highest") + " average price.",
      "Homes here cost " + (vsEng === 0 ? "about the same as" : Math.abs(vsEng) + "% " + (vsEng > 0 ? "more" : "less") + " than") + " the England average of " + gbp(E.price) + ". Across England, prices " + (E.annual > 0 ? "rose " : E.annual < 0 ? "fell " : "held at ") + Math.abs(E.annual).toFixed(1) + "% over the year.",
      "A first-time buyer pays an average of " + gbp(a.firstTime) + ", against " + gbp(E.firstTime) + " across England."
    ];
    var types = [["Detached house", "detached"], ["Flat or maisonette", "flat"], ["First-time buyer home", "firstTime"], ["All homes", "price"]];
    var max = 0; types.forEach(function (t) { max = Math.max(max, a[t[1]], E[t[1]]); });
    out.innerHTML = '<p class="pl-name">' + esc(name) + "</p>" +
      '<p class="pl-sub">Council area averages, ' + esc(D.monthLabel) + ". Essex county council area average: " + gbp(X.price) + " (" + pct(X.annual) + ").</p>" +
      '<div class="pl-tiles">' +
        '<div class="pl-tile"><b>' + gbp(a.price) + "</b><span>average home</span></div>" +
        '<div class="pl-tile"><b class="' + cls(a.annual) + '">' + pct(a.annual) + "</b><span>over the year</span></div>" +
        '<div class="pl-tile"><b class="' + cls(a.monthly) + '">' + pct(a.monthly) + "</b><span>in the month</span></div>" +
      "</div>" +
      '<ul class="pl-facts">' + facts.map(function (f) { return "<li>" + f + "</li>"; }).join("") + "</ul>" +
      "<table><thead><tr><th>Type of home</th><th class=\"n\">" + esc(name) + '</th><th class="n">England</th></tr></thead><tbody>' +
      types.map(function (t) {
        var v = a[t[1]], e = E[t[1]];
        return "<tr><td>" + t[0] + '<span class="bar" style="width:' + Math.max(1, Math.round(v / max * 100)) + '%"></span><span class="bar eng" style="width:' + Math.max(1, Math.round(e / max * 100)) + '%"></span></td><td class="n"><b>' + gbp(v) + '</b></td><td class="n">' + gbp(e) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="pl-note">' + (D.notes || []).map(esc).join(" ") + ' Source: ' + esc(D.source) + ".</p>";
  }
  function mount(box) {
    if (box.getAttribute("data-mounted")) return; box.setAttribute("data-mounted", "1"); addCss();
    var src = box.getAttribute("data-src");
    box.innerHTML = "<h3>Check house prices in your area</h3>" +
      '<p class="pl-intro">Choose any of the 14 Essex council areas to see its average prices, how they have changed and how it compares with England.</p>' +
      '<select aria-label="Choose your area"><option value="">Loading the 14 areas…</option></select><div class="pl-out" aria-live="polite"></div>';
    var sel = box.querySelector("select");
    fetch(src, { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (D) {
      var names = Object.keys(D.areas).sort(function (x, y) { return x.localeCompare(y, "en-GB"); });
      sel.innerHTML = '<option value="">Choose your area</option>' + names.map(function (h) { return '<option value="' + esc(h) + '">' + esc(h) + "</option>"; }).join("");
      sel.addEventListener("change", function () { render(box, D, sel.value); try { localStorage.setItem("seax-price-area", sel.value); } catch (e) {} });
      var last = ""; try { last = localStorage.getItem("seax-price-area") || ""; } catch (e) {}
      if (last && D.areas[last]) { sel.value = last; render(box, D, last); }
      if (location.hash === "#prices") setTimeout(function () { box.scrollIntoView({ block: "start" }); }, 60);
    }).catch(function () { sel.innerHTML = '<option value="">Could not load the figures. Please refresh the page.</option>'; });
  }
  function mountAll(root) { Array.prototype.forEach.call((root || document).querySelectorAll(".seax-plookup"), mount); }
  window.SeaxPriceLookup = { mount: mount, mountAll: mountAll };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { mountAll(); }); else mountAll();
})();
