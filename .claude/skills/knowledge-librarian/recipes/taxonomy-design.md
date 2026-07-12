# Recipe: Organize — design a taxonomy and enrich content

Goal: give the library a classification scheme so content is auto-tagged, coverage is
measurable, and search can be filtered. Worth doing once a library spans multiple
platforms/products/topics; skip for a tiny single-topic library.

## Design first

Sketch the **facets** (dimensions) and their **terms** before creating anything.
Common facets: `platform`, `product`, `doc_category`, `topic`. Keep facets orthogonal
(a chunk can carry one value per facet) and terms mutually distinct. Provide `keywords`
per term so the enrichment LLM has anchors.

## Steps

1. **Create the taxonomy** — `agentbase_create_taxonomy { name }`.
2. **Add terms** — `agentbase_add_taxonomy_term`
   `{ taxonomy_id, facet: "platform", value: "AcmeCRM", keywords: ["acmecrm", "acme crm"] }`.
   Repeat for every term in every facet.
3. **Link taxonomy to the library** — `agentbase_update_library`
   `{ library_id, taxonomy_id, enrichment_model: "gemma3:12b" }`. The `enrichment_model`
   is the classifier LLM and must be available via a configured provider.
4. **Classify existing content** — `agentbase_re_enrich_source { source_id }` for each
   already-indexed source. (Sources indexed *after* the taxonomy is linked auto-classify.)
   Background job — poll `agentbase_get_source_status`.
5. **Review coverage** — `agentbase_get_taxonomy_coverage { taxonomy_id }` to see how
   content distributes across terms.
6. **Curate suggestions** — during enrichment the LLM may propose new terms. Review with
   `agentbase_list_taxonomy_suggestions { taxonomy_id, status: "pending" }`, then
   `agentbase_approve_taxonomy_suggestion` / `agentbase_reject_taxonomy_suggestion`.

## Notes

- Terms with no keywords classify poorly — always seed a few.
- A lopsided coverage distribution (everything lands under one term) usually means the
  facet is too coarse or terms overlap — refine and re-enrich.
- Once classified, filters become available for precise search — see agent-and-search.md.
