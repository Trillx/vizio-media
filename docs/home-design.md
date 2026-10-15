# Home discovery

The production home uses Cinema shelves in charcoal and white at `/`. It keeps live catalog discovery separate from profile-specific data.

The first screen has the existing navigation, genre buttons, a compact featured title, and a landscape shelf. The default view opens with Popular this week, followed by real Continue watching and My list rows when available, Comedy movies, Horror movies, and titles related to the feature. Comedy, Horror, Sci-fi, and Animation open their own collections. The local screening room remains below the catalog.

| Role | Color |
| --- | --- |
| Stage | `#151515` |
| Raised surface | `#242424` |
| Secondary control | `#2e2e2e` |
| Main text | `#f5f5f1` |
| Focus ring | `#ffffff` |
| Supporting text | `#bdbdb7` |

Georgia film headings, Arial controls, the 1920 x 1080 stage, and the 94px side inset remain. The feature is 365px high, its title is 69px, shelf headings are 29px, and cards have 272px by 156px art. The content scrolls beneath fixed navigation and remote hints. Dialogs, account manager, and player controls share the neutral palette. Pass and Fail retain their semantic colors.

## Catalog and personal data

`app/discovery.py` composes catalog collections separately from personal data. `web/home.js` renders them through the shared controller in `web/app.js`.

| Endpoint | Content |
| --- | --- |
| `/api/home?genre=all` | Feature, genre definitions, popular, comedy, and horror shelves |
| `/api/home?genre=comedy` | Feature and selected genre collection |
| `/api/home/shelf?genre=comedy&page=2` | One collection page, bounded to pages 1 through 500 |
| `/api/home/related/{media_id}` | TMDB movie or series recommendations for a catalog title |
| `/api/home/personal` | Active profile's saved local playback and Trakt watchlist |

TMDB supplies weekly trending titles, movie genre definitions, genre discovery, and related titles. Public metadata uses the existing six-hour cache and same-origin artwork proxy. Failed collections can show saved titles or an individual retry while other collections remain available. An initial failure has an explicit retry. Without catalog setup, the screen labels its local sample data and offers setup guidance. Recommendations describe catalog relationships rather than claiming personal taste matching.

Personal responses require an unlocked profile and use `Cache-Control: no-store`. They never enter the public metadata cache. Continue watching appears only for a saved, unfinished local trailer. My list reads up to 100 Trakt watchlist entries, enriches the first six with catalog art, and retains the existing notice at the provider limit. Empty, disconnected, expired, and unavailable states have a next action. Profile changes clear the old person's content immediately, and asynchronous results are checked against the current profile before rendering.

## Interaction

The D-pad moves between navigation, genres, feature, cards, and page controls. Left and Right move through each horizontal shelf, scrolling the focused card into view. OK opens existing title details. Back restores the exact card after details, returns a genre or My list view to For you, and exits playback using the existing player behavior. Focus uses stable IDs while asynchronous content arrives. Pagination can reach every title in a collection page.

The player retains clickable ten-second skip controls and a D-pad timeline. The licensed local trailer remains the only playable video. Catalog discovery and account file search do not resolve remote playback.

The frontend keeps ES5 syntax, XMLHttpRequest, system fonts, explicit colors, and the existing scale model. Browser checks cover the interaction at 1080p and 720p. Scrolling and image decoding still need confirmation on the television's actual browser.
