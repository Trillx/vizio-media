# Source search and Real-Debrid playback

Implemented October 15, 2026.

Choose a movie and select **Play best available** to search and try sources automatically. Select **Find sources** to choose one yourself with the remote or mouse. Source search and preparation show a loading animation. For a series, choose a season and episode first. The search combines filename matches in the selected profile's Real-Debrid account with CocoScrapers results. Sources without format warnings come first, followed by H.264 and AAC preferences, account readiness, resolution, and size. The first source is labeled Recommended. Rows show size, quality, origin, and format warnings.

**Play best available** tries up to eight distinct source choices in that order. Each attempt has 20 seconds for preparation and 15 seconds for video startup, within a three-minute total budget. An API failure, decoding error, or startup timeout advances to the next source. Authentication and rate-limit errors stop the run. A source succeeds only after the playing video clock advances by more than a quarter second. Later playback errors leave the current movie selected. Cancel, Back, or leaving the dialog stops attempts; late responses cannot reopen playback.

Automatic playback selects a multi-file torrent only when the server identifies a matching title or exact episode, excluding extras and samples. Otherwise it skips that source for manual selection. Browser autoplay restrictions display a **Play video** button and pause the deadline until the viewer presses it.

Selecting a new source adds its magnet to the linked Real-Debrid account. Search itself adds nothing. The app lists video files if the torrent contains several, skips sample clips and non-video files, and matches episode markers for series. Selecting a file starts its preparation. The screen polls at three-second intervals and shows download progress. After five minutes, it offers another source; the remote download remains in the account and can finish there.

When the file is ready, choose **Play**, **Resume**, or **Start from beginning**. The server asks Real-Debrid for a fresh unrestricted link and optionally obtains its video/audio codec metadata. Those codec names and filename warnings guide source choice. They do not certify the television's decoder support. No local transcoding or automatic conversion occurs.

The TV receives a local authenticated stream URL. The server relays bytes in bounded chunks, preserves HTTP ranges for seeking, and refreshes an expired link once when the CDN rejects it. The server needs enough network bandwidth for the selected bitrate. It does not save the movie to local disk. API credentials and private upstream URLs stay off the TV page and out of diagnostics.

Back returns to the source list. Sources appear three per page. Left/Right on a source changes pages and keeps the row position. Down from the last source reaches Previous page and Next page; OK changes the page and retains focus on an available pagination button. In the player, Left/Right, timeline seeking, pause, and ten-second skip controls retain their existing behavior. Progress saves per profile and title or episode. Continue watching opens the matching title or episode; choose a source again to resume. Source choices expire after 20 minutes, and playback sessions expire after eight hours or a server restart. Saved progress survives restarts.

## Setup and provider behavior

Connect a Real-Debrid Premium account for the selected profile and configure TMDB or Trakt metadata. The CocoScrapers archive and worker ship with the app. No Kodi installation or separate scraper account is needed. In **Account manager > Service setup > CocoScrapers providers**, enable or disable the eight supported providers. Torrentio, BitSearch, EZTV, Knaben, and YTS are enabled by default. BitCQ, Nyaa, and 1337x are optional. EZTV handles episodes; YTS handles movies; Nyaa focuses on anime. Torrentio and YTS use the catalog's IMDb identifier. Changes apply to the next search. Your Real-Debrid library is always included, even when all public providers are disabled. The selected list persists in the encrypted server configuration. Provider outages, blocks, and missing IMDb identifiers can reduce results.

The app does not claim a source is cached before selection. Real-Debrid may download it first or reject it. Preparation does not guarantee a source will finish. If it remains at 0%, fails, or lacks the right episode, go back and choose another source. Premium, host, or traffic restrictions can also prevent preparation. Stopping or leaving the player never deletes account torrents or downloads.

The existing account library search is bounded to 100 downloads and 100 torrents. CocoScrapers results deduplicate by torrent hash, and at most 100 source choices are returned. A multi-file torrent lists at most 100 matching videos. Archives and split download links cannot play directly; choose a source containing an ordinary video file.

Use this integration for media you are authorized to access. The bundled licensed trailer remains available as an independent TV compatibility test.

## Code and HTTP boundaries

- `app/coco.py` checks the upstream archive and starts the metadata-only worker.
- `coco_worker/worker.py` runs upstream provider parsers in a separate process.
- `app/playback.py` owns scoped source choices, file selection, download state, resolution, codec information, and the range relay.
- `app/playback_routes.py` authenticates selection, session, stream, and progress requests.
- `web/library.js` owns source choices, pagination, preparation, file selection, and resume actions.
- `web/source-playback.js` owns automatic attempts, deadlines, cancellation, and playback confirmation.
- `web/app.js` owns the player and serialized progress writes.

`GET /api/catalog/{id}/sources?discover=true` searches account files and CocoScrapers. Omitting `discover` preserves the account-only lookup. Source results contain opaque selection IDs; the client cannot submit an arbitrary magnet or stream URL. `POST /api/playback` prepares one of those choices. The session endpoint reports `files`, `preparing`, or `ready`. `POST /api/playback/{id}/files` chooses a video. `GET` and `HEAD /api/playback/{id}/stream` relay video for the same authenticated profile session. `PUT /api/playback/{id}/progress` saves position through that bound session. All personal responses use `Cache-Control: no-store`.

Only single-process deployment is supported. Source choices and playback state are bounded in-memory data. Each viewing has a lock, concurrent repeated clicks reuse preparation, and profile disconnect invalidates its choices and streams.

## Verification

`tests/test_coco_worker.py` runs the actual bundled Torrentio and YTS parsers against controlled provider responses. `tests/test_playback.py` exercises search, movies, episodes, file packs, link indexing, concurrent clicks, profile/session isolation, range streaming, expired links, codec warnings, and saved progress through HTTP routes.

For browser verification, start `python tests/serve_playback_mock.py`, then run `node tests/browser-playback.cjs` with Playwright available. The fixture uses an isolated temporary database and the licensed local video. It never uses household accounts. It verifies real HTML video playback, remote seeking and pause, source-list restoration, resume after reload, restart, and 1080p/720p layouts.

For automatic recovery and pagination, start `python tests/serve_autoplay_mock.py`, then run `node tests/browser-autoplay.cjs`. It verifies a failed provider request, an invalid video, then actual advancing playback from the third source. It also covers search animation, cancellation during a delayed response, D-pad page navigation, persistent provider settings, and desktop/mobile layouts. `node --test tests/source-playback.test.cjs` checks the timeout and cancellation paths with a controlled clock.

Desktop playback does not establish audible audio or decoder support on the physical Vizio. Test a suitable source there before relying on long-form playback.
