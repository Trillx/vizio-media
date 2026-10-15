# Catalog and account setup

Version 0.2, implemented October 15, 2026.

Open Account manager on the server loopback address or through the SSH tunnel described in [deployment](deployment.md). The TV uses `http://YOUR_SERVER_IP:8765/`. Use your configured port if it differs.

## First use

Create an owner password of at least twelve characters. This password protects profile administration and service setup. It is separate from service passwords and profile PINs. The manager is available only through loopback, including its static HTML alias, and never asks for a service account password.

Under **Profiles and accounts**, rename Household or add profiles. A profile can have a four- to eight-digit PIN. Changing a name or PIN invalidates that profile's active sessions. Deleting a profile removes its local progress and sessions, requires its service accounts to be disconnected first, and cannot delete Household.

Choose the matching profile on the TV. Profile sessions last eight hours. A sole profile without a PIN is selected automatically on first load. With several profiles or a PIN, choose and unlock the profile before using personal account operations. **Lock current profile** clears that browser's profile session. PINs control shared-device access within this household installation.

## Catalog

In **Service setup**, enter the API Read Access Token from your [TMDB API settings](https://www.themoviedb.org/settings/api). The server validates it before saving. This enables movie and series search, trending metadata, posters, film details, seasons, and episode details. TMDB images are fetched through a fixed-host, bounded server cache.

If TMDB is not configured, a configured Trakt application supplies catalog search and details. This fallback currently omits artwork and season browsing. Without either service, Search shows three clearly labeled samples. Only the local Big Buck Bunny trailer is playable.

On the TV, open **Search**, type a title or year, or choose **Keyboard** for D-pad entry. Choose All titles, Movies, Series, or Trakt watchlist. The screen presents up to six entries at once and supports local result navigation plus API pages. Back returns through episode, season, title, and search screens. Select the plot and use Up/Down to read an overflowing title description.

Metadata results cache for six hours, up to 1,000 records. A cached search can be returned with a saved-results notice if the API becomes unavailable. The artwork cache retains up to 200 images with a three-megabyte response bound. No arbitrary image URL can be requested through the image route. Watchlists and account filename results are not shared through this metadata cache.

## Trakt

Register your application in the [Trakt application console](https://trakt.tv/oauth/applications). Save its client ID in Service setup. If the registration requires a client secret, enter it there. Use the exact registered redirect URI; the default is `urn:ietf:wg:oauth:2.0:oob`.

Choose a profile, select **Connect with device code** in the manager or **Connect Trakt** on the TV, and approve the displayed code at the official address. The page polls automatically. Codes expire, can be cancelled, and report denial or invalid/used states. Pending and rate-limited responses respect the server's next-poll time. The browser never receives the private device code, access token, or refresh token.

The connected profile can open its Trakt watchlist in Search. This version reads up to 100 watchlist entries. It does not add or remove watchlist items, synchronize watched state, or scrobble playback.

## Real-Debrid

For this private installation, the shortest setup is a personal token from [Real-Debrid's token page](https://real-debrid.com/apitoken), while signed in. In the PC manager, choose the profile, expand **Use a personal token on this private installation**, enter the token, and connect. The server checks the account before saving the encrypted token. This field is unavailable on the TV.

Device-code login is also implemented. Configure your own registered application client ID, then connect from either interface and approve the displayed code. The adapter uses Real-Debrid's user-bound credentials and documented nonstandard token grant. The shared open-source client ID is not a default for this private project.

Open a catalog title or episode and choose **Find in my Real-Debrid files**. The provider checks up to 100 account downloads and 100 torrents, compares filename words and year, and applies season/episode markers when requested. It deduplicates and ranks at most 40 matches. Results contain filenames, size, account status, and a filename-match score. A score is a text heuristic, not verification that the file is the correct title or playable.

The provider does not search public indexers, submit torrents, add downloads, unrestrict links, or expose private URLs. Playback resolution is the next independent media task. FenLight+ informs the separation of metadata, provider search, and resolution. Its code and Kodi dependencies are not embedded in this app.

## Disconnect and errors

Each profile can disconnect either service. The server attempts Trakt revocation or disabling the current Real-Debrid token, then removes local account credentials and flows. Review authorized applications on the service website to remove any remaining grant. Local disconnect succeeds even if remote revocation cannot be reached.

Access tokens refresh on demand. Per-account locks prevent two threads from refreshing the same token simultaneously, and rotated token pairs save atomically. A rejected refresh marks the account as requiring reconnection. A connection check reports an unreachable service as an error rather than claiming a successful check. Request timeouts and errors use sanitized messages that omit credentials and raw upstream bodies.

Disconnect accounts and cancel pending sign-ins before changing or removing the service's application setup. Blank setup fields keep current values. Removing setup and saving again clears optional values such as an old Trakt secret.

## Data and deployment

SQLite holds profiles, hashed passwords/PINs, hashed random session tokens, metadata caches, progress, diagnostics, and encrypted service credentials. Passwords and PINs use PBKDF2-SHA256 with 600,000 iterations and random salts. Fernet encrypts application settings, device flows, access tokens, refresh tokens, and user-bound Real-Debrid credentials.

Back up `data/vizio-media.sqlite3` and `data/vault.key` together. The encryption key inherits the local data directory's OS access controls, so protect that directory and its backups. The app refuses startup if encrypted records exist but the key is missing or mismatched. The key is never served to the browser. Data, keys, local media, and browser artifacts are excluded from Git.

Owner and profile cookies are HttpOnly and SameSite Strict. Owner sessions require both a loopback peer and a loopback Host. All writes require the application header, and cross-origin writes are rejected. Login attempts are limited to five per minute per peer and target. The app does not trust forwarding headers and accepts only the configured TV and the server computer. Request bodies, sessions, flow history, diagnostics, and caches are bounded.

Run one worker. In-memory locks and attempt limits are designed for that process. TV traffic is HTTP on the trusted home LAN. Device approval and API calls use the providers' HTTPS endpoints; service credentials are never sent to the TV. Public hosting, internet access, additional household networks, TLS termination, and a standalone user-identity service need a separate deployment design. There is no automatic owner-password recovery in this version.

## Verification

`tests/test_accounts_catalog.py` exercises the actual FastAPI routes with deterministic third-party HTTP fixtures. `tests/serve_mock.py` runs an isolated temporary browser fixture on loopback port 8767. It is imported only by the test command and is never part of `run.py`.

Tests cover owner access, profile isolation, PIN throttling, encrypted storage, missing/mismatched keys, pending/terminal/cancelled device flows, poll intervals, rate limits, concurrent token rotation, reconnect state, catalog filtering and caching, season data, bounded artwork, and URL-free account filename results. Browser checks cover regular and on-screen search, six-result pagination, profile PIN entry, service setup, approval/cancellation, local token entry, watchlists, source results, profile changes, logout, responsive manager layout, scaled TV layouts, and diagnostic privacy.

Live service approval requires the user's credentials and provider accounts. Mocked tests do not establish provider availability, codec compatibility, or playback of remote account files. Provider setup links above point to the official services. Media and logo terms are recorded in [attribution](../media/ATTRIBUTION.md).
