# Initial Sprint 1 source catalogue

The experimental `web` retrieval mode treats this list as preferred sources, then allows wider discovery. It also recognises `.gov`, `.gov.uk` and `.gov.au` namespaces using the registries' eligibility policies. Unknown publishers remain leads and cannot independently drive verdicts. [Source policy, registry references and limitations](../../backend/app/pipeline/evidence_retrieval/WEB_RETRIEVAL.md).

The runtime allowlist is `backend/app/pipeline/evidence_retrieval/sources.py`.
This deliberately limited English prototype catalogue was assembled on 7 September
2026. Inclusion is a search-scope decision, not a guarantee that every statement is
true, current, independent, or relevant. It is not a completed source-credibility audit.

| Domain family | Type | Reason and coverage | Limits |
| --- | --- | --- | --- |
| gov.sg | government | Singapore agency publications, policy and history | Agency statements may need independent corroboration; not every agency covers every topic |
| mfa.go.th | government | Thai Ministry of Foreign Affairs and its document host; added 8 September 2026 | Check publication/effective dates and entry category; older pages can describe superseded schemes |
| thaiembassy.org | government | Royal Thai Embassy pages; added 8 September 2026 | Apply only to the stated entry scheme and traveller eligibility; similarly named commercial domains are not included |
| nasa.gov | government | Space and astronomy primary material | Historic and educational material may not address the exact claim |
| snopes.com | fact_check | Published checks of circulating claims | Reviews can repeat false claims; extraction must retain the verdict and context |
| fullfact.org | fact_check | Public claims and viral-content checks | Mainly UK coverage; conclusions depend on the reviewed wording/date |
| factcheck.org | fact_check | US public-claim checks | Mainly US coverage; limited coverage of Singapore claims |
| reuters.com | news | Reported evidence and published fact checks | Ordinary reporting is classified as news; access may be restricted |
| apnews.com | news | Reported evidence and published fact checks | Reports may quote disputed claims or share the same underlying source |
| channelnewsasia.com | news | Singapore and regional reporting | Related reports may not independently establish the specific claim |
| nus.edu.sg | academic | University research and historical/legal materials | A university hostname does not imply every page is peer reviewed |

Matching accepts the named domain and actual subdomains, not lookalike suffixes.
The precise hostname is used as publisher for the government domain family.
Broader coverage should be added with per-source review and retrieval evaluation.

References used for the initial scope include [Singapore government trusted sites](https://www.gov.sg/trusted-sites/),
[Full Fact's description of its work](https://fullfact.org/about/) and
[FactCheck.org's mission](https://www.factcheck.org/spindetectors/about/).
Live provider checks returned Snopes, NASA, NLB and NUS pages; that confirms sample
retrievability, not a comprehensive quality or accessibility review of those domains.

The Thai domain additions were checked against the official
[Budapest embassy's visa-exemption conditions](https://budapest.thaiembassy.org/en/publicservice/tourist-visa-exemption?menu=698b49659c095935352c7913&page=6984988f8adfb526cf0c38f3)
and [Doha embassy's entry-scheme guidance](https://doha.thaiembassy.org/en/publicservice/tourist-visa-exemption-visa-on-arrival?page=5d7e6a3c15e39c032c006dba),
including their links to the Ministry of Foreign Affairs. This expands source
coverage, not a hard-coded answer to the Phuket cash claim. It does not establish
the personal entry requirements of a traveller whose passport, date and entry
category are unknown.
