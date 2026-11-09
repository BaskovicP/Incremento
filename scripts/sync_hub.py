"""A hub for Incremento sync over the local network (design note section 8).

The hub serves one folder to the devices you pair with it, so a phone and a computer on the same network can sync
without a cloud folder. It needs only Python 3.13 or later and no installation; run it on any machine that is on
while you study.

    python scripts/sync_hub.py --keys hub-keys.json pair phone --host 192.168.1.20
    python scripts/sync_hub.py --keys hub-keys.json serve ~/IncrementoHub

``pair`` prints a pairing code for the device (copy it into the device's sync settings). Devices can be paired
while the hub runs. Each device can change only its own device folder; who owns which is kept in a file beside
the keys file. The hub also answers paired devices that ask the local network where it is (UDP, port 8766;
``--no-discovery`` turns that off), so a device finds it again when its address changes. ``devices`` lists the paired devices and ``revoke`` removes one, which takes effect at once. Keep
the keys file out of the served folder and out of any cloud folder: whoever has a key can read and change the data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import sync_http  # noqa: E402

DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keys", type=Path, required=True, help="The hub's keys file (created by `pair`).")
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("pair", help="Pair a device and print its pairing code.")
    pair.add_argument("name")
    pair.add_argument("--host", required=True, help="This machine's address as the device will reach it.")
    pair.add_argument("--port", type=int, default=DEFAULT_PORT)
    commands.add_parser("devices", help="List the paired devices.")
    revoke = commands.add_parser("revoke", help="Remove a device.")
    revoke.add_argument("name")
    serve = commands.add_parser("serve", help="Serve a folder to the paired devices.")
    serve.add_argument("folder", type=Path)
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--discovery-port", type=int, default=sync_http.DISCOVERY_PORT,
                       help="UDP port on which paired devices can ask where the hub is.")
    serve.add_argument("--no-discovery", action="store_true", help="Do not answer devices that look for the hub.")
    options = parser.parse_args(argv)
    book = sync_http.KeyBook(options.keys)

    if options.command == "pair":
        try:
            key = book.add(options.name)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(f"Paired {options.name!r}. Enter this code in the device's sync settings:\n")
        print(sync_http.Pairing(options.host, options.port, options.name, key).code())
        return 0
    if options.command == "devices":
        for name in sorted(book.devices()):
            print(name)
        return 0
    if options.command == "revoke":
        if not book.revoke(options.name):
            print(f"No device called {options.name!r}.", file=sys.stderr)
            return 1
        print(f"Removed {options.name!r}.")
        return 0

    options.folder.mkdir(parents=True, exist_ok=True)
    try:
        sync_http.require_psk()
        owners = options.keys.with_name(options.keys.stem + "-owners.json")  # who owns which device folder
        hub = sync_http.Hub(options.folder, book.as_mapping(), host=options.host, port=options.port,
                            state_path=owners,
                            discovery_port=None if options.no_discovery else options.discovery_port)
        hub.start()
    except (sync_http.StoreError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Serving {options.folder} on {options.host}:{hub.port} for {len(book.devices())} device(s). Ctrl+C stops it.",
          flush=True)
    try:
        hub._thread.join()  # type: ignore[union-attr]
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
