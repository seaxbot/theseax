# Facebook groups desk

The Seax Page is a member of about 150 Essex Facebook groups. Meta has no API for posting into groups, so the desk posts through the owner's Chrome (Claude in Chrome), logged in to Facebook and acting as The Seax Page. It runs as a scheduled task five times a day, weighted towards the evening (see "Automated runs" and "Timing"). The one-tap queue at theseax.com/groups/ (groups/index.html) shows the same matching for anyone posting by hand.

Owner's instructions (20 Nov 2026): post Seax stories into the relevant Essex groups automatically, wherever it is good to do so, optimising for group rules, time-sensitive stories and people's genuine information needs; join other relevant groups too. Posts go out as The Seax Page only, never the owner's personal profile, and never into groups run by Essex Live.

## Files
- data/fb-groups.json: the groups (members, rules, status, limits, owner, approval behaviour). The queue page reads it live.
- data/fb-group-log.json: every group post and join. "posts": {g: group key, s: story id, t: epoch ms, h: headline, result: live | pending | declined | removed}. "paused": true stops all posting (see Stop rules).
- groups/index.html: the queue. Matches stories to groups, varies the wording per group and tags each link ?ref=fbg-<group key> so GoatCounter shows which groups send readers.

## Group fields
- status: "on" (ready), "caution" (strict rules, low limit), "hold" (cannot post yet, e.g. no post box for the Page, join pending, account too new), "off" (never post: Essex Live, rules ban news links or Pages, auto-declines, dead).
- kind: town and crime groups need the story's place or headline to contain one of the "match" words; county groups take only the lead and top two front-page stories; politics takes council, planning and politics stories; events groups take What's On stories.
- perWeek: most posts in any seven days. onlyTags / avoidTags: story tags allowed or barred. days: weekdays the group allows (0 = Sunday). approval: "instant", "admin approval" or "auto-declined", recorded as posts are made. owner: the "Group by" banner, when there is one.

## Hard limits
- DAILY TARGET 20 (owner, 24 Nov 2026 23:30: "be more accurate with the posting and location etc - aim for 20 tomorrow"). From Wednesday 25 November aim for 20 group posts a day and never more than 20, spread by run as 07:41 up to 3, 12:41 up to 5, 17:41 up to 5, 19:41 up to 3, 20:41 up to 4. Accuracy comes before the count: a run that cannot find a correct, rule-passing post leaves the slot empty. Every post must pass the PRE-POST CHECK below. The rest of this line is the older limit, kept for the record: At most 25 group posts a day across all groups from 23 November 2026 (owner, 23 Nov 17:04: "increase to 25 posts across those times"; it was 15, and 12 before that), at most 7 in any one run (each run's own limit is under "Automated runs"), at least 8 minutes between posts. Of those 25, no more than 8 a day may go to groups The Seax has never posted in. Do not raise the cap further yourself: the owner decides.
- At most 3 groups per story, at most one county-wide group per story. A post that was declined or removed does not count towards its story's 3.

## Picking the groups (owner, 23 Nov 2026: "pick best groups by size and relevance to story")
For each story, rank every group that may take it (status on or caution, rules allow it, within perWeek and the 20-hour gap, not already given this story) and post to the top of the list:
1. Relevance first: a group for the exact town or area the story happened in beats a wider area group, which beats a county-wide group. The story's place or headline must match the group's "match" words (county groups excepted).
2. Then size: among equally relevant groups, the most members first, then the most posts a month (an active group of 10,000 beats a quiet one of 15,000).
3. Prefer groups where The Seax has posted before and the post went live ("approval": "instant" or a live post in the log), and skip groups with a removal or decline. Overlapping groups for one town (e.g. two Chelmsford Community groups): one per story per day.
4. Spread the day: across the 25, cover as many different towns and groups as the stories allow rather than sending one town five posts.

## If a post is removed or declined (owner, 23 Nov 2026: "if one gets removed or refused try another")
When a run finds a post was declined or removed (step 2 of each run), switch that group off as below, then give the same story to the next group on its ranked list in this run, if the story is still under 12 hours old (6 for safety and disruption) and the rules above still allow it. It counts towards the daily 25 and the run's limit. Try at most one replacement per removed post, and none for a story removed in two groups (the story, not the group, is probably the problem). The stop rule still applies: more than 2 declines or removals in one day pauses the desk.
- One post per group per day, at least 20 hours apart; never the same story twice in a group; never more than the group's perWeek.
- Never identical wording in two groups. Write each post fresh from the story: plain English, the useful fact first, no hype, no hashtags, no emoji, no "click here". End with the tagged link.
- SHORT AND HUMAN (owner, 23 Nov 2026: "make the Facebook groups wording a bit more human and short then give the link"). One or two short sentences, about 35 words at most, written the way a well-informed neighbour would pass the news on in the group: conversational, warm, no headline-style title line, no newsroom jargon, no bullet lists, no "The Seax reports". Then the tagged link on its own line, nothing after it. Example: "Big one for Rayleigh and Hockley: ministers have told Rochford council to consult on its Local Plan from 7 December, with the six large housing sites councillors removed put back in." then the link. Special pushes below keep their own angle but follow this length and tone too.
- Every fact in a post must be in the story itself. Never add a quote, a reason or a claim ("X says it shows...") the story does not carry.
- The owner's computer is a Mac: to clear a composer use cmd+a then Backspace (ctrl+a does nothing). Facebook keeps unsent drafts and restores them when the composer reopens, so before typing check the composer is empty; if it is not, clear it first. Read the whole draft in a screenshot before pressing Post.
- Every post must show the story's real picture as the link preview. If the preview does not load or shows no picture, close the composer without posting and skip that post.
- PICTURE MUST FIT, OR USE THE MAP (owner's rule, 22 Nov 2026, after the Colchester B&M opening story went into a Colchester group with a photo of Colchester Castle: "that looks weird"). Before writing each post, open the story at theseax.com/story/<id>/ in Chrome and look at its picture and caption. If it is a general town photo, a Wikimedia Commons photo or a stock photo AND it does not show where the story took place or what the story is about, switch the story to the map first: run `python3 tools/usemap.py <story-id> "<why, a few words>"` in the repo (it adds the id to data/map-pictures.json, sets the map on the live site, rebuilds and pushes), wait about two minutes, reload the story page until the map shows, and only then post. If in doubt, use the map.
  - Fine as they are (no map): a picture of the actual place or subject (a council's own building on a council story, County Hall on an Essex County Council story, the venue, shop, school or street the story is about); the owner's library photos chosen by the site's rules (police, fire engine, ambulance, bus, Post Office, security patrol, fog, Christmas and the rest); Essex Police pictures; sport photos; the owner's own supplied pictures for a story; a charity's own logo on a story about that charity (owner's rule, 22 Nov 2026: charity stories always use the charity logo, never a place photo).
  - Needs the map: a landmark or town view that is not where the story happened (Colchester Castle on a shop opening, a seafront view on an inland street), a stock photo of a generic scene that could mislead, or anything showing the wrong town.
  - If the Facebook link preview still shows the old picture after the switch, open https://developers.facebook.com/tools/debug/ in the same Chrome, paste the story URL and press "Scrape Again", then reopen the composer. If it still shows the old picture, skip that post this run.

## Cav Miley badger story push (owner, 23 Nov 2026 13:46: "Tweet and Facebook out the Cav Miley story widely")
Until the end of Tuesday 24 November, the story "chelmsford-city-cav-miley-badger-hole-training-walton-hersham" goes
first in every run, ahead of other stories, to: Chelmsford town and area groups, Southend groups (Miley was Southend
United's captain and an FA Trophy winner there), and Essex-wide community groups, wherever the group allows sport or
general local news and links. It counts towards the usual daily and per-run caps (no group gets it twice, and the
never-posted-before limit still applies); within those caps, give it as many groups as possible. Keep the wording light
and friendly (it is a funny story, not a mocking one), for example: "Not your usual injury report: Chelmsford City
captain Cav Miley fell down a badger hole in training. Mark Cooper explains." Its picture is the owner's split screen of
Miley and a badger, which fits, so no map. Skip groups whose rules bar sport or news links.

## Crime checker push (owner, 20 Nov 2026: "the top story could go everywhere, saying you can select your neighbourhood"; scaled back at 17:41: "I don't want to push it as we've just launched; select those that will push it through no problems and won't be held")
Until the end of Sunday 22 November, the story "essex-recorded-crime-september-2026-police-data" may also go to groups beyond the usual 3, but ONLY groups whose "approval" is "instant" in data/fb-groups.json (posts from The Seax have gone live there straight away) and that are town or crime groups for an area the story covers. Never to groups with approval "admin approval", "auto-declined" or unknown (blank), never to "caution" groups, never to events or politics groups. Every other hard limit still applies (12 a day, 3 a run, 8 minutes apart, one post per group per day and 20 hours apart, perWeek), and public safety items still go first. If any post in this push is declined, removed or held, stop the push at once and report it.
- At the time of writing that means: Laindon and Basildon (196202630394637), Our Thurrock Community (1601081196881282), Little Thurrock Community Forum (1488274811502316, but not on the same day as Our Thurrock), Harlow Community (1236677473201839). If another town group's approval becomes "instant" during the weekend (a Seax post there went live at once), it may join.
- Make each post local: lead with that area's own figures from data/crime/essex-2026-09.json (the same numbers the story's crime checker shows), September 2026 against September 2025, using the neighbourhood that matches the group (Basildon; Chafford Hundred and Grays for Thurrock groups; Harlow's neighbourhood by name). Say plainly what rose and what fell. Never "soaring", "crime wave" or similar.
- Then one line on the checker, e.g. "You can look up any of Essex's 56 police neighbourhoods, crime by crime, with our new crime checker." End with the tagged link plus "#check" so it opens at the checker. Write every post fresh.

## What to post (in this order)
1. Public safety and disruption happening now or today: road closures and crashes (say if reopened), police appeals for witnesses, missing people (only while still missing: check the story is still on theseax.com and search for a "found" update first; never post a missing-person appeal more than 12 hours old without that check), fires, water or power cuts, school closures, weather warnings.
2. Time-bound information people can act on: events this weekend, consultations closing soon, service changes, bin and transport changes, health services (NHS Essex), council decisions affecting a town.
3. Strong local interest: a town's own news, Southend United and Colchester United match previews on match days, results the morning after.
- A story must still be live on theseax.com (not in tools/takedown.txt) and be under 12 hours old (under 6 hours for safety and disruption items, which go first). Stories from the previous day only if still current (e.g. a road still closed).
- Groups that hold posts for admin approval get time-sensitive items only in the 07:41 or 12:41 run, so approval can land in time (a match preview posted at 11:15 is no use if approved after kick-off).
- The Brentwood School abuse review story ("brentwood-school-safeguarding-review-british-fencing-own-review") was posted by hand at the owner's request on 20 Nov (7 Brentwood groups, 2 Wickford, Essex UK Community). Do not post it again anywhere, and never post follow-ups that identify a victim-survivor.
- Never post: court stories (Court tag), anything about a person charged but not yet convicted, inquests, stories involving children's welfare, anything the legal gate holds, sponsored or deals content, and the same story into overlapping groups of one town in one day (rotate them).
- Match the group: town and crime groups only get stories from their own area; events groups only events; the politics group only council, planning and politics; county groups only the day's biggest Essex story.

## Automated runs
Scheduled task "Seax Facebook groups desk", every day at 07:41, 12:41, 17:41, 19:41 and 20:41 UK time (from 23 Nov 2026; before that 07:41, 09:41, 12:41, 17:41 and 18:41). Posts per run, so no run uses Chrome while the Essex Police Facebook desk does (it starts at :05 past 8, 12, 16 and 20): 07:41 up to 3 and finished by 08:03; 12:41 up to 7 (it starts after the 12:05 police run); 17:41 up to 7; 19:41 up to 3 and finished by 20:03; 20:41 up to 7. That allows 27, so the daily 25 is the limit that bites. Needs the owner's computer awake with Chrome open.

### Timing (owner asked 23 Nov 2026 to optimise the best time to post)
Evidence: The Seax's own GoatCounter figures for 16 to 23 Nov (site visits by hour: weekday peaks 08:00, 11:00 to 12:00, 17:00 and 19:00 to 22:00, with 21:00 the busiest; quietest 09:00 to 10:00 and 13:00 to 14:00), the group posts so far (the Brentwood story posted 18:51 to 19:14 on a Friday brought 28 visits in three hours and 42 from one group; Saturday 14:45 to 15:11 posts brought 0 to 5 each), and published UK Facebook studies, which agree that 7 to 9pm after dinner is the biggest audience, with lunchtime and the morning commute next.
- 07:41: public safety and disruption first (road closures, appeals, weather), same-day events, and anything for groups that hold posts for approval. Morning commute.
- 12:41: lunchtime. Council decisions, consultations, service changes, health. Last run for approval-held groups.
- 17:41: commute home. Disruption still live, tonight's events, match-day previews for evening games.
- 19:41 and 20:41: prime time. Save the day's strongest local-interest stories (the ones people will read and share) for these two runs, and fill the 20:41 run's 7 slots (and 19:41's 3) when there is enough good material. Stories must still be under 12 hours old.
- Saturday and Sunday: the same runs. Weekend afternoons are the quietest time on Facebook, so do not hold weekend stories for an afternoon run.
- Breaking public safety news still goes out at the next run whatever the time.
- Re-check this every couple of weeks: GoatCounter (theseax.goatcounter.com, signed in on the owner's Chrome) shows visits by hour (View by: hour) and each group's clicks as fbg-<group key> under Top referrers. Move a run if the evidence shifts, and note why here.

### One run at a time
Two desk sessions posted at once on 23 Nov 2026 and put the same story into two Chelmsford groups. So: at the start of a run, after pulling, look at the newest post in data/fb-group-log.json. If it is under 25 minutes old and you did not make it, another run is in progress: do not post, and end the run saying so. Pull again just before each post and check the same thing.

### PRE-POST CHECK (owner, 24 Nov 2026, after 24 Nov's posts sent the Cav Miley story into Essex UK Community twice and a Maldon and Tendring house prices story into Harlow Community)
Immediately before EVERY post, pull the repo again and run these checks against data/fb-group-log.json and edition.json. If any fails, do not post; pick another group or story, or leave the slot empty.
1. COUNT: count today's posts in the log by UK date (all results, including pending, declined and removed). If it is already 20, stop the run.
2. GROUP TODAY: this group has no post in the log in the last 20 hours, under any story.
3. STORY IN GROUP: this story id has never been posted to this group, on any day. Check by story id AND by headline (the same story can carry a new headline).
4. STORY SPREAD: the story has fewer than 3 posts today (live or pending) and at most one in a county-wide group.
5. LOCATION: the group's own area must be where the story happened. For town, crime and community groups, the story's "place" or headline must contain one of the group's "match" words, AND the story's "areas" must include the group's district. A story about Maldon or Tendring never goes to a Harlow group; a Chelmsford story never goes to a Southend group unless it is about Southend too (the Cav Miley push named Southend groups by the owner's choice; that push has ended). County-wide groups (Essex UK Community and similar) only take county-wide stories ("areas" includes "all") or the lead. When unsure, do not post.
6. STATUS: the group is "on" or "caution" in data/fb-groups.json (never "off" or "hold"), its "days" allow today, its perWeek is not used up, and its onlyTags or avoidTags allow the story's tag.
7. STORY STILL GOOD: the story is live in edition.json, not in tools/takedown.txt, within the freshness rules, and not excluded (court, inquests, children's welfare and the rest under What to post).
8. WORDS: the post names the right town, says nothing the story does not, and is not worded like any other post today.
Log each post the moment it is made (before the next one), with the group key, story id, time, headline and result, and push, so the next check sees it.

Each run:
1. Get the repo (seaxbot/theseax) and read this file, data/fb-groups.json and data/fb-group-log.json. If "paused" is true, stop and report why.
2. In Chrome, open facebook.com/notifications. For each "An admin declined your post" or "removed your post": open it, read the reason, mark the post's result, and set that group to "off" with the reason in "note" (one decline is enough). Mark pending posts that have since appeared as "live". A group that holds posts and leaves one pending for over 48 hours drops to perWeek 1.
3. Read edition.json from the freshly pulled repo (the shell cannot reach theseax.com; Chrome can, at theseax.com/groups/) and choose up to the run's limit of posts (from 25 Nov: 3, 5, 5, 3, 4 for 07:41, 12:41, 17:41, 19:41, 20:41, daily target 20) by the rules above (replacements for removed or declined posts first, then the ranked groups), counting today's posts in the log against the daily 20, and putting every chosen post through the PRE-POST CHECK.
4. For each: open the group, check the top-left of the composer says "The Seax" (if it shows a personal name, stop the run), write the post, wait for the picture preview, press Post. Note whether it went live or "submitted to group admins for approval". Log it at once.
5. Commit data/fb-group-log.json and data/fb-groups.json changes with a short message and push.
6. Report in a few lines: what was posted where, any declines, anything paused.

## Bulk join of 21 Nov 2026 (owner's request)

The owner asked for The Seax to join as many relevant Essex groups as possible. About 465 were joined by search on 21 Nov. The largest town, crime and travel groups are in data/fb-groups.json with a note saying they are not yet vetted. Before the FIRST post in any of them: open the group, check the Group by banner (never Essex Live) and the rules, and set status off or caution if links, news or Pages are banned. Never post in one on 21 Nov (join day). Start them gently: no more than 8 never-posted groups a day (4 until 23 Nov 2026), perWeek 1 until a post has gone live without complaint, then 2. Groups that asked membership questions are not listed; leave them unless the Page can answer honestly. More joining may continue on later days at the owner's request; stop at once on any Facebook warning (see Stop rules).

## Second join round, 22 Nov 2026 (owner's overnight request)

Eighteen more public groups were joined in the early hours of 22 Nov (in data/fb-groups.json with "joined": "2026-11-22") and about 20 private groups were requested, including the big South Woodham Ferrers, Rayleigh, Braintree, Halstead, Rochford, Loughton, Wickford and Thurrock groups. Never post in the 22 Nov groups on 22 Nov (join day); from 23 Nov treat them like the 21 Nov bulk-join groups (vet before the first post, at most 8 never-posted groups a day, perWeek 1). Three joined groups are "hold" because they ask members to agree to their rules before posting, which only the owner may do. Private groups appear here only once an admin has approved the Page; many are waiting for the owner to answer their membership questions at facebook.com/groups/joins. The Mersea Locals (15,000 members) allows self-promotion once every two weeks and no politics.

## Joining groups
- At most 2 new groups a week, in the 12:41 run, only to cover a town with no active community group (as of 20 Nov 2026: Brightlingsea, Wivenhoe, Manningtree, Frinton and Walton, Thaxted, Ongar, Chigwell and Buckhurst Hill, South Woodham Ferrers, Benfleet, Leigh-on-Sea, Shoeburyness, Grays town centre, Tilbury, Stanford-le-Hope, Ingatestone, Writtle, Danbury).
- Only real community groups for that town, ideally over 3,000 members and active (posts most days). Check the "Group by" banner (never Essex Live; another news outlet is fine, note it as owner) and the rules (skip groups that ban links, news, promotion or Pages).
- Never answer join questions with anything untrue. If a group asks questions the Page cannot honestly answer (e.g. "do you live in X?"), skip it.
- Add each joined group to data/fb-groups.json with status "on", perWeek 2, and record the join in the log. Do not post in a group on the day it was joined.

## Stop rules
Set "paused": true in data/fb-group-log.json with the reason, push, stop the run, and report, if Facebook shows any of: a warning or restriction on the Page or the account, "you're temporarily blocked", a security check or CAPTCHA, a login screen, or more than 2 declines in one day. Only the owner unpauses. Never attempt a CAPTCHA or a login.

## Upkeep
- Before adding a group, read its "Group by" banner and rules.
- Re-check "hold" groups with no post box once a month.
- Re-audit all groups every few months.
