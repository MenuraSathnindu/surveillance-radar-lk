"""Data & methods: pipeline, extraction quality, sources and licences, limitations, scope."""

from __future__ import annotations

import streamlit as st

import common

st.title("Data & methods")

st.subheader("Pipeline")
st.graphviz_chart(
    """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#F3F2EE", color="#C3C2B7",
        fontname="Helvetica", fontsize=11];
  edge [color="#898781"];
  dl [label="Download\\nWER PDFs (robots.txt,\\nrate-limited, kept)"];
  parse [label="Parse Table 1\\n(pdfplumber)"];
  val [label="Validate\\n(sums, cumulatives,\\nscrambled / stale columns)"];
  harm [label="Harmonise\\n(canonical week,\\nRDHS names)"];
  store [label="Store\\nParquet + DuckDB"];
  radar [label="Radar\\nEARS C2 + NB-GLM\\n(tiers, gating)"];
  outlook [label="Outlook\\nGLM / LightGBM + rain\\n(conformal intervals)"];
  ui [label="Dashboard\\n+ weekly briefs"];
  wx [label="Open-Meteo\\nweekly weather"];
  dl -> parse -> val -> harm -> store -> radar -> ui;
  store -> outlook -> ui; wx -> outlook;
  rev [label="Review queue\\n(never shown)", fillcolor="#FFFFFF", style="rounded,dashed"];
  val -> rev [style=dashed];
}
""",
    use_container_width=True,
)
st.caption(
    "One-way batch pipeline, run with `python -m radar_lk.pipeline --all`. The dashboard reads "
    "only its outputs (data/clean), never the PDFs. No language model reads PDFs or produces "
    "numbers."
)

st.subheader("Extraction quality")
for lab in (
    "Hand-check accuracy",
    "Cross-extractor agreement",
    "`extraction_valid`, all years",
    "`extraction_valid` by year",
    "Publication lag",
):
    common.claim(lab)

st.markdown("**The source tables themselves are sometimes scrambled.**")
c1, c2 = st.columns([1, 3])
with c1:
    st.image(
        str(common.ROOT / "docs" / "figures" / "source_scrambled_example.png"),
        caption="WER Vol 53 No 15 (2026-W14), Table 1, dengue: Colombo 9 and Matale 256 where "
        "the weeks around read about 300 and 20.",
    )
with c2:
    common.claim("Source-table scrambling")

st.subheader("Data sources and licences")
st.markdown(
    """
| Source | What | Licence / terms |
|---|---|---|
| Epidemiology Unit, Ministry of Health, Sri Lanka | Weekly Epidemiological Report (WER) Table 1: weekly notified cases by RDHS for 14 diseases, completeness C** | Public reports; primary data source, attributed on every page |
| National Dengue Control Unit, Ministry of Health | Weekly Dengue Update: high-risk MOH lists (2026) | Public reports; external check only |
| Open-Meteo | Daily rainfall, temperature, humidity at one point per district, aggregated to weeks | CC BY 4.0 |
| OCHA HDX COD-AB (Survey Department of Sri Lanka) | Admin-2 district boundaries (simplified in data/geo) | CC BY-IGO |

All data are public, aggregated weekly counts by area. No personal data.
"""
)

st.subheader("Limitations")
st.markdown(
    """
- **Under-notification.** WER counts are notified cases as first printed; true incidence is
  higher. Every signal is relative to the district's own history, never a measure of incidence.
- **Publication lag.** A week appears in the WER about two months after it ends, so radar signals
  describe weeks already past; the outlook estimates the weeks not yet reported.
- **Post-COVID baseline.** Baselines start in 2022, so seasonal terms rest on one to four seasons.
- **Pooled vs per-disease false alerts.** The two-tier radar's false-alert rate (3.8 per 100
  district-weeks) is pooled; dengue (9.3) and leptospirosis (7.3) are higher on their own.
- **Zero adoption margin for the tiers.** The two-tier radar was adopted with a median replay gain
  of exactly 0 weeks against the rule used today; one event moving would flip the decision.
- **Dengue 2026.** The 2026 dengue epidemic is outside anything in the training years; the
  outlook's intervals were too narrow in 2026 (see the Outlook page).
- **Weather** is one Open-Meteo point per district (Kalmunai: its town point), not an areal mean.
"""
)

st.subheader("Scope: non-clinical")
st.markdown(
    "Population-level signals for planning and investigation by Regional Epidemiologists. "
    "No clinical content: no diagnosis, treatment or prophylaxis advice, and nothing about "
    "individuals. Every alert is a signal for investigation and shows its track record."
)
