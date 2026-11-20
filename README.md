# The Seax

Live Essex news, sport, weather, culture and what's on.

- `index.html` is the whole site (styles, scripts and the launch edition built in).
- `edition.json` is the live edition. The hourly newsroom rewrites it and the page reloads it every minute.
- Hosted on GitHub Pages, which republishes automatically whenever this repository changes. To use your own domain, add it under Settings > Pages > Custom domain.

- Stock photos for generic stories come from Openverse via tools/photos.py (see ops/newsroom.md, STOCK PHOTOS).

- The daily audio bulletin ("Listen" on the front page) is written at 07:00 and 17:00 UK by the bulletin desk (ops/bulletin.md) and rendered by tools/bulletin.py into audio/ and data/bulletin.json.

- Facebook groups: the Page's groups and their rules are in data/fb-groups.json, and theseax.com/groups/ is the one-tap posting queue (see ops/fbgroups.md).
