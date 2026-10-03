# Mlog (Alpha)

Local-first peer-to-peer microblogging prototype with signed events, local media storage, and LAN peer discovery.

A project of **[ProgreTech LLC](https://progretech.com)**, owned and maintained by **Ed Rodriguez**. Third-party components and contributions retain their respective ownership and notices.

[Project website](https://progretech.com) · [Report an issue](https://github.com/eabdiel/mlogpeer-2-peer/issues) · [Contribute](CONTRIBUTING.md)

**Mlog** is a local-first, peer-to-peer micro‑publishing Proof‑of‑Concept for the **ProgreTech** portfolio.

- No central server
- Each user owns their data locally
- Your feed emerges from peers you connect to (and optionally follow)

ProgreTech: https://progretech.com

## What’s in this Alpha
- Signed append-only events: **POST**, **REPLY**, **REACTION** (like / dislike / remove)
- Replies are authored/stored by the **replier** (they reference `parent_id` but never modify the original post)
- Like/dislike counts are computed locally from the *latest* reaction per (reactor, target)
- Media attachments (images / audio / video) stored locally as content-addressed **sha256** blobs, fetched on-demand in chunks
- Simple built-in Web UI (no CLI for normal use)
- LAN discovery via mDNS (Zeroconf)
- Seed cards (follow/connect) + connect link + QR code

## Run (dev)
```bash
pip install -r requirements.txt
python -m mlog.main --port 9001
```

Open the UI at:
- http://127.0.0.1:10001  (web port = p2p port + 1000)

Run a second node on the same machine:
```bash
python -m mlog.main --port 9002
```

## Build a single-file executable (PyInstaller)
```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --clean --noconfirm --name Mlog --onefile -m mlog.main
```

## Notes (Alpha safety)
- Text is treated as plain text (no HTML rendering)
- Media is allowlisted by type and capped by size
- Content is accepted/displayed primarily from authors you choose to follow (spam reduction)

## License
MIT

## Collaboration

Reproducible bug reports, platform compatibility, installation documentation, and small regression fixes are useful ways to help. Read [CONTRIBUTING.md](CONTRIBUTING.md) for issue reports, proposed changes, and attribution requirements.

## License and reuse

The repository includes MIT terms in [LICENSE](LICENSE). Preserve applicable copyright and license notices. Consult the full license for modification, distribution, and any source-provision requirements.

## More from ProgreTech

Explore [CodeSeal](https://codeseal.progretech.com) for signed software provenance and project history.

Discover the wider portfolio at [progretech.com](https://progretech.com). These links identify related products; they do not imply a bundled integration or shared license.
