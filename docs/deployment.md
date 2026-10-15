# Proxmox deployment

Run Docker Compose inside a Debian or Ubuntu QEMU VM with its own bridged LAN address. Proxmox recommends a QEMU VM for application containers such as Docker images in its [container documentation](https://pve.proxmox.com/wiki/Linux_Container). Install Docker Engine and the Compose plugin using the [official Debian](https://docs.docker.com/engine/install/debian/) or [Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).

Reserve the VM and TV addresses in DHCP or configure stable LAN addresses. The TV must be able to reach the VM directly; guest-Wi-Fi client isolation can prevent this. Allow the TV's address to reach the configured TCP port in the VM and Proxmox firewall as needed. Keep SSH access for administration. This guide does not change your firewall automatically.

## Configure and start

```sh
git clone https://github.com/Trillx/vizio-media.git
cd vizio-media
cp .env.example .env
nano .env
```

Set `VIZIO_BIND_IP` to the VM's LAN IPv4, `VIZIO_TV_IP` to the TV's LAN IPv4, and optionally change `VIZIO_PORT`. The example addresses belong to documentation-only ranges. Credentials belong in Account manager after startup.

```sh
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=50 app
```

Enable the VM's Start at boot option in Proxmox. Docker must start with the VM; the service's `restart: unless-stopped` policy then restarts an active installation after a reboot. The container runs as UID/GID 10001, with a read-only application filesystem and writable named data/media volumes.

Compose deliberately uses [Linux host networking](https://docs.docker.com/engine/network/drivers/host/). The app binds only the configured VM interface and `127.0.0.1`, sees the TV's original source address, and keeps owner routes on host loopback. There is no `ports:` mapping. Bridge-mode NAT, reverse proxies, tunnels that rewrite the TV's source address, and Windows Docker networking are not supported by this deployment recipe.

The health check uses `/api/health` on loopback. `media_ready: false` means the optional test trailer has not been installed; it does not mean the catalog service failed.

## Owner and services

From a computer with SSH access to the VM:

```sh
ssh -N -L 18765:127.0.0.1:8765 YOUR_SSH_USER@YOUR_VM_IP
```

If you changed the application port, replace the final `8765`. Leave local port `18765` free, keep SSH connected, and open **http://127.0.0.1:18765/manage** locally. This avoids a collision with a local development instance on port 8765. Owner cookies depend on the hostname, so avoid switching between `localhost` and `127.0.0.1` during setup.

Create an owner password of at least twelve characters. Add a TMDB API read token for the catalog, your Trakt application details, and your registered Real-Debrid client ID or a profile-specific personal token. Register your own applications and approve your own accounts. See [account setup](accounts-and-search.md).

The public code creates a fresh Household profile. No owner password, service credentials, linked accounts, watchlist, diagnostics, or playback history are supplied.

Install the optional licensed media:

```sh
sudo docker compose exec app python scripts/download_sample.py
```

Launch `http://YOUR_VM_IP:8765/` through the paired TV launcher. The VM's IP replaces the address of any prior computer-hosted instance. Keep the TV pairing credential only on the machine running that launcher.

## Updates

Back up data, then update application code and rebuild:

```sh
git pull --ff-only
sudo docker compose up -d --build
sudo docker compose ps
```

The named volumes retain profiles, credentials, caches, and local media. Do not use `docker compose down -v` when preserving an installation; that option removes its data volumes.

## Backup and migration

Stop writes and save the complete data volume to a private directory outside the repository:

```sh
mkdir -p "$HOME/vizio-media-backups"
chmod 700 "$HOME/vizio-media-backups"
umask 077
sudo docker compose stop app
sudo docker compose run --rm --no-deps -T --entrypoint tar app -C /app/data -czf - . > "$HOME/vizio-media-backups/data-$(date +%Y%m%d-%H%M%S).tgz"
sudo docker compose start app
```

The archive contains private data and the encryption key. Keep it private and retain both together. Proxmox VM backups can also preserve the installation if the VM disks holding Docker volumes are included.

For migration from a native installation, stop both instances and privately transfer the complete native `data/` directory, including `vizio-media.sqlite3` and its matching `vault.key`. Restore into the Docker data volume with UID/GID 10001 ownership. Never transfer private data through GitHub. A fresh setup through Account manager is also supported. Stop the source instance before migration to prevent conflicting account-token refreshes.

## Troubleshooting

- A bind error means `VIZIO_BIND_IP` is not assigned to the VM, or the configured port is occupied. Use a specific LAN IPv4 rather than `0.0.0.0`.
- HTTP 403 on the TV usually means `VIZIO_TV_IP` does not match its actual address. DHCP reservations help prevent drift.
- HTTP 403 for `/manage` over the LAN is expected. Use the SSH loopback tunnel.
- An SSH tunnel shows the app as a loopback client; native TV traffic still uses the VM's LAN URL.
- Missing or mismatched `vault.key` prevents startup when encrypted records exist. Restore the matching key and database backup.
- To test catalog and account behavior, use the temporary mock fixture described in [testing](testing.md). Keep the fixture off the live deployment.
