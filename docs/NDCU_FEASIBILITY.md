# NDCU feasibility: dengue MOH high-risk outlook

Generated 2026-11-02 06:50 UTC by `python -m radar_lk.ingest.parse_ndcu`. Primary data: National Dengue Control Unit, Ministry of Health, Sri Lanka (Weekly Dengue Update, `www.dengue.health.gov.lk/weekly-report/`).

## Verdict: **NO-GO**

| criterion | required | measured | met |
|---|---|---|---|
| consecutive weeks with a parseable high-risk list | >= 100 | 43 | **no** |
| MOH names mapped through the crosswalk | >= 90% | 98.8% (see caveat) | yes |
| distinct MOH areas ever flagged | >= 30 | 248 | yes |

**The binding failure is history length.** The NDCU site publishes weekly updates for 2026 Weeks 1-43 only; there is nothing from 2023-2025 on the weekly archive (3 pages, 20 per page), the publications page, or the daily-report page. 43 consecutive weeks cannot become 100. Without history there is no way to train or backtest a rolling-origin model of the flag, so the outlook falls back to the **district-level leptospirosis outlook from WER** (already parsed, 2022-2026) as planned. Older NDCU PDFs may exist elsewhere (e.g. a ReliefWeb mirror); that was **not** fetched because it needs your approval.

## 1. Source and coverage

- Archive: `https://www.dengue.health.gov.lk/weekly-report/` and `/page/2/`, `/page/3/` (robots.txt allows them; fetched with the polite downloader, 2 s delay). 43 PDFs downloaded, all dated 2026.
- Parsed: **43** of 43; failed: **0**.
- Parsed issues whose high-risk list did not match the count the issue states about itself: **0**.

| year | issues parsed | weeks | missing weeks | parseable high-risk list |
|---|---|---|---|---|
| 2026 | 43 | 1..43 | none | 43 |

Longest consecutive run of weeks with a parseable list: **43** (2025-12-29 to 2026-10-25).

A list is *parseable* when the number of MOH areas read from Table 2 equals the number the issue states in its own text, every area sits under a district heading, and the week passes the weekday and printed-week checks.

## 2. MOH names

- 258 distinct (district, printed name) pairs over 2800 flag rows.
- Mapped through `config/moh_crosswalk.csv`: **98.8%** of flag rows (98.1% of distinct names). Of the flag rows, **1.9%** map through a hand-curated crosswalk row; the rest map through rows seeded from NDCU's own spellings (`source=ndcu_seed`).
- **Caveat on that number.** The repository has no independent list of the 364 MOH areas, so the crosswalk was seeded from the names NDCU prints (spelling tidied: one space, space before a bracket) under the district heading they appear in. That makes names consistent across weeks and catches a name appearing under two districts, but it does not prove the names match the official MOH list used by anyone else. A 100% here is internal consistency, not external validation.
- Unmapped: 5: Galle/Katuwana, Galle/Tangalle, Hambantota/Katuwana, Hambantota/Tangalle, Matara/Katuwana.
- Names printed under more than one district (left unmapped, not resolved): **2**: Katuwana: Galle (1 wk), Hambantota (14 wk), Matara (2 wk); Tangalle: Galle (1 wk), Hambantota (17 wk). These are source inconsistencies in the district heading above the name, or a wrong heading assignment in my reading of a column break; either way they cannot be mapped without an authoritative list.
- Likely spelling variants of the same area that were **not** merged (different spellings, same district): 13: Ampara: Dehiattakandiya / Dehiyattakandiya; Batticaloa: Chenkaladay / Chenkalady; Colombo: Kahathuduwa / Kahatuduwa; Gampaha: Aththanagalla / Attanagalla; Hambantota: Angunukolapelas / Angunukolapelassa; Hambantota: Weeraketiya / Weereketiya; Jaffna: Telippalai / Tellippalai; Kalmunai: Akkaraipathu / Akkaraipattu; Kalutara: Banadaragama / Bandaragama; Kalutara: Payagala / Pyagala; Ratnapura: Goadakawela / Godakawela; Ratnapura: Rathnapura MC / Ratnapura MC; Ratnapura: Udawalawa / Udawalwa. Only spellings that normalise identically (case, spaces, hyphens) are merged, so the distinct-area counts below can be slightly too high.

## 3. Flag statistics (parseable weeks only)

- Distinct MOH areas ever flagged: **248** of 364 MOH areas (WER Vol 53 No 1: "all 364 Medical Officer of Health (MOH) divisions").
- Areas flagged per week: min 28, median 46, max 175 (12.6% of 364 in a median week).
- **Flag base rate** = flagged MOH-weeks / (364 MOH x 43 parseable weeks) = **17.9%**.
- Persistence (what a 1-week-ahead baseline would score): P(flagged next week | flagged now) = **78%**; P(newly flagged next week | not flagged now) = **4.5%**.

## 4. District weekly counts (Table 1)

- 1114 district-week rows from 43 issues; the 26 districts add to the printed Total in 39 of 43 issues.
- Columns kept: this week and last week for 2026 (an asterisk marks a revised figure), the same weeks of 2025, and the two year-to-date totals. They are in `data/clean/ndcu_districts.parquet`; the flags are in `data/clean/ndcu_flags.parquet`.

## 5. What would make this a GO

At least 100 consecutive weekly lists, i.e. issues back to about Nov 2024 or earlier, from NDCU or a faithful mirror. The parser already handles the 2026 layout; older layouts would need the same self-checks (stated count vs parsed count) before being trusted. Until then the dengue MOH outlook is not buildable with a defensible backtest, and `docs/PLAN.md` switches to the leptospirosis fallback.
