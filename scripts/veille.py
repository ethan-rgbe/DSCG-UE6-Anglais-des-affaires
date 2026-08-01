#!/usr/bin/env python3
"""Veille d'actualité — DSCG UE6.

Récupère les flux RSS configurés dans scripts/veille_config.json, classe chaque
article par thème (mots-clés de data/mots-cles-themes.json pour les flux
généralistes, ou thème fixe pour les alertes Google Alerts dédiées à un thème),
puis met à jour data/actualite.json.

Ne stocke jamais le texte intégral d'un article : uniquement titre, source,
lien et date (voir Mentions légales du site — même principe que les annales
du site UE1, on ne réhéberge pas de contenu protégé).

Usage : python3 scripts/veille.py
"""
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG_PATH = Path(__file__).resolve().parent / "veille_config.json"

USER_AGENT = "Mozilla/5.0 (compatible; LePrecisUE6-Veille/1.0)"
TIMEOUT = 15
DC_NS = "{http://purl.org/dc/elements/1.1/}"


def load_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def parse_date(raw):
    """Accepte RFC 822 (RSS classique) ou ISO 8601 (certains flux dc:date)."""
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


def parse_rss(xml_bytes):
    """Retourne une liste de {titre, url, date, resume} depuis un flux RSS 2.0."""
    items = []
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or item.findtext(f"{DC_NS}date")
        desc = (item.findtext("description") or "").strip()
        if not title or not link:
            continue
        items.append({"titre": title, "url": link, "date": parse_date(pub), "resume": desc})
    return items


def classify(text, keywords_by_theme):
    """Thème avec le plus de mots-clés trouvés dans le texte, ou None si aucun."""
    low = " " + text.lower() + " "
    best_id, best_score = None, 0
    for chap_id, keywords in keywords_by_theme.items():
        score = sum(1 for kw in keywords if kw.lower() in low)
        if score > best_score:
            best_id, best_score = chap_id, score
    return best_id


def make_id(url):
    return "art-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def main():
    config = load_json(CONFIG_PATH, {})
    feeds = config.get("feeds", [])
    max_par_theme = config.get("max_par_theme", 15)
    max_age_jours = config.get("max_age_jours", 120)

    keywords_by_theme = load_json(DATA / "mots-cles-themes.json", {})
    existing = load_json(DATA / "actualite.json", [])

    print("=== Veille d'actualité — UE6 ===")
    skipped_feeds, classified_out = 0, 0
    collected = []

    for feed in feeds:
        url = feed.get("url", "")
        source = feed.get("source", "Source inconnue")
        mode = feed.get("mode", "classify")
        if not url or "VOTRE_" in url:
            skipped_feeds += 1
            continue
        try:
            items = parse_rss(fetch(url))
        except Exception as e:
            print(f"  ! échec sur « {source} » ({url}) : {e}")
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
                "source": source,
                "url": it["url"],
                "date": it["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })

    if skipped_feeds:
        print(f"  {skipped_feeds} flux ignoré(s) (URL non configurée dans veille_config.json)")
    if classified_out:
        print(f"  {classified_out} article(s) non rattachés à un thème (aucun mot-clé trouvé, ignorés)")

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

    print(f"  {new_count} nouvel(le)s article(s) ajouté(s), {len(final)} au total dans data/actualite.json")


if __name__ == "__main__":
    main()
