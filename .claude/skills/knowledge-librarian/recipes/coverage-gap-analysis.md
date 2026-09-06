# Recipe: Assess — coverage gaps

Goal: find which taxonomy terms are under-served and fill them, so the library actually
covers the domain's question surface instead of clustering around a few topics.

## Steps

1. **Confirm a taxonomy is linked** — `agentbase_get_library { library_id }`; look for
   `taxonomy_id`. If null, do taxonomy-design.md first (coverage needs a taxonomy).
2. **Run coverage analysis** — `agentbase_get_library_coverage { library_id }`. Returns
   per-term chunk counts and a rating:
   - `deep` — ≥ 20 chunks
   - `adequate` — ≥ 10
   - `thin` — ≥ 1
   - `none` — 0
3. **Target the gaps.** For every `thin` and `none` term, go back to source-discovery.md:
   find sources that cover that term, then build-library.md to create → index → attach
   them to this library.
4. **Re-assess** — `agentbase_get_library_coverage` again. Loop until coverage meets your
   quality bar (e.g. no `none` on any must-answer term; core terms `adequate`+).

## Notes

- Coverage is a *map of where to dig next*, not a pass/fail. Prioritize terms that map to
  your representative questions from discovery.
- Cross-check with `agentbase_search_library` on a gap term: sometimes content exists but
  is mis-classified — fix via re-enrichment rather than adding redundant sources.
- Adding content can also *reveal* new needed terms — feed taxonomy suggestions back into
  taxonomy-design.md.
