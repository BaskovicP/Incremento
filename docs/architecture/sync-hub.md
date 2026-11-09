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
- **Each device changes only its own folder**: the first device to write below `devices/<id>/` owns it, and another
  paired device cannot write or delete there (everyone can read everything, and blobs and `library.json` are shared).
  A device that is revoked and paired again should keep its name, or it cannot write to the folder it owned. The owners
  are kept in a file beside the keys file; if it is lost, the next writers claim the folders again.
- **The hub's own checks**: it refuses unsafe paths (`..`, absolute, backslash, empty parts), uploads over 512 MB or
  without a length, and uploads that stop part-way (nothing is written). It never shows or follows a symbolic link.
  A client that stalls or sends garbage cannot hold up the others.
- **The devices' checks**: unchanged from a cloud folder. Packs, snapshots and blobs are validated and hashed before
  anything is applied.

- **Discovery**: a device that cannot reach its hub broadcasts `IHUB1 <device> <nonce>`; a hub answers only a device it
  has a key for, with its port and an HMAC of the nonce and port under that key. The question reveals nothing, and an
  answer without a valid proof is ignored. `serve --no-discovery` turns the answers off.

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

- **A paired device is still trusted not to fill the disk or delete shared blobs** (a blob nobody names is cleared
  by any device's cleanup, by design). Revoke a device that misbehaves.
- **Finding the hub again is best effort**: the pairing code names the hub's address; if it cannot be reached there, a
  device asks the local network (UDP broadcast, port 8766) and a hub holding its key answers with a proof only that key
  can make, so a device never follows an impostor. It works on one network segment; across routers or Wi-Fi client
  isolation, pair again with the new address.
- **At most 64 simultaneous connections** (`max_connections`); more are turned away and retry on the next sync.
- The key is stored in the profile's `sync/hub.json` (desktop) or the app's private preferences (Ankrimento), not in
  an OS keystore. Exports and support bundles skip the `sync` folder.
