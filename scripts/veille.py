#!/usr/bin/env python3
"""Veille d'actualité — DSCG UE6.

Récupère les flux configurés dans scripts/veille_config.json, classe chaque
article par thème (mots-clés de data/mots-cles-themes.json pour les flux
généralistes, ou thème fixe pour les alertes Google Alerts dédiées à un thème),
puis met à jour data/actualite.json.

Formats gérés : RSS 2.0 (médias classiques) ET Atom (Google Alerts).
Les liens Google Alerts (redirections google.com/url?...&url=...) sont
automatiquement remplacés par l'URL réelle de l'article.

Ne stocke jamais le texte intégral d'un article : uniquement titre, source,
lien et date (voir Mentions légales du site).

Usage : python3 scripts/veille.py
Code de sortie : 0 même si certains flux échouent (les échecs sont listés),
1 uniquement si AUCUN flux configuré n'a pu être lu (vrai problème réseau).
"""
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG_PATH = Path(__file__).resolve().parent / "veille_config.json"

# Certains serveurs (BBC, Guardian...) refusent les user-agents inconnus :
# on se présente comme un navigateur standard.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}
TIMEOUT = 20
ATOM_NS = "{http://www.w3.org/2005/Atom}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"


def load_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def strip_html(text):
    """Retire les balises HTML (titres Google Alerts : <b>...</b>) et décode les entités."""
    if not text:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def unwrap_google_url(url):
    """https://www.google.com/url?...&url=ARTICLE&... -> ARTICLE"""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.endswith("google.com") and parsed.path == "/url":
            qs = urllib.parse.parse_qs(parsed.query)
            real = qs.get("url") or qs.get("q")
            if real:
                return real[0]
    except ValueError:
        pass
    return url


def parse_date(raw):
    """Accepte RFC 822 (RSS) ou ISO 8601 (Atom, dc:date)."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_feed(xml_bytes):
    """Retourne [{titre, url, date, resume}] depuis un flux RSS 2.0 OU Atom."""
    root = ET.fromstring(xml_bytes)
    items = []

    # --- RSS 2.0 : <rss><channel><item> ---
    for item in root.iter("item"):
        title = strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or item.findtext(f"{DC_NS}date")
        desc = strip_html(item.findtext("description") or "")
        if title and link:
            items.append({"titre": title, "url": link, "date": parse_date(pub), "resume": desc})

    # --- Atom (Google Alerts) : <feed><entry> ---
    for entry in root.iter(f"{ATOM_NS}entry"):
        title = strip_html(entry.findtext(f"{ATOM_NS}title") or "")
        link = ""
        for l in entry.findall(f"{ATOM_NS}link"):
            href = l.get("href", "")
            if href and l.get("rel", "alternate") == "alternate":
                link = href
                break
        link = unwrap_google_url(link.strip())
        pub = entry.findtext(f"{ATOM_NS}published") or entry.findtext(f"{ATOM_NS}updated")
        desc = strip_html(entry.findtext(f"{ATOM_NS}content") or entry.findtext(f"{ATOM_NS}summary") or "")
        if title and link:
            items.append({"titre": title, "url": link, "date": parse_date(pub), "resume": desc})

    return items


def classify(text, keywords_by_theme):
    low = " " + text.lower() + " "
    best_id, best_score = None, 0
    for chap_id, keywords in keywords_by_theme.items():
        score = sum(1 for kw in keywords if kw.lower() in low)
        if score > best_score:
            best_id, best_score = chap_id, score
    return best_id


def source_from_url(url):
    """Nom de domaine lisible, pour les articles Google Alerts (source variable)."""
    try:
        host = urllib.parse.urlparse(url).netloc
        return host.removeprefix("www.") or "Source inconnue"
    except ValueError:
        return "Source inconnue"


def make_id(url):
    return "art-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def main():
    # Un fichier de configuration absent ou vide doit être une erreur visible :
    # sinon le script se termine "en vert" avec 0 article et rien n'explique pourquoi.
    if not CONFIG_PATH.exists():
        print(f"  !! Fichier de configuration introuvable : {CONFIG_PATH}")
        print("     Vérifier que scripts/veille_config.json est bien présent dans le dépôt.")
        raise SystemExit(1)
    try:
        config = load_json(CONFIG_PATH, {})
    except json.JSONDecodeError as e:
        print(f"  !! {CONFIG_PATH.name} est mal formé (JSON invalide) : {e}")
        raise SystemExit(1)

    feeds = config.get("feeds", [])
    if not feeds:
        print(f"  !! Aucun flux déclaré dans {CONFIG_PATH.name} (liste « feeds » vide ou absente).")
        raise SystemExit(1)
    print(f"  {len(feeds)} flux déclaré(s) dans {CONFIG_PATH.name}")
    max_par_theme = config.get("max_par_theme", 15)
    max_age_jours = config.get("max_age_jours", 120)

    keywords_by_theme = load_json(DATA / "mots-cles-themes.json", {})
    existing = load_json(DATA / "actualite.json", [])

    print("=== Veille d'actualité — UE6 ===")
    configured = [f for f in feeds if f.get("url") and "VOTRE_" not in f.get("url", "")]
    skipped = len(feeds) - len(configured)
    ok_feeds, failed_feeds = 0, 0
    classified_out = 0
    collected = []

    for feed in configured:
        url = feed["url"]
        source = feed.get("source", "Source inconnue")
        mode = feed.get("mode", "classify")
        is_alert = "google.com/alerts" in url
        try:
            items = parse_feed(fetch(url))
            ok_feeds += 1
        except Exception as e:
            print(f"  ! échec sur « {source} » : {e}")
            failed_feeds += 1
            continue
        print(f"  {source} : {len(items)} article(s) récupéré(s)")
        for it in items:
            chap_id = feed.get("chapitre_id") if mode == "fixed" else classify(
                it["titre"] + " " + it["resume"], keywords_by_theme
            )
            if not chap_id:
                classified_out += 1
                continue
            collected.append({
                "id": make_id(it["url"]),
                "chapitre_id": chap_id,
                "titre": it["titre"],
                "source": source_from_url(it["url"]) if is_alert else source,
                "url": it["url"],
                "date": it["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })

    if skipped:
        print(f"  {skipped} flux ignoré(s) (URL non configurée dans veille_config.json)")
    if classified_out:
        print(f"  {classified_out} article(s) sans thème identifiable (ignorés)")

    merged = {a["id"]: a for a in existing if "id" in a}
    new_count = sum(1 for a in collected if a["id"] not in merged)
    for a in collected:
        merged[a["id"]] = a

    cutoff = None
    if max_age_jours:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_jours)).strftime("%Y-%m-%d")

    by_theme = {}
    for a in merged.values():
        if cutoff and a.get("date") and a["date"] < cutoff:
            continue
        by_theme.setdefault(a["chapitre_id"], []).append(a)

    final = []
    for arts in by_theme.values():
        arts.sort(key=lambda a: a.get("date") or "", reverse=True)
        final.extend(arts[:max_par_theme])
    final.sort(key=lambda a: a.get("date") or "", reverse=True)

    with (DATA / "actualite.json").open("w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  Bilan : {ok_feeds} flux OK, {failed_feeds} en échec — "
          f"{new_count} nouvel(le)s article(s), {len(final)} au total dans data/actualite.json")

    if configured and ok_feeds == 0:
        print("  !! Aucun flux n'a pu être lu : vérifier la connectivité ou les URLs.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
