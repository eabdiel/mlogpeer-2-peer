from __future__ import annotations
import os
from typing import Dict, Any, Set
from .util import load_json, atomic_write_json

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

class Store:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        ensure_dir(base_dir)

        self.events_path = os.path.join(base_dir, "events.json")
        self.following_path = os.path.join(base_dir, "following.json")
        self.peers_path = os.path.join(base_dir, "peers.json")
        self.seeds_path = os.path.join(base_dir, "seeds.json")

        self.blob_dir = os.path.join(base_dir, "blobs")
        ensure_dir(self.blob_dir)
        self.blob_index_path = os.path.join(base_dir, "blobs_index.json")

        self.events: Dict[str, Dict[str, Any]] = load_json(self.events_path, {})
        self.following: Set[str] = set(load_json(self.following_path, {"following": []}).get("following", []))
        self.peers: Set[str] = set(load_json(self.peers_path, {"peers": []}).get("peers", []))
        self.seeds: Dict[str, Dict[str, Any]] = load_json(self.seeds_path, {})
        self.blob_index: Dict[str, Dict[str, Any]] = load_json(self.blob_index_path, {})

    def save_events(self) -> None:
        atomic_write_json(self.events_path, self.events)

    def save_following(self) -> None:
        atomic_write_json(self.following_path, {"following": sorted(self.following)})

    def save_peers(self) -> None:
        atomic_write_json(self.peers_path, {"peers": sorted(self.peers)})

    def save_seeds(self) -> None:
        atomic_write_json(self.seeds_path, self.seeds)

    def save_blob_index(self) -> None:
        atomic_write_json(self.blob_index_path, self.blob_index)

    def upsert_seed(self, author_id: str, card: Dict[str, Any]) -> None:
        existing = self.seeds.get(author_id, {})
        merged = dict(existing)
        merged.update({k: v for k, v in card.items() if v is not None})
        peers = set(existing.get("peers", []))
        peers.update(card.get("peers", []) or [])
        merged["peers"] = sorted(peers)
        self.seeds[author_id] = merged
        self.save_seeds()
