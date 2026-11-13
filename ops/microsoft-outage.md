# Microsoft outage desk (owner's request, 13 Nov 2026: "keep this story updated!")

You keep ONE owner story up to date: the global Microsoft outage story at
story/microsoft-outage-site-updates-slower/index.html, pinned above the lead by data/pinned.json.
It is a hand-made owner page: the build never regenerates it, and the hourly newsroom is told to
leave it alone. Never use em dashes anywhere.

## 0. Should this run do anything?
- Work out the UK time now. Only work on 13 or 14 November 2026. On 14 November, only work before 12:00.
  Otherwise end the run straight away without changing anything.
- If the story already says Microsoft has fully restored services (the "RESOLVED" step below has
  been done) and nothing has changed since, end without publishing.

## 1. Research (light: at most 6 searches or fetches, in parallel where you can)
- WebSearch (mode "extended") "Microsoft outage latest" and "Microsoft 365 outage update today".
- Look for: Microsoft's latest status (services restored? partial recovery? cause?), how long it
  has lasted, which services are still affected, and UK impact.
- ESSEX ANGLE (most valuable): one search for "Essex Microsoft outage" (council, NHS trust, hospital,
  GP, schools, police, businesses). Only use an Essex detail when a readable source states it.
- Only facts from sources you read THIS run, dated today. Never guess. Downdetector shows user
  reports, not confirmed faults: say so if you use its figures.

## 2. Update the story only if there is genuinely new information
If nothing material has changed since the "Updated" time on the page, end without publishing.
Otherwise edit the page in place (keep its template, layout, share buttons and the Downdetector figure):
- Rewrite the opening paragraph so it leads on the latest position; fold older detail lower down.
  Keep it tight: about 6 to 9 paragraphs at most. Write like a world-class journalist.
- Copyright: paraphrase. At most one quote per source, under 15 words. Never copy a source headline.
- No repetition: no fact repeated across headline, standfirst and paragraphs; the first and second
  paragraphs must not repeat each other.
- Update the "Sources:" line with every outlet used (links to the articles), keeping Downdetector
  while its picture is on the page.
- Set the "Updated" time (span id="updated": both the datetime attribute, in UTC, and the shown
  UK time like 14:20) and meta article:modified_time to now.
- HEADLINE: change it only when the news has moved on (e.g. services restored). Never use "second
  day" (owner's wish). When you change it, change it EVERYWHERE: <title>, og:title, twitter:title,
  the JSON-LD headline, <h1>, both data-title attributes, the WhatsApp and X share links
  (URL-encoded), data/pinned.json "headline", and the quoted headline in ops/newsroom.md
  (PINNED MICROSOFT OUTAGE NOTICE). Keep the story URL and id unchanged.
- The standfirst (p.standfirst) is about the outage itself. The pinned card summary in
  data/pinned.json (and the meta/og descriptions) carries the slower-updates message while the
  outage continues: keep it.

## 3. The slower-updates notice (owner's wish)
While Microsoft services are still disrupted, keep the yellow notice box at the top of the article
("Updates may be slower than usual today...") and the pinned kicker
"Site notice: updates may be slower today".
RESOLVED: once Microsoft or reliable outlets say services are restored, change the box text to
"Microsoft says its services are back up and running, so updates on The Seax should be back to
normal. Thank you for bearing with us." (adapt the wording to what the sources say), set the
pinned.json kicker to "Update: services restored" and its summary to one sentence on the
restoration, and update the meta/og/twitter descriptions to match.

## 4. Pin timing
data/pinned.json pins the story until midnight on 13 Nov ("until") and as a News card until
midday on 14 Nov ("newsUntil"). At the last run of 13 November (23:xx), if the outage is still NOT
resolved, set "until" to "2026-11-14T12:00:00Z" and "newsUntil" to "2026-11-14T18:00:00Z" and
update the timing sentence in ops/newsroom.md. Change nothing else in pinned.json except as above.

## 5. Check and publish
- Check: the HTML still renders (open it and read it back), no em dash (U+2014) anywhere,
  data/pinned.json parses (python3 -c "import json;json.load(open('data/pinned.json'))").
- git add only the files you changed; commit "Microsoft outage story update HH:MM";
  git pull --rebase origin main; git push origin HEAD:main. Retry the pull and push once if
  rejected. Finish the push by :32 past the hour so you never collide with the newsroom at :35.
- Do NOT touch edition.json, the newsroom tools or any other story.

## 6. Finish
One line: what changed (or "no change"), the headline now, and whether the notice still says
updates may be slower.
