/* The Seax: "Check food hygiene in your area" for our food hygiene data stories (27 Nov 2026, weekend analysis).
   Any element with class "seax-hlookup" and data-src="/data/hygiene/....json" becomes a selector for the 14 Essex
   council areas, showing how its places to eat out are rated, how its takeaways compare with Essex, how many are
   waiting for a first inspection, and the places rated 0 or 1 at their last inspection, each linked to the Food
   Standards Agency's own page. Used on story pages and in the front page's reader. */
(function () {
  "use strict";
  var CSS = ".seax-hlookup{margin:26px 0;border:1px solid #e6dcc0;border-top:5px solid #2e8b57;border-radius:6px;background:#fbfdf9;padding:18px 18px 14px;font-size:15px;line-height:1.45;color:#1a1a1a}" +
    ".seax-hlookup h3{margin:0 0 4px;font-size:21px;line-height:1.2}" +
    ".seax-hlookup .hl-intro{margin:0 0 12px;color:#555;font-size:14px}" +
    ".seax-hlookup select{width:100%;font:inherit;font-size:16px;padding:10px 12px;border:2px solid #2e8b57;border-radius:6px;background:#fff;color:#111;cursor:pointer}" +
    ".seax-hlookup .hl-out{margin-top:14px}" +
    ".seax-hlookup .hl-name{font-size:19px;font-weight:800;margin:0 0 2px}" +
    ".seax-hlookup .hl-sub{color:#666;font-size:13px;margin:0 0 12px}" +
    ".seax-hlookup .hl-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 12px}" +
    ".seax-hlookup .hl-tile{background:#fff;border:1px solid #dfe9dc;border-radius:6px;padding:10px 10px 8px}" +
    ".seax-hlookup .hl-tile b{display:block;font-size:24px;line-height:1.1;font-variant-numeric:tabular-nums}" +
    ".seax-hlookup .hl-tile span{display:block;font-size:12.5px;color:#555}" +
    ".seax-hlookup .hl-facts{margin:0 0 12px;padding-left:18px;font-size:14px}.seax-hlookup .hl-facts li{margin:3px 0}" +
    ".seax-hlookup table{width:100%;border-collapse:collapse;font-size:14px;margin:0 0 12px}" +
    ".seax-hlookup th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:#777;font-weight:700;padding:4px 6px 6px 0;border-bottom:1px solid #dfe9dc}" +
    ".seax-hlookup td{padding:6px 6px 6px 0;border-bottom:1px solid #edf2ea;vertical-align:middle}" +
    ".seax-hlookup td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}" +
    ".seax-hlookup .bar{display:block;height:7px;border-radius:3px;background:#2e8b57;margin-top:4px;min-width:2px}" +
    ".seax-hlookup .bar.r4{background:#7fb069}.seax-hlookup .bar.r3{background:#d79f2b}.seax-hlookup .bar.r2,.seax-hlookup .bar.r1,.seax-hlookup .bar.r0{background:#c8102e}" +
    ".seax-hlookup .hl-low h4{margin:6px 0 6px;font-size:15px}" +
    ".seax-hlookup .hl-low ul{list-style:none;margin:0;padding:0}" +
    ".seax-hlookup .hl-low li{padding:7px 0;border-bottom:1px solid #edf2ea;font-size:14px}" +
    ".seax-hlookup .hl-low a{font-weight:700;color:#111}" +
    ".seax-hlookup .hl-r{display:inline-block;min-width:22px;text-align:center;font-weight:800;color:#fff;background:#c8102e;border-radius:4px;padding:0 5px;margin-right:6px}" +
    ".seax-hlookup .hl-pend{display:inline-block;font-size:11.5px;font-weight:700;color:#2e6b45;background:#e6f2e9;border-radius:99px;padding:0 7px;margin-left:6px}" +
    ".seax-hlookup .hl-meta{display:block;color:#666;font-size:12.5px}" +
    ".seax-hlookup .hl-note{margin:10px 0 0;color:#666;font-size:12.5px}" +
    "@media(max-width:560px){.seax-hlookup .hl-tiles{grid-template-columns:1fr 1fr}.seax-hlookup .hl-tile:first-child{grid-column:1/-1}}";
  function addCss() {
    if (document.getElementById("seax-hlookup-css")) return;
    var s = document.createElement("style"); s.id = "seax-hlookup-css"; s.textContent = CSS; document.head.appendChild(s);
  }
  function esc(t) { return String(t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function sum(m, ks) { return ks.reduce(function (s, k) { return s + (m[k] || 0); }, 0); }
  function pc(a, b) { return b ? Math.round(a / b * 100) : 0; }
  var MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function day(iso) { var p = String(iso).split("-"); return p.length === 3 ? (+p[2]) + " " + MON[+p[1] - 1] + " " + p[0] : iso; }
  function rankOf(D, name) {
    var list = Object.keys(D.areas).sort(function (a, b) { var A = D.areas[a], B = D.areas[b]; return B.twMix["5"] / B.twRated - A.twMix["5"] / A.twRated; });
    return list.indexOf(name) + 1;
  }
  function ord(n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function render(box, D, name) {
    var out = box.querySelector(".hl-out"), a = D.areas[name];
    if (!a) { out.innerHTML = ""; return; }
    var X = D.essex, n = Object.keys(D.areas).length;
    var e5 = pc(a.eatMix["5"], a.eatRated), t5 = pc(a.twMix["5"], a.twRated), low = sum(a.eatMix, ["2", "1", "0"]);
    var xe5 = pc(X.eatMix["5"], X.eatRated), xt5 = pc(X.twMix["5"], X.twRated), r = rankOf(D, name);
    var facts = [
      a.eatRated.toLocaleString("en-GB") + " restaurants, cafes, takeaways, pubs, hotels and mobile caterers in " + esc(name) + " have a hygiene rating. " + e5 + "% have the top rating of 5, against " + xe5 + "% across Essex.",
      a.twMix["5"] + " of its " + a.twRated + " rated takeaways and sandwich shops (" + t5 + "%) have a 5, against " + xt5 + "% across Essex. That is the " + (r === 1 ? "best" : r === n ? "lowest" : ord(r) + " best") + " of Essex's " + n + " council areas.",
      low ? low + " place" + (low === 1 ? " was" : "s were") + " rated 2 or below at their last inspection, meaning improvement was needed." : "None was rated 2 or below at its last inspection.",
      a.awaiting + " more " + (a.awaiting === 1 ? "is" : "are") + " waiting for a first inspection, usually because they are new or have changed hands."
    ];
    var keys = ["5", "4", "3", "2", "1", "0"], lab = { "5": "5 Very good", "4": "4 Good", "3": "3 Generally satisfactory", "2": "2 Improvement necessary", "1": "1 Major improvement necessary", "0": "0 Urgent improvement necessary" };
    var max = Math.max.apply(null, keys.map(function (k) { return a.eatMix[k]; }));
    var lows = (a.lowest || []).map(function (p) {
      return "<li><span class=\"hl-r\">" + p.rating + "</span><a href=\"" + esc(p.url) + "\" target=\"_blank\" rel=\"noopener\">" + esc(p.name) + "</a>" +
        (p.pending ? "<span class=\"hl-pend\">New rating pending</span>" : "") +
        "<span class=\"hl-meta\">" + esc(p.type) + (p.town ? ", " + esc(p.town) : "") + (p.pc ? " " + esc(p.pc) : "") + ". Inspected " + day(p.date) + ".</span></li>";
    }).join("");
    out.innerHTML = '<p class="hl-name">' + esc(name) + "</p>" +
      '<p class="hl-sub">Places to eat out with a published food hygiene rating, as at ' + esc(D.asOfLabel) + ".</p>" +
      '<div class="hl-tiles">' +
        '<div class="hl-tile"><b>' + e5 + "%</b><span>of places to eat rated 5</span></div>" +
        '<div class="hl-tile"><b>' + t5 + "%</b><span>of takeaways rated 5</span></div>" +
        '<div class="hl-tile"><b>' + a.awaiting + "</b><span>awaiting a first inspection</span></div>" +
      "</div>" +
      '<ul class="hl-facts">' + facts.map(function (f) { return "<li>" + f + "</li>"; }).join("") + "</ul>" +
      "<table><thead><tr><th>Rating</th><th class=\"n\">Places to eat</th></tr></thead><tbody>" +
      keys.map(function (k) {
        return "<tr><td>" + lab[k] + '<span class="bar r' + k + '" style="width:' + Math.max(1, Math.round(a.eatMix[k] / (max || 1) * 100)) + '%"></span></td><td class="n"><b>' + a.eatMix[k].toLocaleString("en-GB") + "</b></td></tr>";
      }).join("") + "</tbody></table>" +
      (lows ? '<div class="hl-low"><h4>Rated 0 or 1 at their last inspection</h4><ul>' + lows + "</ul></div>" : '<p class="hl-note">No place to eat out here was rated 0 or 1 at its last inspection.</p>') +
      '<p class="hl-note">' + (D.notes || []).map(esc).join(" ") + " Source: " + esc(D.source) + ".</p>";
  }
  function mount(box) {
    if (box.getAttribute("data-mounted")) return; box.setAttribute("data-mounted", "1"); addCss();
    var src = box.getAttribute("data-src");
    box.innerHTML = "<h3>Check food hygiene in your area</h3>" +
      '<p class="hl-intro">Choose any of the 14 Essex council areas to see how its restaurants, takeaways and pubs are rated, and which were rated 0 or 1.</p>' +
      '<select aria-label="Choose your area"><option value="">Loading the 14 areas…</option></select><div class="hl-out" aria-live="polite"></div>';
    var sel = box.querySelector("select");
    fetch(src, { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (D) {
      var names = Object.keys(D.areas).sort();
      sel.innerHTML = '<option value="">Choose your council area…</option>' + names.map(function (n) { return '<option value="' + esc(n) + '">' + esc(n) + "</option>"; }).join("");
      var saved = ""; try { saved = localStorage.getItem("seax-hlookup") || ""; } catch (e) {}
      if (saved && D.areas[saved]) { sel.value = saved; render(box, D, saved); }
      sel.addEventListener("change", function () { try { localStorage.setItem("seax-hlookup", sel.value); } catch (e) {} render(box, D, sel.value); });
    }).catch(function () { sel.innerHTML = "<option>Sorry, the figures did not load. Please try again.</option>"; });
  }
  function mountAll(root) { Array.prototype.forEach.call((root || document).querySelectorAll(".seax-hlookup"), mount); }
  window.SeaxHygieneLookup = { mount: mount, mountAll: mountAll };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { mountAll(); }); else mountAll();
})();
