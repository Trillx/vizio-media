# Compatibility and household accounts

## Design decisions

The Conjure entry point uses the `vizaio app launch-config 17 4 URL` command. The browser engine version, actual key mappings, media policies, and decoder behavior remain hardware observations to collect. No Android assumptions or permanent installation are part of this design.

Use one Python process and SQLite. Keeping the frontend and video on the same origin removes a CDN, CORS policy, and external TLS from the first playback test. MP4 byte ranges let the TV seek without a media proxy or local transcoding. The test file is small enough for repeatable checks over the home network. Low resolution is deliberate for the first codec test and says nothing about maximum supported resolution.

Keep the page's focus as explicit rows. The controller clamps horizontal movement and moves to the same available column in adjacent rows. A modal replaces those rows and restores its opener on Back. The player has a timeline row above four control buttons. Left/Right select a button and OK activates it; Up selects the timeline, where Left/Right seek by ten seconds. Down restores the last selected button. The timeline is an accessible slider with a visible thumb and current-time attributes. Mouse clicks use its displayed bounds, including stage scaling, to calculate absolute positions. Focus keeps the timeline visible; otherwise playback controls hide after inactivity and wake on navigation or pointer movement. Numeric key codes are fallbacks and the diagnostic recorder preserves actual observations. TV-owned buttons are left to the firmware when no action is mapped.

Progress for the test title is scoped to the active household profile. The original progress migrates to the default Household profile. Catalog IDs use provider, media type, and provider identifier. Diagnostic entries contain bounded scalar fields and stay separate from media and static assets. Catalog and PIN screens suppress key diagnostics.

## Visual plan

The production home uses the approved Cinema shelves layout in charcoal and white. A 365px feature and landscape title shelves scroll beneath fixed navigation and genre buttons. Popular titles lead the screen, followed by the selected profile's actual playback and Trakt watchlist, movie genres, and catalog recommendations. The screening room remains available below these collections.

Georgia supplies 69px film headings and 54px dialog headings. Arial/Helvetica supplies 29px shelf headings and 19px to 25px labels and controls. The stage remains 1920 x 1080 with 94px side insets, scaled uniformly to the browser viewport. White focus rings remain visible without animation. The 52px player timeline and clickable ten-second skip buttons retain their existing interaction.

The shared palette uses `#151515` for the stage, `#242424` for raised surfaces, `#2e2e2e` for secondary controls, `#f5f5f1` for primary text, `#ffffff` for focus, and `#bdbdb7` for supporting text. Details, account manager, and the player use the same neutral colors. Pass and Fail retain semantic colors. System fonts, ES5, XMLHttpRequest, and explicit colors preserve the existing TV baseline.

[Home discovery](home-design.md) records the composition, endpoint contracts, public caches, private profile data, error states, and remote behavior. [Deployment](deployment.md) covers Linux and Proxmox operation. TV hardware remains the source of truth for scrolling, image decoding, and browser support.

## Code boundaries

- `app/config.py` resolves the LAN interface and environment settings.
- `app/store.py` owns SQLite transactions, progress, and diagnostic retention.
- `app/main.py` owns HTTP validation, local access restrictions, and static/media responses.
- `web/remote.js` normalizes candidate keys and computes bounded focus movement.
- `web/app.js` handles views, video state, diagnostic requests, and progress.
- `scripts/download_sample.py` owns the only required first-run media download.

The account milestone adds these boundaries:

- `app/security.py` owns password hashing, login throttling, and the Fernet credential vault.
- `app/integrations.py` owns fixed official API hosts, encrypted configuration, OAuth state, token refresh, and disconnect.
- `app/catalog.py` normalizes TMDB, Trakt, and sample metadata, including stable IDs and bounded metadata/art caches.
- `app/discovery.py` composes public home collections and uncached profile-specific playback and watchlist data.
- `web/home.js` renders home discovery and supplies its stable focus rows to the shared controller.
- `app/providers.py` defines the source-provider interface and independently implements account filename matching.
- `app/routes.py` owns local owner administration, profile sessions, account operations, and catalog routes.
- `web/library.js` uses the existing focus controller for catalog, profiles, and account screens.
- `web/service-link.js` coordinates browser polling at the server-provided interval. The server enforces the interval independently.
- `web/manage.*` implements the owner interface on loopback. It never loads the TV's diagnostic logger.

`run.py` binds separate LAN and loopback sockets for one Uvicorn worker. Per-profile service locks serialize refresh and sign-in transitions. Both rotated tokens persist in one SQLite transaction. Application settings cannot change while accounts are linked or a device sign-in is pending. These locks require the documented single-worker deployment.

See [account setup](accounts-and-search.md) and [source search and playback](playback.md). `app/playback.py` owns source selection, Real-Debrid preparation, file mapping, and a bounded streaming relay. `app/coco.py` invokes the separately licensed compatibility worker over JSON. Its upstream provider source remains in the pinned, unchanged archive. Kodi is not required. License boundaries and source provenance are recorded in [third-party notices](../THIRD_PARTY_NOTICES.md).
