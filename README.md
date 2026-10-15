# Vizio Media

A self-hosted web app for Vizio SmartCast TVs. Browse catalog recommendations and genres, search movies and series, connect profile-specific Trakt and Real-Debrid accounts, and test local video playback with a TV remote.

The home uses a charcoal and white layout with horizontal shelves, genre filters, related titles, Trakt My list, and Continue watching for actual saved playback. The app includes an owner account manager, household profiles with optional PINs, device-code authentication, and encrypted server-side credentials.

CocoScrapers source search and Real-Debrid playback are implemented. Choose a movie or episode, select **Play best available** to try recommended sources until a video starts, or **Find sources** to choose one manually. Source search shows a loading animation, pagination works with the D-pad, and eight CocoScrapers providers can be configured in Account manager under Service setup. Preparation progress, codec information and format warnings, byte-range seeking, expired-link refresh, and per-profile resume are included. See [playback setup and behavior](docs/playback.md). Trakt watched-state synchronization and scrobbling remain future work. The licensed Big Buck Bunny trailer remains available as a compatibility check.

## Run on Proxmox

Use a Debian or Ubuntu VM with Docker Engine and the Compose plugin. The [Proxmox deployment guide](docs/deployment.md) covers networking, owner setup over SSH, startup, updates, backups, and troubleshooting.

Inside the VM:

```sh
git clone https://github.com/Trillx/vizio-media.git
cd vizio-media
cp .env.example .env
nano .env
# Set VIZIO_BIND_IP to the VM's LAN IPv4 and VIZIO_TV_IP to the TV's IPv4.
sudo docker compose up -d --build
```

Open the app on the television using `http://YOUR_VM_IP:8765/`. The supplied `192.0.2.x` addresses are documentation examples and must be replaced.

Account manager is loopback-only. From your computer, create a tunnel to the VM:

```sh
ssh -N -L 18765:127.0.0.1:8765 YOUR_SSH_USER@YOUR_VM_IP
```

Keep that connection open, then visit **http://127.0.0.1:18765/manage** on your computer. Create an owner password, add your own service application settings, and connect each profile's accounts. The public repository includes no configured services or accounts.

Optionally install the checksum-verified trailer into the media volume:

```sh
sudo docker compose exec app python scripts/download_sample.py
```

## Run with Python

Python 3.12 or newer is required. On Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export VIZIO_TV_IP=YOUR_TV_IP
export VIZIO_BIND_IP=YOUR_SERVER_IP
python scripts/download_sample.py
python run.py
```

Windows can use `.venv\Scripts\python.exe` and PowerShell environment assignments such as `$env:VIZIO_TV_IP='YOUR_TV_IP'`. The optional PowerShell helpers are in `scripts/`. Python does not load `.env` automatically; Compose reads it, while native runs use exported environment variables.

| Variable | Purpose |
| --- | --- |
| `VIZIO_TV_IP` | Required TV IPv4 address |
| `VIZIO_BIND_IP` | Specific server interface; auto-detected toward the TV if omitted |
| `VIZIO_PORT` | HTTP port, default `8765` |
| `VIZIO_DATA_DIR` | SQLite, encryption key, and caches; default `data/` |
| `VIZIO_MEDIA_DIR` | Local trailer directory; default `media/` |

## Open on a TV

On a machine with a paired [vizaio](https://github.com/raman325/vizaio) installation:

```sh
vizaio app launch-config 17 4 "http://YOUR_SERVER_IP:8765/"
```

This launches the web app through Conjure. It does not install a permanent SmartCast tile. The server must remain available on the same home network, and each TV model's browser, remote, and codec behavior must be tested on the hardware.

Use the D-pad to select genres and scroll shelves; OK opens a title. Back restores the selected card. In the player, Left/Right choose a button, OK activates it, and Up focuses the timeline for ten-second seeking. Skip buttons and the timeline also support pointer clicks. Remote check and Test results remain in the header.

## Development

```sh
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/remote.test.cjs tests/service-link.test.cjs tests/source-playback.test.cjs tests/provider-settings.test.cjs tests/suggestions.test.cjs
```

Backend tests use temporary databases and fictional credentials. Optional Playwright tests use isolated fixtures on ports 8767 and 8768; see [testing](docs/testing.md) and [playback verification](docs/playback.md). CI runs the Python and JavaScript suites, builds the Linux image, and checks its loopback health and owner access.

See [account setup](docs/accounts-and-search.md), [architecture](docs/architecture.md), and [home design](docs/home-design.md).

## Data and license

Original application code is [MIT licensed](LICENSE). The CocoScrapers source archive and separate compatibility worker are distributed under GPL version 3. The complete upstream source, worker source, license text, and provenance ship with the application; see [third-party notices](THIRD_PARTY_NOTICES.md). Media, logos, and other dependencies retain their respective terms; see [attribution](media/ATTRIBUTION.md). Vizio Media is an independent project and is not affiliated with VIZIO, TMDB, Trakt, Real-Debrid, FenLight+, or CocoScrapers.

Credentials, pairing tokens, local addresses, account databases, encryption keys, logs, downloaded media, and local agent tooling are excluded from the public snapshot. Runtime data stays in the `app-data` Docker volume or your native `data/` directory. Preserve the database and matching `vault.key` together when backing up or moving an installation. See [security and publishing](SECURITY.md).
