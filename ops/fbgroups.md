# Facebook groups desk

The Seax Page is a member of about 140 Essex Facebook groups. Meta has no API for posting into groups, so posts are sent by hand from the one-tap queue at theseax.com/groups/ (groups/index.html). Nothing in the newsroom posts into groups automatically.

## Files
- data/fb-groups.json: every group worth tracking, audited from each group's About page on 20 Nov 2026 (members, posts in the last month, privacy, rules). The queue page reads it live.
- groups/index.html: the queue. It reads edition.json, matches stories to groups, writes a different wording for each group and tags each link (?ref=fbg-<group key>) so GoatCounter shows which groups send readers.

## Group fields
- status: "on" (ready), "caution" (strict rules, low limit, shown with a warning), "hold" (cannot post yet), "off" (rules bar news links or Pages, or the group is dead).
- kind: town and crime groups need the story's place or headline to contain one of the "match" words; county groups take only the lead and top two front-page stories; politics takes council, planning and politics stories; events groups take What's On stories.
- perWeek: most posts in any seven days. onlyTags / avoidTags: story tags allowed or barred. days: weekdays the group allows (0 = Sunday).

## Rules the queue enforces (limits in the data file)
- At most 12 group posts a day, 3 groups per story, one county-wide group per story.
- One post per group per day, at least 20 hours apart, and never the same story twice in a group.
- Local groups first, least recently used first, so the many overlapping Thurrock, Brentwood, Basildon and Southend groups rotate.
- Stories older than 24 hours are not queued. Court stories are never queued (open comment threads on live cases).
- Posts go out as The Seax Page, never the owner's personal profile, and never into groups run by Essex Live.

## Upkeep
- Re-audit the groups every few months, or when a post is removed or declined: update status, note and perWeek.
- A group that removes a Seax post goes to "off" with the reason in "note".
- Not yet checked: which groups hold posts for admin approval.
