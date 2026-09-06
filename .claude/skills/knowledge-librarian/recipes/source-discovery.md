# Recipe: Discover sources

Goal: identify the *authoritative* sources for a domain before ingesting anything.
Curation quality is capped by source quality — garbage in, confident-but-wrong out.

## Approach

1. **Define the domain's question surface.** What kinds of questions must downstream
   agents answer? Write 5–10 representative questions; they become both your source
   checklist and your later evaluation seed (see evaluation.md).
2. **Enumerate candidate sources** by type:
   - **Web / docs** — official documentation sites, API references, spec pages,
     vendor knowledge bases, authoritative guides.
   - **Local files / directories** — PDFs, DOCX, manuals, exported wikis, code books.
   - **Existing Agentbase sources** — `agentbase_list_sources`; an authoritative root
     may already be indexed.
3. **Prefer primary, stable, structured sources.** Official docs over forum threads;
   canonical references over blog aggregations. Note volatility per source — it drives
   the freshness policy you'll set at ingestion.
4. **Preview a web source before committing** — `agentbase_scan_url` to see the page/URL
   structure and how many pages a crawl would pull. Use it to decide `selected_urls`
   scoping so you index the right slice, not the whole domain.
5. **Rank and scope.** For each chosen source, decide: full crawl vs. selected URLs vs.
   a sub-source (filtered view) over an existing root.

## Output of this phase

A short source plan: for each source — name, type (`url` / `file` / `directory`),
path, scope (full vs. `selected_urls`), and intended freshness policy. Feed it into
build-library.md.

## Notes

- `agentbase_scan_url` is read-only discovery; it does not create or index anything.
- Don't over-crawl. A tightly scoped, on-topic source outperforms a huge noisy one for
  retrieval precision.
