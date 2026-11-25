"""What the current mouse cursor means for one account.

Holds a live reference to the account's hash dictionary, so re-registering a
cursor in the UI takes effect immediately without restarting the session.
"""

from ..config.models import CURSOR_KINDS
from ..winapi.cursor import AHASH_MAX_DIST, CursorProbe, hamming_hex, is_ahash, is_windows_cursor


# PLAN 0.36: the aiming ellipse changes with the ground under it. These four were seen on the game PC
# (observe "타락한 축복의 땅의 봄" + the registered one); any cursor this close to them or to a registered
# cast picture is "cast" - never "attack" (fc92fe38 was once registered as attack there).
CAST_DEFAULTS = ("fc92fe3800000000", "fc96fe3800000000", "fcbafe3800000000", "fcfefe3800000000")
CAST_MAX_DIST = 6


def _split(signature):
    return [t.strip() for t in str(signature or "").replace(";", ",").split(",") if t.strip()]


class CursorProfile:
    def __init__(self, hashes, max_dist=AHASH_MAX_DIST):
        self._hashes = hashes
        self.max_dist = max_dist
        self._warned = set()

    @property
    def hashes(self):
        return self._hashes

    def get(self, kind):
        return self._hashes.get(kind, "")

    def is_registered(self, kind):
        return bool(self.get(kind)) or kind == "cast"  # cast always has CAST_DEFAULTS

    @property
    def ready(self):
        """The attack cursor is the only one the bot cannot work without (and it must be unique)."""
        return self.is_registered("attack") and "attack" not in self.duplicate_kinds()

    def duplicates(self):
        """{token: [kinds]} for every token registered under 2+ kinds (PLAN 0.11)."""
        owners = {}
        for kind in CURSOR_KINDS:
            for token in self._token_list(kind):
                owners.setdefault(token, [])
                if kind not in owners[token]:
                    owners[token].append(kind)
        return {token: kinds for token, kinds in owners.items() if len(kinds) > 1}

    def near_duplicates(self, max_dist=2):
        """PLAN 0.35: [(kind_a, kind_b, dist)] for kinds whose aHashes are nearly the same picture.

        The game PC had attack fc92fe3800000000 and cast fcfefe3800000000 - 4 bits apart. They are told apart
        exactly here, but a picture that close usually means one of them was captured on the wrong frame, so
        the Cursor tab says so and the user can delete it. PLAN 0.36: only <= 2 bits - corpse f0f0f038 and npc
        f0f06020 are 4 apart and both right; attack/cast no longer need it (cast wins, see classify)."""
        pairs = []
        for i, a in enumerate(CURSOR_KINDS):
            for b in CURSOR_KINDS[i + 1:]:
                dist = min((hamming_hex(x, y) for x in self._token_list(a) if is_ahash(x)
                            for y in self._token_list(b) if is_ahash(y)), default=64)
                if self.max_dist < dist <= max_dist:
                    pairs.append((a, b, dist))
        return pairs

    def duplicate_kinds(self):
        return {kind for kinds in self.duplicates().values() for kind in kinds}

    def clashes_with(self, kind, signature):
        """Other VALID kinds that already hold one of the tokens in ``signature``.

        Kinds that are themselves duplicated are ignored (PLAN 0.13): they are wrong anyway."""
        tokens = _split(signature)
        broken = self.duplicate_kinds()
        return [other for other in CURSOR_KINDS
                if other != kind and other not in broken and any(t in self._token_list(other) for t in tokens)]

    def drop_duplicates(self):
        """Clear every kind that shares a token with another kind. Returns the cleared kinds."""
        broken = sorted(self.duplicate_kinds(), key=CURSOR_KINDS.index)
        for kind in broken:
            self._hashes[kind] = ""
        return broken

    def pictures(self, kind):
        """[signature] of each picture of a kind: an aHash with the MD5s right after it (PLAN 0.17)."""
        groups = []
        for token in self._token_list(kind):
            if is_ahash(token) or not groups:
                groups.append([token])
            else:
                groups[-1].append(token)
        return [",".join(g) for g in groups]

    def remove(self, kind, signature):
        """Drop exactly this picture (its aHash + paired MD5) from ``kind``; other pictures stay."""
        tokens = set(_split(signature))
        before = self.pictures(kind)
        kept = [p for p in before if not tokens & set(_split(p))]
        self._hashes[kind] = ",".join(kept)
        return len(kept) != len(before)

    def assign(self, kind, signature):
        """Cursor collection: move these tokens to ``kind`` (added to what it has), or to no kind (None).

        Adding (not replacing) lets several pictures of one kind (e.g. an animated cross) all count.
        Only the given tokens (and the MD5 paired with a dropped aHash) move; other pictures never change."""
        tokens = _split(signature)
        if kind in CURSOR_KINDS and is_windows_cursor(signature):
            return False  # PLAN 0.17: Windows' own arrow is never a game cursor
        for other in CURSOR_KINDS:
            kept, drop_md5 = [], False
            for token in self._token_list(other):
                # Captures store "aHash,MD5" pairs: dropping an aHash drops the MD5 right after it too
                # (old recordings only know the aHash).
                if token in tokens or (drop_md5 and not is_ahash(token)):
                    drop_md5 = is_ahash(token)
                    continue
                drop_md5 = False
                kept.append(token)
            if other == kind:
                kept += [t for t in tokens if t not in kept]
            self._hashes[other] = ",".join(kept)
        return kind in CURSOR_KINDS

    def kind_of(self, token):
        """The kind that holds this exact token, or None."""
        for kind in CURSOR_KINDS:
            if token in self._token_list(kind):
                return kind
        return None

    def _token_list(self, kind):
        return _split(self.get(kind))

    def _live_ids(self, cursor_hash, md5=None):
        """md5=None: the MD5 of the live read (CursorProbe); offline callers pass the recorded one or ""."""
        ids = []
        if cursor_hash:
            ids.append(cursor_hash)
        legacy = getattr(CursorProbe, "last_legacy", None) if md5 is None else md5
        if legacy and legacy not in ids:
            ids.append(legacy)
        return ids

    def classify(self, cursor_hash, md5=None):
        """One winner or "unknown". Exact MD5, then exact aHash, then the single nearest aHash
        within max_dist. A token registered under 2+ kinds, or a tie, is "unknown"."""
        live = self._live_ids(cursor_hash, md5)
        if not live:
            return "unknown"
        if self._near_cast(live):
            return "cast"
        tokens = {kind: self._token_list(kind) for kind in CURSOR_KINDS}
        for ident in sorted(live, key=is_ahash):  # MD5 before aHash
            kinds = [kind for kind in CURSOR_KINDS if ident in tokens[kind]]
            if len(kinds) == 1:
                return kinds[0]
            if kinds:
                self._warn_once(ident, kinds)
                return "unknown"
        live_prints = [c for c in live if is_ahash(c)]
        best = {
            kind: min((hamming_hex(t, c) for t in tokens[kind] if is_ahash(t) for c in live_prints), default=64)
            for kind in CURSOR_KINDS
        }
        nearest = min(best.values())
        winners = [kind for kind, dist in best.items() if dist == nearest]
        if nearest > self.max_dist or len(winners) != 1:
            return "unknown"
        return winners[0]

    def _near_cast(self, live):
        prints = [t for t in (*CAST_DEFAULTS, *self._token_list("cast")) if is_ahash(t)]
        return any(hamming_hex(t, c) <= CAST_MAX_DIST for t in prints for c in live if is_ahash(c))

    def _warn_once(self, ident, kinds):
        if ident not in self._warned:
            self._warned.add(ident)
            print(f"[CURSOR] WARNING: one cursor is registered as {'/'.join(kinds)} -> treated as unknown; "
                  "register those cursors again")

    def matches(self, kind, cursor_hash):
        expected = self.is_registered(kind)
        if not expected or not self._live_ids(cursor_hash):
            return False
        return self.classify(cursor_hash) == kind

    def is_attack(self, cursor_hash):
        return self.matches("attack", cursor_hash)

    def is_corpse(self, cursor_hash):
        return self.matches("corpse", cursor_hash)

    def is_ground(self, cursor_hash):
        return self.matches("ground", cursor_hash)

    def is_npc(self, cursor_hash):
        return self.matches("npc", cursor_hash)

    def is_cast(self, cursor_hash):
        """PLAN 0.34: the aiming ellipse after a spell hotkey - the spell is armed, the click will fire it."""
        return self.matches("cast", cursor_hash)

    def register(self, kind, cursor_hash, add=False):
        """Replace the kind's cursor (``add``: keep the old pictures too — attack = sword AND arrow, 1.1c);
        refuses a cursor another kind already holds."""
        if kind not in CURSOR_KINDS or not cursor_hash or self.clashes_with(kind, cursor_hash):
            return False
        if is_windows_cursor(cursor_hash):
            return False
        if add:
            return self.assign(kind, cursor_hash)
        self._hashes[kind] = cursor_hash
        return True

    @staticmethod
    def read_live():
        return CursorProbe.current_hash()
