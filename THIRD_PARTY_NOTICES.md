# Third-party source and licenses

The CocoScrapers integration includes code under GNU GPL version 3. Do not describe the entire distribution as MIT-only.

| Component | Location | License |
| --- | --- | --- |
| CocoScrapers 1.0.32, provider-name CocoJoe | `vendor/cocoscrapers-1.0.32.zip` | GNU GPL version 3, as declared in the upstream `addon.xml` |
| Vizio Media compatibility worker | `coco_worker/worker.py` | GPL-3.0-only |
| Vizio Media application | `app/`, `web/`, remaining original application code | See the root `LICENSE` in the public distribution |

The upstream source archive is included unchanged. It contains the complete Python source and its original author and third-party notices, including modules not loaded by this integration. Preserve those notices when redistributing it. The worker source is included beside the application. The GNU GPL version 3 text is included at `vendor/GPL-3.0.txt`.

Upstream repository: <https://github.com/CocoJoe2411/repository.cocoscrapers>

Pinned revision: `46166a791cc9a792ceb678ab0e1960a43af7525f`.

Archive SHA-256: `f33b11e3fcc8967aeca65548398212ba7c806298845eac2e57ba38cd35a6436e`.

The immutable source URL and checksum are also recorded in `vendor/cocoscrapers-provenance.json`. The server verifies that checksum before launching the worker. No upstream source has been modified.

The application communicates with the separate worker over JSON stdin and stdout. The worker loads the pinned upstream Python providers and provides replacements for Kodi settings, window properties, logging, cache calls, and bounded HTTPS transport. It receives catalog metadata only. Kodi itself is not required.

FenLight+ remains an architectural reference. Its source code is not included. Other Python dependencies retain their own package licenses. Media and artwork notices remain in `media/ATTRIBUTION.md`.
