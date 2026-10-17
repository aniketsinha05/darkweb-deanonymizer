"""
Synthetic multi-alias forum data generator for darkweb-deanonymizer (SIH26151).

Everything here is fabricated: fake actors, fake aliases, fake wallets/keys, and
benign "marketplace-style" chatter. No real people, no real illicit content.
Ground truth (which aliases belong to the same actor) is known, so you can
train and evaluate alias-linking models properly.

Usage:
    python generate_synthetic_data.py --actors 60 --seed 42 --out data/

Outputs:
    posts.csv          one row per post (schema from README Phase 1)
    ground_truth.csv   alias -> actor_id
    positive_pairs.csv all same-actor alias pairs (label=1)
    pairs_labeled.csv  positive pairs + sampled negatives (label=0, incl. hard negatives)
"""
import argparse
import csv
import hashlib
import itertools
import os
import random
from datetime import datetime, timedelta

# ---------------------------------------------------------------- vocab ----
TOPICS = {
    "vendor": [
        "fresh stock just landed, shipping within 48 hours",
        "reship policy updated, check the listing before ordering",
        "bulk discount for repeat buyers this week",
        "escrow only, no finalize early please",
        "new batch tested and verified by third party",
        "restock soon, wait for the announcement",
    ],
    "buyer": [
        "ordered last week, still no tracking update",
        "package arrived, packaging was discreet, thanks",
        "anyone tried this vendor before? need feedback",
        "dispute opened, waiting for moderator response",
        "is this listing legit or a scam, looks too cheap",
        "delivery took longer than expected but all good",
    ],
    "tech": [
        "anyone know a good way to harden a vps setup",
        "tor bridge keeps dropping, any fix for this",
        "which mail provider is still safe these days",
        "need help configuring pgp on a new device",
        "wallet mixing service down again, alternatives",
        "forum login captcha is broken for me today",
    ],
    "gossip": [
        "heard the admin is changing the rules again",
        "market looks quiet lately, many vendors gone",
        "exit scam rumours going around, stay careful",
        "moderators are strict about new threads now",
        "anyone else notice the site is slow tonight",
        "new forum opened, invite only for now",
    ],
}

GREETINGS = ["hey", "hello", "yo", "hi all", "greetings", "sup", "namaste", "bhai", "hello friends"]
SIGNOFFS = ["", "cheers", "regards", "peace", "stay safe", "- out", "thx", "dhanyawad", "jai hind", "~"]
HINGLISH = ["yaar", "bhai", "kya scene hai", "thoda", "jaldi", "sahi hai", "mast", "ekdum", "bilkul", "pakka"]
FILLERS = ["basically", "honestly", "to be fair", "tbh", "imo", "ngl", "literally", "kinda"]
TYPO_MAP = {"the": "teh", "receive": "recieve", "definitely": "definately",
            "separate": "seperate", "because": "becuase", "which": "wich", "ordered": "orderd"}
LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}
HANDLE_A = ["shadow", "ghost", "silent", "night", "cipher", "void", "raven", "zero", "pixel", "ember",
            "storm", "nova", "echo", "cobalt", "onyx", "vector", "mirage", "falcon", "rogue", "drift"]
HANDLE_B = ["fox", "wolf", "byte", "hawk", "node", "root", "blade", "king", "rider", "smith",
            "walker", "trader", "monk", "wire", "pulse", "lord", "dealer", "scribe", "hunter", "whisper"]
PLATFORMS = ["DarkForumX", "ShadowBoard", "MarketHubOnion", "CipherTalk"]
LANGS = ["en", "hinglish", "en-IN"]


# -------------------------------------------------------------- helpers ----
def fake_hex(rng, n):
    return "".join(rng.choice("0123456789ABCDEF") for _ in range(n))


def fake_btc(rng):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "bc1" + "".join(rng.choice(alphabet) for _ in range(30))


def fake_xmr(rng):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "4" + "".join(rng.choice(alphabet) for _ in range(40))


class Actor:
    """A latent real operator behind one or more aliases."""

    def __init__(self, rng, actor_id):
        self.id = actor_id
        self.rng = rng
        self.role = rng.choice(list(TOPICS))
        self.secondary = rng.choice(list(TOPICS))
        # --- stylometric fingerprint
        self.greeting = rng.choice(GREETINGS)
        self.signoff = rng.choice(SIGNOFFS)
        self.lang = rng.choice(LANGS)
        self.hinglish_rate = rng.choice([0.0, 0.0, 0.15, 0.35, 0.5])
        self.filler = rng.choice(FILLERS + [""])
        self.filler_rate = rng.choice([0.0, 0.2, 0.5])
        self.typos = rng.sample(list(TYPO_MAP), k=rng.choice([0, 1, 2, 3]))
        self.leet_rate = rng.choice([0.0, 0.0, 0.0, 0.3, 0.6])
        self.lowercase_only = rng.random() < 0.4
        self.ellipsis = rng.random() < 0.35
        self.exclaim_rate = rng.choice([0.0, 0.1, 0.4])
        self.emoji = rng.choice(["", "", ":)", "xD", ":D", "^_^"])
        self.double_space = rng.random() < 0.2
        self.avg_sentences = rng.choice([1, 2, 3, 4])
        self.comma_style = rng.choice(["normal", "none", "heavy"])
        # --- temporal fingerprint (UTC offset in hours, active window)
        self.tz = rng.choice([5.5, 5.5, 5.5, 0, 1, 3, 8, -5])
        self.peak_local_hour = rng.choice([9, 13, 18, 21, 23, 1])
        self.hour_spread = rng.choice([1.5, 2.5, 3.5])
        self.weekday_bias = rng.choice([None, "weekend", "weekday"])
        # --- identifiers (may be shared across this actor's aliases)
        self.pgp = fake_hex(rng, 40)
        self.btc = fake_btc(rng)
        self.xmr = fake_xmr(rng)
        self.contact = f"{rng.choice(HANDLE_A)}{rng.randint(10, 99)}@jabber.example"
        self.platform_pref = rng.sample(PLATFORMS, k=rng.choice([1, 2, 3]))
        # reuse probabilities (opsec sloppiness)
        self.reuse_pgp = rng.random() < 0.25
        self.reuse_wallet = rng.random() < 0.20
        self.reuse_contact = rng.random() < 0.20
        # adversarial: deliberately tries to mask style
        self.obfuscates = rng.random() < 0.12

    # ---- text generation
    def _apply_style(self, text, obf=False):
        rng = self.rng
        words = text.split()
        out = []
        for w in words:
            if not obf:
                if w in self.typos or w in TYPO_MAP and w in self.typos:
                    w = TYPO_MAP.get(w, w)
                if self.leet_rate and rng.random() < self.leet_rate * 0.3:
                    w = "".join(LEET.get(c, c) if rng.random() < 0.5 else c for c in w)
            out.append(w)
        text = " ".join(out)
        if self.comma_style == "none":
            text = text.replace(",", "")
        elif self.comma_style == "heavy" and not obf:
            text = text.replace(" and ", ", and ").replace(" but ", ", but ")
        if self.lowercase_only and not obf:
            text = text.lower()
        elif not self.lowercase_only:
            text = text[:1].upper() + text[1:]
        if self.double_space and not obf:
            text = text.replace(". ", ".  ")
        return text

    def make_post(self, rng, obf=False):
        n = max(1, int(rng.gauss(self.avg_sentences, 1)))
        parts = []
        for _ in range(n):
            topic = self.role if rng.random() < 0.7 else self.secondary
            s = rng.choice(TOPICS[topic])
            if not obf and self.hinglish_rate and rng.random() < self.hinglish_rate:
                s = f"{rng.choice(HINGLISH)}, {s}"
            if not obf and self.filler and rng.random() < self.filler_rate:
                s = f"{self.filler} {s}"
            s = self._apply_style(s, obf)
            end = "..." if (self.ellipsis and not obf and rng.random() < 0.5) else (
                "!" if rng.random() < self.exclaim_rate else ".")
            parts.append(s + end)
        body = " ".join(parts)
        if rng.random() < 0.5:
            g = self.greeting if not obf else rng.choice(GREETINGS)
            body = f"{g}, {body}" if not self.lowercase_only else f"{g.lower()}, {body}"
        if self.signoff and rng.random() < 0.6 and not obf:
            body += f" {self.signoff}"
        if self.emoji and rng.random() < 0.4 and not obf:
            body += f" {self.emoji}"
        return body.strip()

    def sample_time(self, rng, start, days):
        for _ in range(50):
            day = rng.randint(0, days - 1)
            d = start + timedelta(days=day)
            if self.weekday_bias == "weekend" and d.weekday() < 5 and rng.random() < 0.7:
                continue
            if self.weekday_bias == "weekday" and d.weekday() >= 5 and rng.random() < 0.7:
                continue
            local_h = int(rng.gauss(self.peak_local_hour, self.hour_spread)) % 24
            utc_h = int((local_h - self.tz) % 24)
            return d.replace(hour=utc_h, minute=rng.randint(0, 59), second=rng.randint(0, 59))
        return start


def make_handle(rng, used):
    while True:
        style = rng.choice(["a_b", "ab99", "A-B", "xAbx", "a.b"])
        a, b = rng.choice(HANDLE_A), rng.choice(HANDLE_B)
        h = {"a_b": f"{a}_{b}", "ab99": f"{a}{b}{rng.randint(1, 99)}",
             "A-B": f"{a.title()}-{b.title()}", "xAbx": f"x{a}{b}x", "a.b": f"{a}.{b}"}[style]
        if h not in used:
            used.add(h)
            return h


# ----------------------------------------------------------------- main ----
def generate(n_actors, seed, out_dir):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    start = datetime(2025, 1, 1)
    days = 540

    actors = [Actor(rng, f"A{str(i).zfill(3)}") for i in range(n_actors)]
    used_handles, alias_rows, posts = set(), [], []
    post_id = 0
    thread_id = 0

    for act in actors:
        n_alias = rng.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
        # aliases appear sequentially (ban / exit scam handovers) -> timeline pattern
        window = days // max(n_alias, 1)
        for k in range(n_alias):
            alias = make_handle(rng, used_handles)
            a_start = start + timedelta(days=k * window)
            platform_list = act.platform_pref
            alias_rows.append({"alias": alias, "actor_id": act.id, "alias_index": k,
                               "obfuscating": int(act.obfuscates and k > 0)})
            n_posts = rng.randint(15, 70)
            # per-alias identifiers: reused or fresh
            pgp = act.pgp if (act.reuse_pgp or k == 0) else fake_hex(rng, 40)
            btc = act.btc if (act.reuse_wallet or k == 0) else fake_btc(rng)
            contact = act.contact if (act.reuse_contact or k == 0) else \
                f"{rng.choice(HANDLE_A)}{rng.randint(10, 99)}@jabber.example"
            obf = act.obfuscates and k > 0
            for _ in range(n_posts):
                ts = act.sample_time(rng, a_start, window)
                thread_id += 1 if rng.random() < 0.5 else 0
                text = act.make_post(rng, obf=obf)
                attach_hash = ""
                if rng.random() < 0.04:
                    attach_hash = hashlib.sha1(f"{act.id}-file-{rng.randint(1, 3)}".encode()).hexdigest()[:16] \
                        if rng.random() < 0.5 else hashlib.sha1(str(rng.random()).encode()).hexdigest()[:16]
                posts.append({
                    "post_id": f"P{post_id:06d}",
                    "alias": alias,
                    "platform": rng.choice(platform_list),
                    "thread_id": f"T{thread_id:05d}",
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "text": text,
                    "language": act.lang,
                    "links": "",
                    "attachments": attach_hash,
                    "pgp_key": pgp if rng.random() < 0.15 else "",
                    "crypto_address": btc if rng.random() < 0.08 else "",
                    "contact_handle": contact if rng.random() < 0.10 else "",
                })
                post_id += 1

    # shuffle chronologically like a real crawl
    posts.sort(key=lambda r: r["timestamp"])

    def write(name, rows, fields):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    write("posts.csv", posts, list(posts[0].keys()))
    write("ground_truth.csv", alias_rows, ["alias", "actor_id", "alias_index", "obfuscating"])

    # labeled pairs
    by_actor = {}
    for r in alias_rows:
        by_actor.setdefault(r["actor_id"], []).append(r["alias"])
    positives = [(a, b) for al in by_actor.values() for a, b in itertools.combinations(al, 2)]
    actor_of = {r["alias"]: r["actor_id"] for r in alias_rows}
    role_of = {a.id: a.role for a in actors}
    all_alias = list(actor_of)

    negatives, hard = [], 0
    target = len(positives) * 3
    attempts = 0
    while len(negatives) < target and attempts < target * 50:
        attempts += 1
        a, b = rng.sample(all_alias, 2)
        if actor_of[a] == actor_of[b]:
            continue
        is_hard = role_of[actor_of[a]] == role_of[actor_of[b]]
        if not is_hard and hard < len(negatives) * 0.5 and rng.random() < 0.7:
            continue  # bias toward hard negatives (same topic, different person)
        negatives.append((a, b))
        hard += int(is_hard)

    write("positive_pairs.csv", [{"alias_a": a, "alias_b": b, "label": 1} for a, b in positives],
          ["alias_a", "alias_b", "label"])
    pair_rows = [{"alias_a": a, "alias_b": b, "label": 1} for a, b in positives] + \
                [{"alias_a": a, "alias_b": b, "label": 0} for a, b in negatives]
    rng.shuffle(pair_rows)
    write("pairs_labeled.csv", pair_rows, ["alias_a", "alias_b", "label"])

    print(f"actors={n_actors} aliases={len(alias_rows)} posts={len(posts)} "
          f"positive_pairs={len(positives)} negative_pairs={len(negatives)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--actors", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/")
    args = ap.parse_args()
    generate(args.actors, args.seed, args.out)
