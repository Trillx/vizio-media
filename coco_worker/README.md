# CocoScrapers compatibility worker

This executable adapter is licensed GPL-3.0-only and loads the unchanged CocoScrapers 1.0.32 source archive. See `../THIRD_PARTY_NOTICES.md` and `../vendor/GPL-3.0.txt`.

`worker.py` reads one JSON object from stdin and writes one JSON object to stdout. Input contains `title`, optional `season` and `episode`, and an optional subset of supported `providers`. No accounts, service tokens, household database paths, or settings are passed to this process.

The provider catalog is `providers.json`. Supported modules are `torrentio`, `bitsearch`, `eztv`, `knaben`, `ytsmx`, `bitcq`, `nyaa`, and `1337x`. The first five are enabled by default. EZTV runs only for episodes; YTS runs only for movies. Torrentio and YTS need an IMDb identifier. Owners can change the selection in Account manager, Service setup, CocoScrapers providers. Disabling all providers preserves account-library search. The worker uses the actual upstream provider parsers and title filters. Results contain normalized names, hashes, sizes, and provider statuses. API keys for other provider modules, pack-search methods, Kodi services and windows, Cloudflare challenge solvers, and CAPTCHA services are not enabled.

Providers run concurrently in daemon threads with an 18-second overall search budget. The parent process enforces a 23-second timeout. A maximum of two worker processes run concurrently. HTTPS transport verifies certificates, rejects private network destinations, checks redirects, and bounds response bodies. A blocked or unavailable provider produces a partial-search notice in the application. Results interleave providers before applying the 500-result bound, so a large response cannot exclude every later provider.

To support another bundled module, audit its imports and network behavior, add its entry to `providers.json`, and exercise its real parser with controlled responses. Runtime module names remain restricted to that catalog. The pinned Pirate Bay parser is excluded because its successful-response path references an uninitialized local logging variable. HTTP-only providers, challenge solvers, and modules needing unsupported credentials or dependencies are also excluded.

Run the worker with the same Python environment as the server. It uses the application's existing `httpx` dependency. The archive must remain at `../vendor/cocoscrapers-1.0.32.zip`; it is imported directly and does not need extraction or installation into Kodi.
