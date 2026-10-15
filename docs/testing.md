# Testing

Python 3.12 or newer and the development requirements run the backend and ES5 syntax checks:

```sh
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/remote.test.cjs tests/service-link.test.cjs tests/source-playback.test.cjs
```

The Python suite creates temporary SQLite databases and mocks provider HTTP responses. It checks encryption, profile isolation, authentication state, catalog and home collections, stale metadata, scoped watchlists, byte ranges, and request guards. Playback checks cover source deduplication, the actual bundled CocoScrapers parser, file selection, concurrent clicks, episode matching, signed-link refresh, CDN MIME headers, codec warnings, stream isolation, and resume. Test credentials are fictional and must never be replaced with real accounts.

For optional browser checks, install Playwright and its Chromium browser in your development environment, then start the isolated fixture in a separate terminal:

```sh
python tests/serve_mock.py
```

Install the licensed sample media first if testing playback. The fixture binds only loopback port 8767, uses temporary data, and is never imported by the production entry point. Run the playback suite before the account suite on a fresh fixture:

```sh
VIZIO_TEST_URL=http://127.0.0.1:8767 VIZIO_BROWSER_CHANNEL=chromium node tests/browser.cjs
VIZIO_BROWSER_CHANNEL=chromium node tests/browser-accounts.cjs
```

The account suite includes `browser-home.cjs` after configuring mock services. It covers home genres, paging, horizontal D-pad scroll, Back focus, real saved sample progress, watchlists, delayed responses during profile switching, and retry. The complete account suite requires a fresh fixture database. Restart the fixture before repeating it.

These scripts default to installed Edge on Windows. Set `VIZIO_BROWSER_CHANNEL=chromium` for Playwright's bundled Chromium. Screenshots go to the ignored `artifacts/` directory. Browser suites are optional local checks; CI runs Python, Node unit tests, and a Docker build/startup smoke check.

For Real-Debrid playback, run `python tests/serve_playback_mock.py` and `node tests/browser-playback.cjs` in separate terminals. For automatic source recovery, source pagination, loading indicators, and provider settings, use a fresh `python tests/serve_autoplay_mock.py` process on port 8769 and run `node tests/browser-autoplay.cjs`. Both use the licensed sample media, controlled service responses, and temporary databases. See [playback verification](playback.md).

Desktop browser tests do not establish firmware-specific behavior. Test scrolling, focus, key codes, decoding, sound, and resume on each actual TV.
