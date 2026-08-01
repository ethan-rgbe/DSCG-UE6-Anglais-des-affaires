#!/usr/bin/env python3
"""Build script — LE PRÉCIS, DSCG UE6 (Anglais des affaires).

Lit data/*.json + content/*.md, injecte le tout dans templates/index_template.html
et produit public/index.html en fichier unique (auto-suffisant, sans dépendance externe).

Usage : python3 scripts/build.py
"""
import json
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
PUBLIC = ROOT / "public"

MD = markdown.Markdown(extensions=["extra", "sane_lists"])


def load_json(name):
    path = DATA / name
    if not path.exists():
        print(f"  ! {name} introuvable — traité comme liste vide.")
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def md_to_html(text):
    MD.reset()
    return MD.convert(text or "")


def build_cours():
    """content/<chapitre_id>.md -> { chapitre_id: html }"""
    cours = {}
    if not CONTENT.exists():
        return cours
    for md_file in sorted(CONTENT.glob("*.md")):
        chapitre_id = md_file.stem
        cours[chapitre_id] = md_to_html(md_file.read_text(encoding="utf-8"))
    return cours


def main():
    print("=== Build LE PRÉCIS — UE6 ===")

    chapitres = load_json("chapitres.json")
    vocabulaire = load_json("vocabulaire.json")
    expressions = load_json("expressions.json")
    phrases_orales = load_json("phrases-orales.json")
    rappels_grammaire = load_json("rappels-grammaire.json")
    actualite = load_json("actualite.json")
    qr_cartes = load_json("qr_cartes.json")
    liens_utiles = load_json("liens-utiles.json")

    for r in rappels_grammaire:
        r["contenu_html"] = md_to_html(r.get("contenu_md", ""))

    cours = build_cours()

    # ---- Contrôles d'intégrité référentielle (avertissements, non bloquants) ----
    chap_ids = {c["id"] for c in chapitres}
    warnings = []
    for v in vocabulaire:
        if v.get("chapitre_id") is not None and v.get("chapitre_id") not in chap_ids:
            warnings.append(f"vocabulaire {v.get('id')} : chapitre_id inconnu ({v.get('chapitre_id')!r})")
    for e in expressions:
        if e.get("chapitre_id") is not None and e.get("chapitre_id") not in chap_ids:
            warnings.append(f"expressions {e.get('id')} : chapitre_id inconnu ({e.get('chapitre_id')!r})")
    for a in actualite:
        if a.get("chapitre_id") not in chap_ids:
            warnings.append(f"actualite {a.get('id')} : chapitre_id inconnu ({a.get('chapitre_id')!r})")
    for c in qr_cartes:
        if c.get("chapitre_id") and c.get("chapitre_id") not in chap_ids:
            warnings.append(f"qr_cartes {c.get('id')} : chapitre_id inconnu ({c.get('chapitre_id')!r})")
        ref_id = c.get("ref_id")
        ctype = c.get("type")
        pool = {"vocabulaire": vocabulaire, "expression": expressions, "phrase": phrases_orales}.get(ctype, [])
        if ref_id and not any(x.get("id") == ref_id for x in pool):
            warnings.append(f"qr_cartes {c.get('id')} : ref_id {ref_id!r} introuvable dans {ctype}")
    for cid in cours:
        if cid not in chap_ids:
            warnings.append(f"content/{cid}.md : ne correspond à aucun chapitre_id de chapitres.json")

    if warnings:
        print(f"  ! {len(warnings)} avertissement(s) d'intégrité :")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  Intégrité référentielle : OK (aucun chapitre_id/ref_id orphelin détecté)")

    bundle = {
        "chapitres": chapitres,
        "vocabulaire": vocabulaire,
        "expressions": expressions,
        "phrases_orales": phrases_orales,
        "rappels_grammaire": rappels_grammaire,
        "actualite": actualite,
        "qr_cartes": qr_cartes,
        "liens_utiles": liens_utiles,
        "cours": cours,
    }

    bundle_json = json.dumps(bundle, ensure_ascii=False)
    # Empêche la fermeture prématurée de la balise <script> si jamais
    # "</" apparaît dans une valeur (ex. un lien, un exemple de code).
    bundle_json = bundle_json.replace("</", "<\\/")

    template_path = TEMPLATES / "index_template.html"
    template = template_path.read_text(encoding="utf-8")
    if "__BUNDLE_JSON__" not in template:
        print("  ! Le template ne contient pas le marqueur __BUNDLE_JSON__ — abandon.")
        sys.exit(1)
    output = template.replace("__BUNDLE_JSON__", bundle_json, 1)

    PUBLIC.mkdir(exist_ok=True)
    out_path = PUBLIC / "index.html"
    out_path.write_text(output, encoding="utf-8")

    print(f"  {len(chapitres)} thèmes, {len(vocabulaire)} mots de vocabulaire, "
          f"{len(expressions)} expressions, {len(phrases_orales)} phrases, "
          f"{len(rappels_grammaire)} rappels de grammaire, {len(actualite)} articles, "
          f"{len(qr_cartes)} cartes de révision, {len(liens_utiles)} liens utiles, "
          f"{len(cours)} synthèse(s) rédigée(s)")
    print(f"  -> {out_path} ({out_path.stat().st_size:,} octets)")


if __name__ == "__main__":
    main()
