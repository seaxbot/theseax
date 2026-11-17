# The Seax audio bulletin desk (07:00, 12:30, 17:00 and 23:00 UK time, every day)

The owner asked (14 Nov 2026) for a two-minute spoken news bulletin of the site's main stories, played from the "Listen" button in the My Essex row at the top of the front page. It is updated four times a day: the **morning update at 07:00**, the **afternoon update at 12:30** (owner added it on 16 Nov 2026, to match the lunchtime Facebook post), the **evening update at 17:00** and the **overnight bulletin at 23:00** UK time (owner added it on 17 Nov 2026; it stays on the site and on Alexa until the morning update), except on **Saturdays, when the evening bulletin is at 18:40** (owner's choice, 14 Nov 2026) so it can read the 3pm full-time scores, which only reach the site when the sport desk's 18:05 run publishes them. In these instructions "morning" means the morning update (slot `am`), "midday" the afternoon update (slot `mid`), "evening" the evening update (slot `pm`) and "overnight" the overnight bulletin (slot `night`). You write the script; `tools/bulletin.py` turns it into the MP3 in the owner's chosen voice and updates `data/bulletin.json`, which the player reads.

This run is fully automated. Nobody will answer questions. Never use em dashes. Do no web research: the bulletin only ever reads out what The Seax has already published. Your push must be done by 07:30 (morning) or 17:30 (weekday and Sunday evening), before the newsroom run at :35. The 12:30 midday run overlaps the 12:35 newsroom; like the Saturday 18:40 run that is fine, because you only touch audio/ and data/bulletin.json, so push as soon as you are done (aim for 12:50 at the latest). The Saturday 18:40 run overlaps the 18:35 newsroom; that is fine because you only touch audio/ and data/bulletin.json, so just push as soon as you are done (the retry loop in step 5 handles the race). The 23:00 overnight run starts as the 22:35 newsroom finishes and overlaps the sport desk's 23:05 run; the same applies, push as soon as you are done (aim for 23:15 at the latest).

## 1. Which bulletin, and is it already done?

Before 11:00 UK time this is the **morning** bulletin (slot `am`); from 11:00 to 14:59 it is the **midday** bulletin (slot `mid`); from 15:00 to 20:59 it is the **evening** bulletin (slot `pm`); from 21:00 it is the **overnight** bulletin (slot `night`).
`python3 -c "import json;d=json.load(open('data/bulletin.json'));print(d.get('date'),d.get('slot'))"` . If it prints today's UK date and this slot, stop: this bulletin exists.

## 2. Pick the stories (from edition.json only)

Read `edition.json` with Python, not by eye. In this order:

1. The lead (`lead.id`), then the `front` picks.
2. Then the strongest other stories from `stories` (and `official`, `courts`, `community` if they hold news), by `weight` and freshness.
   - Morning: published or updated since 17:00 yesterday, overnight and early news first; fill from yesterday's big stories only if the morning is thin.
   - Midday: published or updated since 07:00 today, so a listener who heard the morning bulletin gets something new. Today's lead may repeat if it is still the lead, told with the latest. Fill from the morning's biggest stories only if the morning has been thin.
   - Evening: published or updated since 12:30 today first, then the day's other big stories from since 07:00 (many listeners only hear the evening one), so a listener who heard the midday bulletin still gets something new. Today's lead may repeat if it is still the lead, told with today's latest. Fill from the morning only if the day is thin.
   - Overnight: published or updated since the evening update (17:00, or 18:40 on Saturdays) first, then the day's biggest stories (many listeners will hear it last thing at night or first thing before the morning update), so a listener who heard the evening update still gets something new. Today's lead may repeat if it is still the lead, told with the latest.
3. Aim for **five to seven news stories** (Sunday morning: three, see the Sunday morning format below), with a spread of districts (not all Southend, not all Chelmsford) and a spread of subjects (not all crime). Skip `linkOnly` items.
4. Sport: one paragraph. Morning: results since yesterday afternoon, then today's big fixtures. Midday: any results since the morning bulletin, then today's and tonight's big fixtures (skip the sport paragraph if there is nothing new since 07:00). Evening: today's results first, then tonight's fixtures. Overnight: tonight's results first (the sport desk's 22:15 run publishes the evening games), then any of today's results not in the evening update; skip the sport paragraph if there is nothing worth reading. On the Saturday 18:40 bulletin the sport paragraph matters most: read today's full-time scores for the main Essex clubs from `sport.results` (dated today), it can run to four or five sentences, and a big result can come straight after the lead. Only read scores that are in the edition; if a 3pm game has no result there yet, leave it out rather than guess. Essex results from `sport.results` (Essex clubs only: Colchester United, Southend United, Chelmsford City, Braintree Town, Billericay Town, Essex cricket, Essex rugby clubs and the rest), or today's big fixtures from `sport.fixtures` if there are no results worth reading. Only scores and fixtures that are in the edition.
**SUNDAY MORNING FORMAT (owner's request, 14 Nov 2026).** The Sunday 07:00 bulletin is different: after the opening, read **exactly three news stories** (the lead and the two strongest others, chosen as in 1 to 3), then a longer **sport headlines** section of several short paragraphs about Saturday's sport, in this order: Colchester United and Southend United first, then Chelmsford City, Billericay Town and Braintree Town, then cup ties and Essex derbies, then the Isthmian and other round-ups (Chieftains, cricket, rugby). Take it all from `sport.stories` and `sport.results` (and sport stories in `stories`): the scores, the scorers, a further round-up of other Essex results, and any manager comments or reaction, but only what a published sport story actually says (a manager quote only if it is in a published story; paraphrase it, or use one very short quote). Signpost it ("Now the sport headlines..."). Then weather and the sign-off, with no "and finally". Same length (300 to 340 words) and the same house style and legal rules. If Saturday had almost no Essex results in the edition, fill with a fourth news story instead of padding the sport.

5. Optionally one light "and finally" item (What's On, community, a festive or quirky story).
6. Weather (and `weather.warnings` if a warning is live): morning, today's high from `weather.days[0]` and tonight's low; midday, this afternoon (today's high) and tonight's low; evening, tonight's low and tomorrow from `weather.days[1]`; overnight, tonight's low and tomorrow from `weather.days[1]`, said as "tomorrow".

Never read a story that is not on the site. Never add a fact that is not in the published story.

## 3. Write the script

Save it to `/tmp/bulletin.txt`: plain text, **one paragraph per story, a blank line between paragraphs** (the tool puts the owner's 1.5-second pause between paragraphs, so a paragraph must never be split across a blank line).

**Fixed opening (owner's wording, 17 Nov 2026), as the first paragraph, by slot:**
- `am`: `Welcome to your morning update from the See-Ax. It's <Weekday>, the <ordinal day in words> of <Month>.`
- `mid`: `Welcome to your afternoon update from the See-Ax. It's <Weekday>, the <ordinal day in words> of <Month>.`
- `pm` (including Saturday 18:40): `Welcome to your evening update from the See-Ax. It's <Weekday>, the <ordinal day in words> of <Month>.`
- `night`: `Welcome to your overnight bulletin from the See-Ax.` with **no date** (owner's rule: it is heard either side of midnight, so a date would be wrong for half the listeners). Do not say "tonight", "today" or a day name for the bulletin itself; for stories, say "on Tuesday" or "this evening" as the story needs.
For example: `It's Sunday, the fifteenth of November.` Use only these names for the bulletin itself, never "morning bulletin", "evening bulletin" or "good morning". (Saying when a story happened, such as "a crash this morning on the A12", is fine.) The site's Listen button still says "Latest bulletin"; the Alexa title uses the slot's name.

**Fixed sign-off, as the last paragraph:**
`That's all for now. For the full stories, head to the See-Ax dot com.`

**Length:** 300 to 340 words in all. That reads at about 2 minutes 10 to 2 minutes 25 in the owner's voice.

**House style: it must sound like a person on local radio, never like a machine reading the website.** The owner rejected the first robotic version.
- Write for the ear. Short sentences. Contractions (it's, there's, they've). One or two facts per story, not five.
- Signpost: "We start in Southend, where...", "In Colchester...", "Some good news for families...", "In sport...", "And finally...". Vary them; do not start every story the same way.
- The lead gets three to five sentences; most stories get one or two.
- Numbers as they are said: "eight hundred and fifty thousand pounds", "twelve and a half years", "half past seven", "around a third". No figures with commas, no £, %, or digits for times.
- No brackets, no abbreviations a reader would not say aloud (NHS, FA, A12, M25 are fine), no web addresses except the sign-off, no headline-style phrasing ("Man, 19, charged...").
- Avoid quoting; paraphrase. At most one very short quote in the whole bulletin.
- Never use em dashes. Never use song lyrics, poems or catchphrases from songs.
- Say the site's name as "See-Ax" (the tool also fixes "Seax" automatically). If an Essex place name or surname is likely to be misread, respell it for the ear (for example "Wivenhoe" is fine; "Thorpe-le-Soken" is fine; check anything unusual).

**Legal and editorial rules (the same as ops/newsroom.md):**
- Crime and court stories: only what the published story says, in the same terms ("has been charged with", "has been jailed for", "denies"). Never add colour, never speculate, never imply guilt before a verdict. If in doubt, leave the story out.
- Never name a child. Never describe a suicide method. Inquests only in the published wording, briefly, or leave them out.
- No graphic detail. Deaths and tragedies are read plainly and with care, and never next to a jokey link.

## 4. Make the audio

```
python3 tools/bulletin.py --script /tmp/bulletin.txt --slot <am, mid, pm or night> --stories <story ids read out, in order, comma-separated>
```

The first run in a fresh environment downloads the voice model (about 350 MB from GitHub) and installs `kokoro-onnx`; allow up to 10 minutes and a generous command timeout (run it in the background if your tool limits commands to 2 minutes, and wait for it). It prints the duration.
- Over 2:40: cut the weakest story and run it again. Under 1:50: add one more story and run it again.
- It writes `audio/bulletin-<date>-<slot>.mp3`, deletes older bulletin files and writes `data/bulletin.json` and `audio/alexa.json` (the Alexa Flash Briefing feed, owner's request 14 Nov 2026; smart speakers play whatever it points to, so every bulletin must be published this way). Do not edit those by hand.

## 5. Publish

```
git add -A audio data/bulletin.json
git commit -m "Audio bulletin <date> <morning, afternoon, evening or overnight>"
for i in 1 2 3 4 5; do git pull -q --rebase origin main && git push -q origin HEAD:main && break; sleep $((i*7)); done
```

## 6. Summary

One line: `Bulletin <date> <morning, afternoon, evening or overnight>: <duration>, <n> stories (<short list>), PUSHED <commit hash>` or what went wrong.
