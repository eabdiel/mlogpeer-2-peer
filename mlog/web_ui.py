from __future__ import annotations
import os, re
from typing import Any, Dict, List
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
import io
import segno
from .storage import Store
from .p2p_node import P2PNode

INDEX_HTML = '<!doctype html>\n<html>\n<head>\n<meta charset="utf-8"/>\n<meta name="viewport" content="width=device-width,initial-scale=1"/>\n<title>Mlog</title>\n<style>\n  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f5f8fa}\n  header{position:sticky;top:0;background:#fff;border-bottom:1px solid #e6ecf0;padding:10px 14px;display:flex;gap:10px;align-items:center;z-index:5}\n  .wrap{display:grid;grid-template-columns:280px 1fr 360px;gap:12px;max-width:1200px;margin:0 auto;padding:12px}\n  .card{background:#fff;border:1px solid #e6ecf0;border-radius:12px;padding:12px}\n  .menu button{width:100%;text-align:left;padding:10px;border:0;border-radius:10px;background:transparent;cursor:pointer}\n  .menu button:hover{background:#f0f6ff}\n  .title{font-weight:700}\n  .small{color:#536471;font-size:12px}\n  .btn{border:1px solid #1d9bf0;background:#1d9bf0;color:#fff;padding:8px 10px;border-radius:10px;cursor:pointer}\n  .btn2{border:1px solid #e6ecf0;background:#fff;padding:8px 10px;border-radius:10px;cursor:pointer}\n  textarea{width:100%;min-height:70px;border:1px solid #e6ecf0;border-radius:10px;padding:8px;font-size:14px}\n  input[type=text]{width:100%;border:1px solid #e6ecf0;border-radius:10px;padding:8px;font-size:14px}\n  .tweet{border-top:1px solid #e6ecf0;padding:12px 0}\n  .tweet:first-child{border-top:0}\n  .actions{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}\n  .pill{background:#f0f6ff;border:1px solid #d8e6ff;padding:3px 8px;border-radius:999px;font-size:12px}\n  .link{color:#1d9bf0;cursor:pointer;text-decoration:none}\n  .media img{max-width:100%;border-radius:12px;margin-top:8px}\n  .replybox{margin-top:8px;border-left:3px solid #e6ecf0;padding-left:10px}\n  .row{display:flex;gap:8px}\n</style>\n</head>\n<body>\n<header>\n  <div class="title">Mlog</div>\n  <div class="small" id="me"></div>\n  <div style="margin-left:auto" class="row">\n    <button class="btn2" onclick="refreshAll()">Refresh</button>\n  </div>\n</header>\n\n<div class="wrap">\n  <div class="card menu">\n    <button onclick="show(\'home\')">Home</button>\n    <button onclick="show(\'profile\')">Profile</button>\n    <button onclick="show(\'tracking\')">Tracking</button>\n    <button onclick="show(\'peers\')">Peers</button>\n    <div style="margin-top:10px" class="small">Connect Link</div>\n    <div class="small" id="connectLink" style="word-break:break-all"></div>\n    <button class="btn2" style="margin-top:8px" onclick="copyConnect()">Copy</button>\n  </div>\n\n  <div class="card" id="main"></div>\n\n  <div class="card">\n    <div class="title">LAN Discovery</div>\n    <div class="small">Nearby nodes appear automatically (mDNS).</div>\n    <div id="lan" style="margin-top:10px"></div>\n  </div>\n</div>\n\n<script>\nlet STATE=null;\nlet VIEW=\'home\';\nlet LAN={};\n\nfunction esc(s){return (s||\'\').replaceAll(\'&\',\'&amp;\').replaceAll(\'<\',\'&lt;\').replaceAll(\'>\',\'&gt;\');}\n\nasync function api(path, opts){\n  const r = await fetch(path, opts||{});\n  if(!r.ok){ throw new Error(await r.text()); }\n  return await r.json();\n}\n\nfunction show(v){ VIEW=v; render(); }\nfunction toggleQR(){
  const box=document.getElementById('qrBox');
  const img=document.getElementById('qrImg');
  if(box.style.display==='none'){
    box.style.display='block';
    img.src='/api/qr?ts='+Date.now();
  }else{
    box.style.display='none';
  }
}

function copyConnect(){\n  const t = document.getElementById(\'connectLink\').innerText;\n  navigator.clipboard.writeText(t);\n}\n\nasync function refreshAll(){\n  await loadState();\n  await render();\n}\n\nasync function loadState(){\n  STATE = await api(\'/api/state\');\n  document.getElementById(\'me\').innerText = `me: ${STATE.author_id} | p2p: ${STATE.listen_url}`;\n  document.getElementById(\'connectLink\').innerText = STATE.connect_link;\n  LAN = await api(\'/api/lan\');\n  renderLan();\n}\n\nfunction seedCardHtml(aid, card){\n  const peers = (card.peers||[]).map(p=>`<div class="small">${esc(p)}</div>`).join(\'\');\n  const followed = (STATE.following||[]).includes(aid);\n  return `\n    <div class="tweet">\n      <div><b>${esc(card.display_name||(\'seed-\'+aid))}</b> <span class="small">${aid}</span></div>\n      ${peers}\n      <div class="actions">\n        ${followed?`<button class="btn2" onclick="unfollow(\'${aid}\')">Unfollow</button>`:`<button class="btn2" onclick="follow(\'${aid}\')">Follow</button>`}\n        ${(card.peers||[]).length?`<button class="btn2" onclick="addPeer(\'${esc(card.peers[0])}\')">Connect</button>`:\'\'}\n      </div>\n    </div>\n  `;\n}\n\nconst SEED_NAME_DRAFT={};
function setSeedName(aid,val){ SEED_NAME_DRAFT[aid]=val; }
async function saveSeedName(aid){
  const name=(SEED_NAME_DRAFT[aid]||'').trim();
  await api('/api/seed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({author_id:aid, display_name:name})});
  await refreshAll();
}

async function follow(aid){ await api(\'/api/follow\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({author_id:aid})}); await refreshAll(); }\nasync function unfollow(aid){ await api(\'/api/unfollow\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({author_id:aid})}); await refreshAll(); }\n\nasync function addPeer(url){\n  await api(\'/api/peer\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({url})});\n  await refreshAll();\n}\n\nasync function addSeed(){\n  const link = document.getElementById(\'seedLink\').value.trim();\n  if(!link) return;\n  await api(\'/api/seed\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({connect_link:link})});\n  document.getElementById(\'seedLink\').value=\'\';\n  await refreshAll();\n}\n\nfunction mediaHtml(m){\n  if(!m || !m.cid) return \'\';\n  const cid = m.cid;\n  const mime = m.mime||\'\';\n  if(mime.startsWith(\'image/\')){\n    return `<div class="media"><img src="/media/${encodeURIComponent(cid)}"/></div>`;\n  }\n  if(mime.startsWith(\'audio/\')){\n    return `<div class="media"><audio controls src="/media/${encodeURIComponent(cid)}" style="width:100%;margin-top:8px"></audio></div>`;\n  }\n  if(mime.startsWith(\'video/\')){\n    return `<div class="media"><video controls src="/media/${encodeURIComponent(cid)}" style="width:100%;margin-top:8px;border-radius:12px"></video></div>`;\n  }\n  return `<div class="small">Attachment: ${esc(m.name||cid)}</div>`;\n}\n\nfunction tweetHtml(p){\n  const media = (p.media||[]).map(mediaHtml).join(\'\');\n  const isReply = p.type===\'REPLY\';\n  const replyMeta = isReply ? `<div class="small">replying to <span class="pill">${esc(p.parent_id)}</span></div>` : \'\';\n  const replyCount = (!isReply && (p.reply_count||0)>0) ? `<a class="link" onclick="openReplies(\'${p.id}\')">${p.reply_count} replies</a>` : `<a class="link" onclick="openReplies(\'${p.id}\')">reply</a>`;\n  return `\n    <div class="tweet" id="t_${p.id}">\n      <div class="small">${p.author_id} · ${new Date(p.timestamp*1000).toLocaleString()}</div>\n      ${replyMeta}\n      <div>${esc(p.text||\'\')}</div>\n      ${media}\n      <div class="actions">\n        <button class="btn2" onclick="react(\'${p.id}\',1)">👍 ${p.likes||0}</button>\n        <button class="btn2" onclick="react(\'${p.id}\',-1)">👎 ${p.dislikes||0}</button>\n        <button class="btn2" onclick="react(\'${p.id}\',0)">↩︎</button>\n        <span class="small">${replyCount}</span>\n      </div>\n      <div class="replybox" id="r_${p.id}" style="display:none"></div>\n    </div>\n  `;\n}\n\nasync function react(target_id, value){\n  await api(\'/api/react\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({target_id, value})});\n  await renderHome();\n}\n\nasync function openReplies(postId){\n  const box = document.getElementById(\'r_\'+postId);\n  if(box.style.display===\'none\'){\n    box.style.display=\'block\';\n    box.innerHTML = `<div class="small">Loading…</div>`;\n    const reps = await api(\'/api/replies?parent_id=\'+encodeURIComponent(postId));\n    const repHtml = reps.map(tweetHtml).join(\'\');\n    box.innerHTML = `\n      <div class="row">\n        <input type="text" id="reply_text_${postId}" placeholder="Reply…"/>\n        <button class="btn2" onclick="sendReply(\'${postId}\')">Reply</button>\n      </div>\n      <div class="small" style="margin-top:6px">Replies you see are from people you follow (alpha spam resistance).</div>\n      ${repHtml || `<div class="small" style="margin-top:8px">No replies yet.</div>`}\n    `;\n  } else {\n    box.style.display=\'none\';\n  }\n}\n\nasync function sendReply(parentId){\n  const txt = document.getElementById(\'reply_text_\'+parentId).value.trim();\n  const fd = new FormData();\n  fd.append(\'parent_id\', parentId);\n  fd.append(\'text\', txt);\n  await fetch(\'/api/reply\',{method:\'POST\',body:fd});\n  await renderHome();\n  await openReplies(parentId);\n}\n\nasync function renderHome(){\n  const main = document.getElementById(\'main\');\n  main.innerHTML = `\n    <div class="title">Home</div>\n    <div class="small">Public feed = what your node knows from peers + followed authors.</div>\n    <div style="margin-top:10px" class="row">\n      <input type="text" id="post_text" placeholder="What\'s happening?"/>\n      <button class="btn" onclick="sendPost()">Post</button>\n    </div>\n    <div class="small" style="margin-top:8px">Attach media (optional):</div>\n    <input type="file" id="post_files" multiple/>\n    <div id="feed" style="margin-top:10px"></div>\n  `;\n\n  const posts = await api(\'/api/timeline\');\n  document.getElementById(\'feed\').innerHTML = posts.map(tweetHtml).join(\'\') || `<div class="small">No posts yet.</div>`;\n}\n\nasync function sendPost(){\n  const txt = document.getElementById(\'post_text\').value.trim();\n  const files = document.getElementById(\'post_files\').files;\n  const fd = new FormData();\n  fd.append(\'text\', txt);\n  for(const f of files){ fd.append(\'files\', f, f.name); }\n  await fetch(\'/api/post\',{method:\'POST\',body:fd});\n  document.getElementById(\'post_text\').value=\'\';\n  document.getElementById(\'post_files\').value=\'\';\n  await renderHome();\n}\n\nasync function renderProfile(){\n  const main = document.getElementById(\'main\');\n  main.innerHTML = `\n    <div class="title">Profile</div>\n    <div class="small">Identity is local. (Display-name editing can be added next.)</div>\n    <div style="margin-top:12px"><span class="pill">author_id: ${STATE.author_id}</span></div>\n  `;\n}\n\nasync function renderTracking(){\n  const main = document.getElementById(\'main\');\n  const seeds = STATE.seeds || {};\n  const cards = Object.keys(seeds).sort().map(aid => seedCardHtml(aid, seeds[aid])).join(\'\');\n  main.innerHTML = `\n    <div class="title">Tracking</div>\n    <div class="small">Seed cards help you follow/connect to friends.</div>\n    <div style="margin-top:10px" class="row">\n      <input type="text" id="seedLink" placeholder="Paste connect link: mlog://host:port?aid=..."/>\n      <button class="btn2" onclick="addSeed()">Add</button>\n    </div>\n    <div style="margin-top:10px">${cards || `<div class="small">No seed cards yet.</div>`}</div>\n  `;\n}\n\nasync function renderPeers(){\n  const main = document.getElementById(\'main\');\n  const peers = (STATE.peers||[]).map(p=>`<div class="tweet"><div>${esc(p)}</div></div>`).join(\'\');\n  main.innerHTML = `\n    <div class="title">Peers</div>\n    <div class="small">Add a peer websocket URL to connect.</div>\n    <div style="margin-top:10px" class="row">\n      <input type="text" id="peerUrl" placeholder="ws://host:port"/>\n      <button class="btn2" onclick="addPeerFromInput()">Add</button>\n    </div>\n    <div style="margin-top:10px">${peers || `<div class="small">No peers yet.</div>`}</div>\n  `;\n}\n\nasync function addPeerFromInput(){\n  const url = document.getElementById(\'peerUrl\').value.trim();\n  if(!url) return;\n  await addPeer(url);\n  document.getElementById(\'peerUrl\').value=\'\';\n}\n\nfunction renderLan(){\n  const el = document.getElementById(\'lan\');\n  const items = Object.values(LAN||{}).slice(0,30).map(p=>{\n    if(!p || !p.author_id || p.author_id===STATE.author_id) return \'\';\n    return `\n      <div class="tweet">\n        <div><b>${esc(p.author_id)}</b></div>\n        <div class="small">${esc(p.ws||\'\')}</div>\n        <div class="actions">\n          <button class="btn2" onclick="api(\'/api/seed\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({author_id:\'${esc(p.author_id)}\',peer_url:\'${esc(p.ws||\'\')}\'})}).then(refreshAll)">Add Seed</button>\n          <button class="btn2" onclick="addPeer(\'${esc(p.ws||\'\')}\')">Connect</button>\n        </div>\n      </div>\n    `;\n  }).join(\'\');\n  el.innerHTML = items || `<div class="small" style="margin-top:10px">No nearby nodes yet.</div>`;\n}\n\nasync function render(){\n  if(!STATE) await loadState();\n  if(VIEW===\'home\') await renderHome();\n  if(VIEW===\'profile\') await renderProfile();\n  if(VIEW===\'tracking\') await renderTracking();\n  if(VIEW===\'peers\') await renderPeers();\n  renderLan();\n}\n\n(async function init(){\n  await loadState();\n  await render();\n})();\n</script>\n</body>\n</html>\n'

def build_app(store: Store, node: P2PNode, lan_cache: Dict[str, Dict[str, Any]]) -> FastAPI:
    app = FastAPI(title="Mlog")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return INDEX_HTML

    @app.get("/api/state")
    async def state():
        return {
            "author_id": node.author_id,
            "listen_url": node.listen_url(),
            "following": sorted(list(store.following)),
            "peers": sorted(list(store.peers)),
            "seeds": store.seeds,
            "connect_link": f"mlog://{node.public_host}:{node.p2p_port}?aid={node.author_id}",
        }

    @app.get("/api/lan")
    async def lan():
        return lan_cache

    @app.post("/api/peer")
    async def add_peer(payload: Dict[str, Any]):
        url = (payload.get("url") or "").strip()
        if not url.startswith("ws://") and not url.startswith("wss://"):
            return JSONResponse({"ok": False, "error": "peer url must start with ws:// or wss://"}, status_code=400)
        store.peers.add(url); store.save_peers()
        node.peers.add(url)
        return {"ok": True}

    @app.post("/api/follow")
    async def follow(payload: Dict[str, Any]):
        aid = (payload.get("author_id") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{16}", aid):
            return JSONResponse({"ok": False, "error": "author_id should be 16 hex chars"}, status_code=400)
        store.following.add(aid); store.save_following()
        return {"ok": True}

    @app.post("/api/unfollow")
    async def unfollow(payload: Dict[str, Any]):
        aid = (payload.get("author_id") or "").strip()
        store.following.discard(aid); store.save_following()
        return {"ok": True}

    @app.post("/api/seed")
    async def add_seed(payload: Dict[str, Any]):
        link = (payload.get("connect_link") or "").strip()
        author_id = (payload.get("author_id") or "").strip()
        peer_url = (payload.get("peer_url") or "").strip()
        display_name = (payload.get("display_name") or "").strip()

        if link:
            m = re.match(r"^mlog://([^/]+):(\d+)\?aid=([0-9a-f]{16})$", link)
            if not m:
                return JSONResponse({"ok": False, "error": "bad connect link"}, status_code=400)
            host = m.group(1); port = int(m.group(2)); author_id = m.group(3)
            peer_url = f"ws://{host}:{port}"

        if not re.fullmatch(r"[0-9a-f]{16}", author_id):
            return JSONResponse({"ok": False, "error": "author_id should be 16 hex chars"}, status_code=400)
        if peer_url and (not peer_url.startswith("ws://") and not peer_url.startswith("wss://")):
            return JSONResponse({"ok": False, "error": "peer_url must start with ws:// or wss://"}, status_code=400)

        store.upsert_seed(author_id, {
            "author_id": author_id,
            "display_name": payload.get("display_name"),
            "author_pub": payload.get("author_pub"),
            "peers": [peer_url] if peer_url else [],
        })
        if peer_url:
            store.peers.add(peer_url); store.save_peers()
            node.peers.add(peer_url)
        return {"ok": True}

    def allowed(ev: Dict[str, Any]) -> bool:
        aid = ev.get("author_id")
        return (aid == node.author_id) or (aid in store.following)

    def compute_reactions(events: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        latest: Dict[tuple[str,str], Dict[str, Any]] = {}
        for ev in events.values():
            if ev.get("type") != "REACTION": 
                continue
            if not allowed(ev):
                continue
            reactor = ev.get("author_id"); target = ev.get("target_id")
            if not reactor or not target:
                continue
            key = (reactor, target)
            prev = latest.get(key)
            if prev is None or int(ev.get("timestamp",0)) >= int(prev.get("timestamp",0)):
                latest[key] = ev
        out: Dict[str, Dict[str, int]] = {}
        for (_reactor, target), ev in latest.items():
            v = int(ev.get("value", 0))
            out.setdefault(target, {"likes":0,"dislikes":0})
            if v == 1: out[target]["likes"] += 1
            elif v == -1: out[target]["dislikes"] += 1
        return out

    def strip(ev: Dict[str, Any]) -> Dict[str, Any]:
        t = ev.get("type")
        base = {
            "type": t,
            "id": ev.get("id"),
            "author_id": ev.get("author_id"),
            "timestamp": int(ev.get("timestamp", 0)),
            "text": ev.get("text", ""),
            "media": ev.get("media", []),
        }
        if t == "REPLY":
            base["parent_id"] = ev.get("parent_id")
        return base

    @app.get("/api/timeline")
    async def timeline():
        posts = [ev for ev in store.events.values() if ev.get("type") == "POST" and allowed(ev)]
        posts.sort(key=lambda x: int(x.get("timestamp", 0)), reverse=True)

        reactions = compute_reactions(store.events)

        reply_count: Dict[str, int] = {}
        for ev in store.events.values():
            if ev.get("type") != "REPLY" or not allowed(ev):
                continue
            parent = ev.get("parent_id")
            if parent:
                reply_count[parent] = reply_count.get(parent, 0) + 1

        out = []
        for p in posts[:200]:
            pid = p["id"]
            out.append({
                **strip(p),
                "likes": reactions.get(pid, {}).get("likes", 0),
                "dislikes": reactions.get(pid, {}).get("dislikes", 0),
                "reply_count": reply_count.get(pid, 0),
            })
        return out

    @app.get("/api/replies")
    async def replies(parent_id: str):
        reps = [ev for ev in store.events.values() if ev.get("type") == "REPLY" and ev.get("parent_id") == parent_id and allowed(ev)]
        reps.sort(key=lambda x: int(x.get("timestamp", 0)))
        reactions = compute_reactions(store.events)
        out = []
        for r in reps[:200]:
            rid = r["id"]
            out.append({
                **strip(r),
                "likes": reactions.get(rid, {}).get("likes", 0),
                "dislikes": reactions.get(rid, {}).get("dislikes", 0),
            })
        return out

    @app.post("/api/post")
    async def api_post(text: str = Form(""), files: List[UploadFile] = File(default=[])):
        media = []
        total = 0
        for uf in files or []:
            data = await uf.read()
            total += len(data)
            if total > 30 * 1024 * 1024:
                return JSONResponse({"ok": False, "error": "attachments too large"}, status_code=400)
            tmp_path = os.path.join(store.base_dir, f".upload_{uf.filename}")
            with open(tmp_path, "wb") as f:
                f.write(data)
            try:
                m = node.import_blob(tmp_path)
                media.append(m)
            finally:
                try: os.remove(tmp_path)
                except OSError: pass

        ev = node.create_post(text, media)
        node.persist_event(ev)
        await node.broadcast({"type": "EVENT", "event": ev})
        cids = [m["cid"] for m in media if isinstance(m, dict) and "cid" in m]
        if cids:
            await node.broadcast({"type": "HAVE", "cids": cids})
        return {"ok": True, "id": ev["id"]}

    @app.post("/api/reply")
    async def api_reply(parent_id: str = Form(...), text: str = Form(""), files: List[UploadFile] = File(default=[])):
        media = []
        total = 0
        for uf in files or []:
            data = await uf.read()
            total += len(data)
            if total > 30 * 1024 * 1024:
                return JSONResponse({"ok": False, "error": "attachments too large"}, status_code=400)
            tmp_path = os.path.join(store.base_dir, f".upload_{uf.filename}")
            with open(tmp_path, "wb") as f:
                f.write(data)
            try:
                m = node.import_blob(tmp_path)
                media.append(m)
            finally:
                try: os.remove(tmp_path)
                except OSError: pass

        ev = node.create_reply(parent_id, text, media)
        node.persist_event(ev)
        await node.broadcast({"type": "EVENT", "event": ev})
        cids = [m["cid"] for m in media if isinstance(m, dict) and "cid" in m]
        if cids:
            await node.broadcast({"type": "HAVE", "cids": cids})
        return {"ok": True, "id": ev["id"]}

    @app.post("/api/react")
    async def api_react(payload: Dict[str, Any]):
        target_id = (payload.get("target_id") or "").strip()
        value = int(payload.get("value", 0))
        ev = node.create_reaction(target_id, value)
        node.persist_event(ev)
        await node.broadcast({"type": "EVENT", "event": ev})
        return {"ok": True, "id": ev["id"]}

    @app.get("/media/{cid_path:path}")
    async def media(cid_path: str):
        cid = cid_path if cid_path.startswith("sha256:") else "sha256:" + cid_path
        if not node.has_blob(cid):
            return Response(status_code=404)
        path = node.blob_path(cid)
        meta = store.blob_index.get(cid, {})
        mime = meta.get("mime") or "application/octet-stream"
        return FileResponse(path, media_type=mime)

    return app
