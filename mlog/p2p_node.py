from __future__ import annotations
import asyncio, json, os, mimetypes, hashlib
from typing import Dict, Any, Set, List

import websockets
from websockets.server import WebSocketServerProtocol

from .identity import load_public_key
from .util import b64, b64d, now_ts, sha256_file, get_local_ip
from .storage import Store

CHUNK_SIZE = 64 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_TOTAL_ATTACH_BYTES = 30 * 1024 * 1024

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AUDIO_MIMES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/aac", "audio/ogg"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime"}

def infer_mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"

def classify_and_limit(mime: str, size: int) -> None:
    if mime in ALLOWED_IMAGE_MIMES:
        if size > MAX_IMAGE_BYTES: raise ValueError("image too large")
        return
    if mime in ALLOWED_AUDIO_MIMES:
        if size > MAX_AUDIO_BYTES: raise ValueError("audio too large")
        return
    if mime in ALLOWED_VIDEO_MIMES:
        if size > MAX_VIDEO_BYTES: raise ValueError("video too large")
        return
    raise ValueError("unsupported mime")

def cid_from_hash(hexhash: str) -> str:
    return f"sha256:{hexhash}"

def canonical_event_bytes(event: Dict[str, Any]) -> bytes:
    t = event.get("type")
    base = {
        "type": t,
        "id": event["id"],
        "author_id": event["author_id"],
        "author_pub": event["author_pub"],
        "timestamp": event["timestamp"],
    }
    if t in ("POST", "REPLY"):
        base["text"] = event.get("text", "")
        base["media"] = event.get("media", [])
        if t == "REPLY":
            base["parent_id"] = event.get("parent_id")
    elif t == "REACTION":
        base["target_id"] = event.get("target_id")
        base["value"] = int(event.get("value", 0))
    return json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")

def verify_event(event: Dict[str, Any]) -> bool:
    try:
        pub = load_public_key(event["author_pub"])
        pub.verify(b64d(event["signature_b64"]), canonical_event_bytes(event))
        expected = hashlib.sha256(b64d(event["author_pub"])).hexdigest()[:16]
        return expected == event["author_id"]
    except Exception:
        return False

class P2PNode:
    def __init__(self, author_id: str, author_pub_b64: str, private_sign, store: Store, p2p_port: int):
        self.author_id = author_id
        self.author_pub_b64 = author_pub_b64
        self._sign = private_sign
        self.store = store
        self.p2p_port = p2p_port
        self.public_host = get_local_ip()

        self.connections: Set[websockets.WebSocketClientProtocol] = set()
        self.incoming_blobs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        self.peers: Set[str] = set(store.peers)

    def listen_url(self, host: str = "127.0.0.1") -> str:
        return f"ws://{host}:{self.p2p_port}"

    def has_blob(self, cid: str) -> bool:
        if not cid.startswith("sha256:"):
            return False
        hexh = cid.split(":", 1)[1]
        return os.path.exists(os.path.join(self.store.blob_dir, hexh))

    def blob_path(self, cid: str) -> str:
        hexh = cid.split(":", 1)[1]
        return os.path.join(self.store.blob_dir, hexh)

    def import_blob(self, filepath: str) -> Dict[str, Any]:
        mime = infer_mime(filepath)
        hexh, size = sha256_file(filepath)
        classify_and_limit(mime, size)
        cid = cid_from_hash(hexh)
        dest = os.path.join(self.store.blob_dir, hexh)
        if not os.path.exists(dest):
            with open(filepath, "rb") as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
        self.store.blob_index[cid] = {"mime": mime, "size": size, "name": os.path.basename(filepath)}
        self.store.save_blob_index()
        return {"cid": cid, "mime": mime, "size": size, "name": os.path.basename(filepath), "duration_sec": None}

    def _new_event_id(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def create_post(self, text: str, media: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "type": "POST",
            "author_id": self.author_id,
            "author_pub": self.author_pub_b64,
            "timestamp": now_ts(),
            "text": (text or "").strip(),
            "media": media or [],
        }
        payload["id"] = self._new_event_id(payload)
        payload["signature_b64"] = b64(self._sign(canonical_event_bytes(payload)))
        return payload

    def create_reply(self, parent_id: str, text: str, media: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "type": "REPLY",
            "author_id": self.author_id,
            "author_pub": self.author_pub_b64,
            "timestamp": now_ts(),
            "text": (text or "").strip(),
            "media": media or [],
            "parent_id": parent_id,
        }
        payload["id"] = self._new_event_id(payload)
        payload["signature_b64"] = b64(self._sign(canonical_event_bytes(payload)))
        return payload

    def create_reaction(self, target_id: str, value: int) -> Dict[str, Any]:
        v = int(value)
        if v not in (-1, 0, 1):
            v = 0
        payload = {
            "type": "REACTION",
            "author_id": self.author_id,
            "author_pub": self.author_pub_b64,
            "timestamp": now_ts(),
            "target_id": target_id,
            "value": v,
        }
        payload["id"] = self._new_event_id(payload)
        payload["signature_b64"] = b64(self._sign(canonical_event_bytes(payload)))
        return payload

    def persist_event(self, ev: Dict[str, Any]) -> None:
        self.store.events[ev["id"]] = ev
        self.store.save_events()
        aid = ev.get("author_id")
        if aid and aid != self.author_id:
            self.store.upsert_seed(aid, {"author_id": aid, "author_pub": ev.get("author_pub"), "display_name": None, "peers": []})

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send(json.dumps(msg))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.discard(ws)

    def _should_accept_event(self, ev: Dict[str, Any]) -> bool:
        aid = ev.get("author_id")
        return (aid == self.author_id) or (aid in self.store.following)

    async def handle_message(self, ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
        t = msg.get("type")

        if t == "HELLO":
            their_author_id = msg.get("author_id")
            their_pub = msg.get("author_pub")
            their_url = msg.get("listen_url")
            their_peers = msg.get("peers", [])
            if isinstance(their_url, str):
                self.peers.add(their_url); self.store.peers.add(their_url)
            for p in their_peers or []:
                if isinstance(p, str):
                    self.peers.add(p); self.store.peers.add(p)
            self.store.save_peers()
            if isinstance(their_author_id, str) and isinstance(their_pub, str):
                self.store.upsert_seed(their_author_id, {
                    "author_id": their_author_id,
                    "author_pub": their_pub,
                    "display_name": None,
                    "peers": [their_url] if isinstance(their_url, str) else [],
                })

            await ws.send(json.dumps({
                "type": "HELLO",
                "author_id": self.author_id,
                "author_pub": self.author_pub_b64,
                "listen_url": self.listen_url(),
                "peers": sorted(list(self.peers))[:50],
            }))

        elif t == "EVENT":
            ev = msg.get("event")
            if not isinstance(ev, dict) or "id" not in ev:
                return
            if ev["id"] in self.store.events:
                return
            if not verify_event(ev):
                return
            if not self._should_accept_event(ev):
                return
            self.persist_event(ev)
            await self.broadcast({"type": "EVENT", "event": ev})
            await self.request_missing_blobs(ev)

        elif t == "HAVE?":
            cids = msg.get("cids", [])
            have = [cid for cid in cids if isinstance(cid, str) and self.has_blob(cid)]
            if have:
                await ws.send(json.dumps({"type": "HAVE", "cids": have}))

        elif t == "HAVE":
            for cid in [c for c in msg.get("cids", []) if isinstance(c, str)]:
                if not self.has_blob(cid):
                    asyncio.create_task(self.fetch_blob(ws, cid))

        elif t == "GET_BLOB":
            cid = msg.get("cid")
            offset = int(msg.get("offset", 0))
            length = int(msg.get("length", CHUNK_SIZE))
            if not isinstance(cid, str) or not cid.startswith("sha256:"):
                return
            if length <= 0 or length > CHUNK_SIZE:
                return
            if not self.has_blob(cid):
                return
            path = self.blob_path(cid)
            size = os.path.getsize(path)
            if offset < 0 or offset >= size:
                return
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read(length)
            done = (offset + len(data)) >= size
            await ws.send(json.dumps({
                "type": "BLOB_CHUNK",
                "cid": cid,
                "offset": offset,
                "data_b64": b64(data),
                "done": done,
                "total_size": size,
            }))

        elif t == "BLOB_CHUNK":
            await self._handle_blob_chunk(msg)

    async def _handle_blob_chunk(self, msg: Dict[str, Any]) -> None:
        cid = msg.get("cid")
        offset = int(msg.get("offset", 0))
        data_b64 = msg.get("data_b64")
        done = bool(msg.get("done", False))
        total_size = int(msg.get("total_size", 0))
        if not isinstance(cid, str) or not cid.startswith("sha256:"):
            return
        if not isinstance(data_b64, str):
            return
        data = b64d(data_b64)

        async with self._lock:
            if cid not in self.incoming_blobs:
                tmp_path = os.path.join(self.store.blob_dir, f".incoming_{cid.split(':',1)[1]}")
                self.incoming_blobs[cid] = {"tmp_path": tmp_path, "received_upto": 0, "total_size": total_size}
            info = self.incoming_blobs[cid]
            tmp_path = info["tmp_path"]
            if offset != info["received_upto"]:
                return
            if info["total_size"] > MAX_TOTAL_ATTACH_BYTES:
                return
            mode = "ab" if os.path.exists(tmp_path) else "wb"
            with open(tmp_path, mode) as f:
                f.write(data)
            info["received_upto"] += len(data)

            if done:
                hexh = cid.split(":", 1)[1]
                h = hashlib.sha256()
                with open(tmp_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        h.update(chunk)
                if h.hexdigest() == hexh:
                    os.replace(tmp_path, self.blob_path(cid))
                else:
                    try: os.remove(tmp_path)
                    except OSError: pass
                self.incoming_blobs.pop(cid, None)

    async def request_missing_blobs(self, ev: Dict[str, Any]) -> None:
        media = ev.get("media") or []
        missing = []
        for m in media:
            if isinstance(m, dict) and "cid" in m and isinstance(m["cid"], str):
                cid = m["cid"]
                if cid not in self.store.blob_index:
                    self.store.blob_index[cid] = {
                        "mime": m.get("mime", "application/octet-stream"),
                        "size": int(m.get("size", 0)),
                        "name": m.get("name", cid),
                    }
                    self.store.save_blob_index()
                if not self.has_blob(cid):
                    missing.append(cid)
        if missing:
            await self.broadcast({"type": "HAVE?", "cids": missing})

    async def fetch_blob(self, ws: websockets.WebSocketClientProtocol, cid: str) -> None:
        offset = 0
        while not self.has_blob(cid):
            await ws.send(json.dumps({"type": "GET_BLOB", "cid": cid, "offset": offset, "length": CHUNK_SIZE}))
            await asyncio.sleep(0.05)
            info = self.incoming_blobs.get(cid)
            if info:
                offset = info["received_upto"]
            else:
                if self.has_blob(cid):
                    return
                await asyncio.sleep(0.2)

    async def server_handler(self, ws: WebSocketServerProtocol):
        self.connections.add(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if isinstance(msg, dict):
                        await self.handle_message(ws, msg)
                except json.JSONDecodeError:
                    continue
        finally:
            self.connections.discard(ws)

    async def run_server(self):
        async with websockets.serve(self.server_handler, "0.0.0.0", self.p2p_port):
            await asyncio.Future()

    async def connect_peer(self, url: str):
        if url.endswith(f":{self.p2p_port}"):
            return
        try:
            ws = await websockets.connect(url)
            self.connections.add(ws)
            await ws.send(json.dumps({
                "type": "HELLO",
                "author_id": self.author_id,
                "author_pub": self.author_pub_b64,
                "listen_url": self.listen_url(),
                "peers": sorted(list(self.peers))[:50],
            }))

            async def reader():
                try:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            if isinstance(msg, dict):
                                await self.handle_message(ws, msg)
                        except json.JSONDecodeError:
                            continue
                finally:
                    self.connections.discard(ws)

            asyncio.create_task(reader())
        except Exception:
            return

    async def peer_maintenance_loop(self):
        while True:
            targets = list(self.peers)
            for url in targets[:50]:
                if len(self.connections) >= 10:
                    break
                await self.connect_peer(url)
            await asyncio.sleep(3)
