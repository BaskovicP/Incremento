# Sync through a hub on your network

A hub lets devices that share no cloud folder (a phone and a computer on one network) exchange Incremento data.
It is the same exchange as a shared folder, reached over the network. The engine on each device validates every
file it reads, so a hub is only a place to put files: it cannot make a device accept bad data.

## Using it

On a machine that is on while you study (any computer with Python 3.13 or later; nothing to install):

```
python scripts/sync_hub.py --keys hub-keys.json pair phone --host 192.168.1.20
python scripts/sync_hub.py --keys hub-keys.json pair desktop --host 192.168.1.20
python scripts/sync_hub.py --keys hub-keys.json serve ~/IncrementoHub
```

`pair` prints a pairing code for the device. Enter it in the device:

- Anki desktop: Incremento sync dialog, **Use a hub…**.
- Ankrimento: Incremento settings, **This device**, **Sync hub**.

Devices can be paired while the hub runs. `devices` lists them and `revoke` removes one, at once. Keep the keys file
out of the served folder and out of any cloud folder. The hub needs its port reachable from the devices (default
8765); the firewall may ask the first time.

A hub paired with a device replaces that device's sync folder. Pairing a device that already has data with an
empty hub makes it publish everything it has, with the documents.

## What protects the data

- **The channel**: TLS 1.2 with a pre-shared key, the pairing secret (`ECDHE-PSK-CHACHA20-POLY1305`). It is
  encrypted, forward secret, and both sides prove they hold the key, so a device knows it is talking to its own hub
  and the hub knows the device is paired. There is no certificate to create, trust or renew. It needs Python 3.13's
  `ssl`, which Anki 25 and Ankrimento have; an older Python says so.
- **One key per device**: 256 random bits each. A lost device is revoked by deleting its key.
- **The hub's own checks**: it refuses unsafe paths (`..`, absolute, backslash, empty parts), uploads over 512 MB or
  without a length, and uploads that stop part-way (nothing is written). It never shows or follows a symbolic link.
  A client that stalls or sends garbage cannot hold up the others.
- **The devices' checks**: unchanged from a cloud folder. Packs, snapshots and blobs are validated and hashed before
  anything is applied.

## Protocol (version 1)

All under `/v1`, the path in the `path` query parameter (`/`-separated, relative):

| Request | Answer |
|---|---|
| `GET /v1/list?path=<folder>` | JSON `[{name, dir, size, mtime}]`; a missing folder is `[]` |
| `GET /v1/stat?path=<rel>` | JSON `{name, dir, size, mtime}`, or 404 |
| `GET /v1/file?path=<rel>` | the bytes, or 404 |
| `PUT /v1/file?path=<rel>` | replaces the file atomically; `Content-Length` required; 204 |
| `DELETE /v1/file?path=<rel>` | 204, also when there is nothing to delete |

The pairing code is `ihub1-` + the URL-safe base64 of `[1, host, port, identity, key-hex]` + `-` + a 6-character
check. It contains the key, so treat it like a password.

## Not covered

- **A paired device can write anywhere in the folder**, as in a cloud folder. A device cannot make another accept bad
  data, but it can delete or overwrite another device's packs. Per-device write confinement would close this.
- **No discovery**: the pairing code names the hub's address. A hub whose address changes needs a new code.
- **No limit on simultaneous connections** beyond the operating system's.
- The key is stored in the profile's `sync/hub.json` (desktop) or the app's private preferences (Ankrimento), not in
  an OS keystore. Exports and support bundles skip the `sync` folder.
