# Weekend feature desk

Owner's instructions (27 Nov 2026): "keep looking for great weekend features for that section every weekend". The Weekend
section (data/weekend.json, shown on the front page just below the lead) carries one big feature every weekend: The
Seax's own analysis, something people will take time over and nobody else in Essex has. The first two were the September
2026 police data analysis (21 to 23 Nov) and the food hygiene analysis "essex-food-hygiene-ratings-takeaways-november-2026"
(27 to 30 Nov), which is the model to follow: a fresh dataset, every Essex council area compared, a clear headline
finding, three varied charts, a look-up so readers can check their own area, and every figure triple checked.

This desk runs every Friday at 10:08 UK time. It is the only automated task allowed to edit data/weekend.json.

## 1. Is the weekend already set?
Read data/weekend.json. If its "from" is on or after this Friday 00:00 UK and its "until" is after this Sunday, the
owner has already chosen this weekend's feature: change nothing and end with "Weekend already set: <headline>".

## 2. Pick the topic (by 10:30)
Read data/weekend-log.json (past features) and data/archive.json for the last 30 days. Choose ONE topic that:
- uses official open data you can download in full and recount (government, NHS, police.uk, ONS, Land Registry, Food
  Standards Agency, DfT, Ofsted, Environment Agency, Companies House, Parliament petitions and the like);
- can be compared across all 14 Essex council areas (or every town, school, hospital, road) so every reader finds their own patch;
- has a clear, true finding that will make people want to read and share it, and suits a weekend read or the season;
- has not been a weekend feature in the last 8 weeks and has not been covered by The Seax in the last 30 days.
Ideas to consider (not a fixed list; seasonal hooks win): road crashes and casualties by road and district (DfT road
safety data, ahead of the December drink-drive campaign); Ofsted ratings of schools and nurseries; GP patients per
doctor by practice; A&E and ambulance waits at Essex hospitals; empty homes by district; fly-tipping by council (Defra);
bathing water quality at Essex beaches (spring/summer); electric car chargers per head; planning decisions and
approval times; new businesses and closures (Companies House); council tax by band and district; flood warnings; air
quality; library and leisure centre use; petitions signed by constituency.

## 3. Get and analyse the data
The shell in this session usually cannot reach government sites directly. Use the one-off GitHub Actions pattern from
the hygiene analysis: add a small script under tools/datadesk/ and a workflow under .github/workflows/ that downloads
the data and saves it to its own branch (see tools/datadesk/fsa_snapshot.py and .github/workflows/fsa-snapshot.yml),
push, wait for the run, then fetch the branch with git and analyse it here. Keep every raw file.
Write a recount script that computes every figure in the story straight from the raw files.

## 4. Write it
Follow ops/style.md, ops/newsroom.md 3a vii (headlines, including rule 14 on parts), 3a viii and x (context first: what
the data is and why it matters, then the figures), the bold summary rule (max 25 words), and the item format. Desk
"owner", "original": "data", "researched": true, "areas": ["all"], "place": "Essex", "noWhere": true, weight 6.
- Name businesses or people only where the official data names them and it is fair and in the public interest, always
  with the date of the record and a line saying it may have changed. Check every named entry on its official page.
- Include "How we did this" and where readers can check or report things themselves.
- Charts: follow CHART VARIETY in ops/newsroom.md 2k. Three charts in at least two different forms; when the data is by
  council area, one of them is the shaded Essex map (ESSEX_MAP in index.html holds the district outlines
  and label centroids; draw it with matplotlib, one-hue scale, labelled areas, a legend, as in tools/datadesk/hygiene_charts_2026_11.py,
  whose grid, map and dot-pair code can be reused; tools/datadesk/hygiene_recount_2026_11.py shows the recount). House style, alt text listing the figures, captions with source and date.
- A look-up widget when readers would want to check their own area: reuse js/hygiene-lookup.js, js/price-lookup.js or
  js/crime-lookup.js if the shape fits; otherwise write a new one the same way and wire it into tools/build.py (widgets)
  and index.html (front page reader and the weekend box "checkerType").
- Main picture: an owner photo or library photo that fits (see data/portraits.json and the image rules), or the
  feature's strongest chart as a 1200x655 image. Never a stock photo of the wrong place.

## 5. Triple check, then publish
Run tools/verify.py on the final items file with real notes for all three checks: every figure recomputed from the
raw data; an independent second source or method (the official site's own pages, a second file, a different
calculation); a read-back of the final copy. Then publish with tools/publish.py --items FILE --desk owner. Fix
anything it refuses. Confirm the story page shows the charts and the look-up after the build.

## 6. Set the Weekend box
Edit data/weekend.json: "from" this Friday 17:00 UK (in UTC), "until" Monday 07:00 UK (in UTC), keep "title" and
"strap", and set "feature": id, "kicker": "Weekend read", headline (the story's), image and alt, a one or two sentence
"dek" inviting readers in, three "tiles" (figure, label, short context; none repeating the headline figure), "cta":
"Read the full analysis", and "checker" plus "checkerType" if the story has a look-up. Push.

## 7. Fallback
If by 15:30 no analysis has passed all three checks, do not publish a half-checked one. Instead feature the strongest
Seax original story (Seax Investigates or Seax Analysis) published in the last 7 days that has not been a weekend
feature, using its own picture and three tiles drawn from its verified copy, and say so in the summary.

## 8. Log and report
Add the weekend to data/weekend-log.json: {"weekend": "YYYY-MM-DD" (the Saturday), "id", "headline", "topic", "data",
"from", "until"}. Push. Finish with a short summary starting "ALERT:" if the owner needs to know anything (fallback
used, data source failed, a check could not be done): the topic, headline, the three charts' forms, and the box times.
