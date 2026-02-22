from __future__ import annotations
import argparse, asyncio, os, webbrowser, threading
import uvicorn

from .identity import ensure_identity, load_private_key
from .storage import Store
from .p2p_node import P2PNode
from .web_ui import build_app
from .discovery import Discovery

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9001, help="P2P websocket port")
    ap.add_argument("--dir", type=str, default=None, help="data directory (default ./node_<port>)")
    ap.add_argument("--no-open", action="store_true", help="do not auto-open browser")
    ap.add_argument("--host", type=str, default="127.0.0.1", help="web ui bind host")
    return ap.parse_args()

async def run_async(node: P2PNode):
    asyncio.create_task(node.peer_maintenance_loop())
    await node.run_server()

def run_uvicorn(app, host: str, port: int):
    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def main():
    args = parse_args()
    base_dir = args.dir or os.path.join(os.getcwd(), f"node_{args.port}")
    os.makedirs(base_dir, exist_ok=True)

    ident = ensure_identity(os.path.join(base_dir, "identity.json"))
    priv = load_private_key(ident)
    store = Store(base_dir=base_dir)

    def signer(data: bytes) -> bytes:
        return priv.sign(data)

    node = P2PNode(
        author_id=ident["author_id"],
        author_pub_b64=ident["public_key_b64"],
        private_sign=signer,
        store=store,
        p2p_port=args.port,
    )

    # self-follow so your own content always shows in the filtered feed
    store.following.add(node.author_id)
    store.save_following()

    web_port = args.port + 1000

    lan_cache = {}

    discovery = Discovery(author_id=node.author_id, p2p_port=args.port, web_port=web_port)

    def on_peer(info):
        aid = info.get("author_id")
        ws = info.get("ws")
        if not aid or not ws or aid == node.author_id:
            return
        lan_cache[aid] = {"author_id": aid, "ws": ws}
        store.upsert_seed(aid, {"author_id": aid, "display_name": None, "author_pub": None, "peers": [ws]})
        store.peers.add(ws); store.save_peers()
        node.peers.add(ws)

    try:
        discovery.start_advertise()
        discovery.start_browse(on_peer)
    except Exception:
        pass

    app = build_app(store, node, lan_cache)

    t = threading.Thread(target=run_uvicorn, args=(app, args.host, web_port), daemon=True)
    t.start()

    url = f"http://{args.host}:{web_port}"
    if not args.no_open:
        try: webbrowser.open(url)
        except Exception: pass

    try:
        asyncio.run(run_async(node))
    finally:
        try: discovery.close()
        except Exception: pass

if __name__ == "__main__":
    main()
