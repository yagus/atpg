#!/usr/bin/env python3
import csv
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

API = "https://api.openalex.org/works"
START_DATE = "2020-01-01"
END_DATE = "2026-12-31"
TARGET = 320
PER_PAGE = 200
MAILTO = "yaguscahyadi@gmail.com"

SEARCH_TERMS = [
    "artificial intelligence chemistry education",
    "generative artificial intelligence chemistry education",
    "ChatGPT chemistry education",
    "large language models chemistry education",
    "machine learning chemistry education",
    "artificial intelligence science education",
    "generative AI science education",
    "ChatGPT science education",
    "artificial intelligence STEM education",
    "generative AI STEM education",
    "AI tutoring education",
    "AI scaffold learning education",
    "artificial intelligence critical thinking education",
    "ChatGPT critical thinking education",
    "generative AI assessment education",
    "artificial intelligence personalized learning",
    "adaptive learning artificial intelligence",
    "artificial intelligence feedback education",
    "AI ethics education",
    "AI fairness education",
    "AI equity education",
    "academic integrity generative AI education",
    "AI literacy education",
    "human oversight artificial intelligence education",
    "Socratic tutoring large language model education",
    "artificial intelligence inquiry based learning",
    "generative AI conceptual understanding education",
    "artificial intelligence problem solving education",
    "AI inclusive education accessibility",
    "large language model educational feedback",
]

AI_TERMS = [
    "artificial intelligence", "generative ai", "generative artificial intelligence",
    "chatgpt", "large language model", "large language models", " llm ", " llms ",
    "machine learning", "deep learning", "intelligent tutoring", "ai tutor",
    "ai-assisted", "ai assisted", "ai-powered", "ai powered", "chatbot"
]
EDU_TERMS = [
    "education", "learning", "teaching", "student", "students", "teacher", "teachers",
    "classroom", "instruction", "pedagogy", "curriculum", "assessment", "feedback",
    "tutor", "tutoring", "learner", "learners", "academic", "school", "university"
]
CHEM_TERMS = [
    "chemistry", "chemical education", "chemical concept", "molecular", "stoichiometry",
    "organic chemistry", "inorganic chemistry", "physical chemistry", "analytical chemistry",
    "biochemistry", "laboratory chemistry", "chemistry learning"
]
SCIENCE_TERMS = [
    "science education", "science learning", "science teaching", "stem education", "stem learning",
    "physics education", "biology education", "scientific reasoning", "scientific literacy"
]
CRITICAL_TERMS = [
    "critical thinking", "reasoning", "problem solving", "problem-solving", "evaluation",
    "metacognition", "argumentation", "evidence-based", "source evaluation", "verification"
]
SCAFFOLD_TERMS = [
    "scaffold", "scaffolding", "hint", "hints", "socratic", "tutor", "tutoring",
    "feedback", "guidance", "guided", "facilitat", "support", "learning assistant"
]
EQUITY_TERMS = [
    "fairness", "equity", "equitable", "inclusive", "inclusion", "accessibility",
    "digital divide", "bias", "ethical", "ethics", "responsible ai", "social justice"
]
MEANINGFUL_TERMS = [
    "meaningful learning", "conceptual understanding", "engagement", "motivation", "inquiry",
    "active learning", "collaborative learning", "self-regulated learning", "deep learning approach",
    "authentic learning", "higher-order thinking"
]
NEGATIVE_DISCIPLINES = {
    "medicine": ["medical education", "medical students", "clinical education", "health professions education"],
    "nursing": ["nursing education", "nursing students"],
    "programming": ["programming education", "computer science education", "software engineering education", "coding education"],
    "business": ["business education", "accounting education", "management education"],
    "law": ["legal education", "law students"],
}


def get_json(url, retries=5):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": f"AI-Chemistry-Education-Literature/1.0 (mailto:{MAILTO})",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def reconstruct_abstract(inv):
    if not inv:
        return ""
    positions = []
    for word, indexes in inv.items():
        for idx in indexes:
            positions.append((idx, word))
    positions.sort()
    return " ".join(word for _, word in positions).strip()


def norm_doi(value):
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.I)
    return value.lower()


def contains_any(text, terms):
    return any(term in text for term in terms)


def count_terms(text, terms):
    return sum(1 for term in terms if term in text)


def classify(text):
    if contains_any(text, CHEM_TERMS):
        return "A. AI dalam pembelajaran kimia"
    if contains_any(text, SCIENCE_TERMS) or " stem " in f" {text} ":
        return "B. AI dalam pembelajaran sains/STEM"
    if contains_any(text, SCAFFOLD_TERMS):
        return "C. AI sebagai pemantik, tutor, scaffolding, atau umpan balik"
    if contains_any(text, CRITICAL_TERMS) or "assessment" in text or "academic integrity" in text:
        return "D. Berpikir kritis, asesmen, verifikasi, dan integritas akademik"
    if contains_any(text, EQUITY_TERMS):
        return "E. Keadilan, etika, inklusi, dan akses"
    if contains_any(text, MEANINGFUL_TERMS):
        return "F. Pembelajaran bermakna, motivasi, dan keterlibatan"
    return "G. Implementasi umum AI generatif dalam pendidikan"


def relevance_score(title, abstract, year, cited_by_count, query_hits):
    text = f" {title} {abstract} ".lower()
    if not contains_any(text, AI_TERMS) or not contains_any(text, EDU_TERMS):
        return -999
    score = 20
    score += 22 * count_terms(text, CHEM_TERMS)
    score += 10 * count_terms(text, SCIENCE_TERMS)
    score += 7 * min(4, count_terms(text, CRITICAL_TERMS))
    score += 7 * min(4, count_terms(text, SCAFFOLD_TERMS))
    score += 6 * min(4, count_terms(text, EQUITY_TERMS))
    score += 5 * min(4, count_terms(text, MEANINGFUL_TERMS))
    if "chatgpt" in text or "large language model" in text or "generative ai" in text or "generative artificial intelligence" in text:
        score += 6
    if "human oversight" in text or "not provide direct" in text or "without revealing solutions" in text:
        score += 7
    score += min(8, query_hits * 2)
    score += max(0, year - 2020) * 0.5
    score += min(4, math.log10(max(1, cited_by_count + 1)))
    for terms in NEGATIVE_DISCIPLINES.values():
        if contains_any(text, terms):
            score -= 5
    if len(abstract) < 300:
        score -= 4
    return round(score, 3)


def fetch_query(term, pages=1):
    cursor = "*"
    rows = []
    for _ in range(pages):
        filters = ",".join([
            f"from_publication_date:{START_DATE}",
            f"to_publication_date:{END_DATE}",
            "is_oa:true",
            "has_doi:true",
            "has_abstract:true",
            "type:article",
        ])
        params = {
            "search": term,
            "filter": filters,
            "per-page": str(PER_PAGE),
            "cursor": cursor,
            "mailto": MAILTO,
        }
        url = API + "?" + urllib.parse.urlencode(params)
        data = get_json(url)
        results = data.get("results", [])
        rows.extend(results)
        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            break
        time.sleep(0.15)
    return rows


def extract_record(work):
    title = (work.get("display_name") or work.get("title") or "").strip()
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    doi = norm_doi(work.get("doi"))
    year = int(work.get("publication_year") or 0)
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    source_type = (source.get("type") or "").lower()
    journal = (source.get("display_name") or "").strip()
    if source_type and source_type != "journal":
        return None
    if not title or not abstract or not doi or year < 2020 or year > 2026:
        return None
    authors = []
    for auth in work.get("authorships") or []:
        name = ((auth.get("author") or {}).get("display_name") or "").strip()
        if name:
            authors.append(name)
    best_oa = work.get("best_oa_location") or {}
    oa = work.get("open_access") or {}
    oa_url = best_oa.get("pdf_url") or best_oa.get("landing_page_url") or f"https://doi.org/{doi}"
    publisher = source.get("host_organization_name") or ""
    return {
        "openalex_id": work.get("id") or "",
        "title": title,
        "abstract": abstract,
        "doi": doi,
        "year": year,
        "publication_date": work.get("publication_date") or "",
        "journal": journal,
        "publisher": publisher,
        "authors": "; ".join(authors[:20]),
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "oa_status": oa.get("oa_status") or "",
        "oa_url": oa_url,
        "is_oa": bool(oa.get("is_oa")),
        "is_in_doaj": bool(source.get("is_in_doaj")),
        "issn_l": source.get("issn_l") or "",
        "source_type": source_type or "journal",
        "query_hits": 0,
        "queries": set(),
    }


def main():
    os.makedirs("output", exist_ok=True)
    records = {}
    fetch_log = []
    for idx, term in enumerate(SEARCH_TERMS, 1):
        pages = 2 if "chemistry" in term.lower() else 1
        works = fetch_query(term, pages=pages)
        fetch_log.append({"term": term, "records_returned": len(works)})
        for work in works:
            rec = extract_record(work)
            if not rec:
                continue
            key = rec["doi"] or rec["openalex_id"]
            if key not in records:
                records[key] = rec
            records[key]["query_hits"] += 1
            records[key]["queries"].add(term)
        print(f"[{idx:02d}/{len(SEARCH_TERMS)}] {term}: {len(works)} results; unique={len(records)}", flush=True)

    candidates = []
    for rec in records.values():
        score = relevance_score(
            rec["title"], rec["abstract"], rec["year"], rec["cited_by_count"], rec["query_hits"]
        )
        if score < 20:
            continue
        text = f" {rec['title']} {rec['abstract']} ".lower()
        rec["category"] = classify(text)
        rec["relevance_score"] = score
        rec["queries"] = " | ".join(sorted(rec["queries"]))
        candidates.append(rec)

    candidates.sort(key=lambda r: (-r["relevance_score"], -r["year"], -r["cited_by_count"], r["title"]))

    # Preserve disciplinary relevance and thematic diversity.
    selected = []
    category_caps = {
        "A. AI dalam pembelajaran kimia": 90,
        "B. AI dalam pembelajaran sains/STEM": 75,
        "C. AI sebagai pemantik, tutor, scaffolding, atau umpan balik": 75,
        "D. Berpikir kritis, asesmen, verifikasi, dan integritas akademik": 65,
        "E. Keadilan, etika, inklusi, dan akses": 50,
        "F. Pembelajaran bermakna, motivasi, dan keterlibatan": 50,
        "G. Implementasi umum AI generatif dalam pendidikan": 55,
    }
    counts = Counter()
    for rec in candidates:
        cat = rec["category"]
        if counts[cat] < category_caps[cat]:
            selected.append(rec)
            counts[cat] += 1
        if len(selected) >= TARGET:
            break

    # Fill to target without caps if needed.
    if len(selected) < TARGET:
        seen = {r["doi"] for r in selected}
        for rec in candidates:
            if rec["doi"] not in seen:
                selected.append(rec)
                seen.add(rec["doi"])
            if len(selected) >= TARGET:
                break

    fields = [
        "no", "title", "abstract", "doi", "year", "publication_date", "journal", "publisher",
        "authors", "category", "relevance_score", "cited_by_count", "oa_status", "is_in_doaj",
        "oa_url", "openalex_id", "issn_l", "source_type", "query_hits", "queries"
    ]
    out_csv = "output/ai_chemistry_education_literature.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, rec in enumerate(selected, 1):
            row = {k: rec.get(k, "") for k in fields}
            row["no"] = i
            writer.writerow(row)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_year_range": "2020-2026",
        "target": TARGET,
        "selected": len(selected),
        "unique_candidates": len(candidates),
        "unique_raw_records": len(records),
        "category_counts": dict(Counter(r["category"] for r in selected)),
        "year_counts": dict(sorted(Counter(str(r["year"]) for r in selected).items())),
        "search_terms": SEARCH_TERMS,
        "fetch_log": fetch_log,
        "method_note": (
            "Records were discovered through the OpenAlex API, restricted to open-access journal articles "
            "with DOI and abstract, publication years 2020-2026. Ranking emphasizes chemistry/science education, "
            "AI as scaffold/tutor/feedback, critical thinking, meaningful learning, fairness, ethics, and access. "
            "Scopus indexing was not individually verified; DOI and source links support follow-up checking in "
            "Google Scholar, Scopus Sources, Crossref, and publisher pages."
        ),
    }
    with open("output/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if len(selected) < 200:
        raise SystemExit(f"Only {len(selected)} eligible records found; expected at least 200")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
