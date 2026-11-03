"""docs/OUTLOOK_BACKTEST.md and docs/figures/outlook_* from the saved outlook outputs."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, REPO_ROOT
from radar_lk.outlook.models import lgbm_frame

DOC = REPO_ROOT / "docs" / "OUTLOOK_BACKTEST.md"
FIG = REPO_ROOT / "docs" / "figures"
LABEL = {
    "persistence": "Persistence",
    "climatology": "Seasonal climatology",
    "glm": "NB GLM / logistic",
    "lightgbm": "LightGBM",
}
MODELS = list(LABEL)
TEST = "test (2025-26 origins)"
SELECT = "select (2024 origins)"
TEST_FROM = "2025-W01"
COLOR = {
    "climatology": "#2a78d6",
    "glm": "#eb6834",
    "lightgbm": "#1baf7a",
    "persistence": "#898781",
}
MARKER = {"climatology": "o", "glm": "s", "lightgbm": "^", "persistence": "D"}
INK, INK2, MUTED, GRID, AXIS, SURF = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb",
)  # fmt: skip


def md(df: pd.DataFrame, index: bool = False, fmt: str = "{:.3f}") -> str:
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else fmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def headline_h(cfg) -> list[int]:
    return [1, 2, cfg["L"] + 1, cfg["H"]]


def h_name(h: int, cfg) -> str:
    if h == cfg["L"] + 1:
        return f"h={h} (this week)"
    if h == cfg["H"]:
        return f"h={h} (next week)"
    return f"h={h}"


# ------------------------------------------------------------------ figures


def skill_figure(tr: pd.DataFrame, disease: str, path, cfg) -> None:
    plt = _plt()
    a = tr[(tr["scope"] == TEST) & (tr["disease"] == disease)]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=150)
    fig.patch.set_facecolor(SURF)
    for ax, col, ttl, ref in (
        (axes[0], "BSS vs persistence", "Brier skill vs persistence (higher is better)", 0.0),
        (axes[1], "MASE vs persistence", "MAE relative to persistence (lower is better)", 1.0),
    ):
        ax.set_facecolor(SURF)
        for m in ("climatology", "glm", "lightgbm"):
            g = a[a["model"] == m].sort_values("h")
            ax.plot(g["h"], g[col], color=COLOR[m], marker=MARKER[m], lw=2, ms=5, label=LABEL[m])
        ax.axhline(ref, color=MUTED, lw=1, ls="--")
        ax.axvline(cfg["L"] + 0.5, color=AXIS, lw=1, ls=":")
        _style(ax)
        ax.set_xlabel("horizon h (weeks after the latest reported week)", color=INK2, fontsize=8)
        ax.set_title(ttl, loc="left", color=INK, fontsize=10)
        ax.set_xticks(range(1, cfg["H"] + 1))
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK2)
    axes[1].text(cfg["L"] + 0.6, axes[1].get_ylim()[1], " now", color=INK2, fontsize=8, va="top")
    fig.suptitle(
        f"{disease}: skill by horizon, test origins 2025-26 (dashed = persistence)",
        x=0.01,
        ha="left",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def reliability_figure(fc: pd.DataFrame, disease: str, path, cfg) -> pd.DataFrame:
    plt = _plt()
    e = fc[
        (fc["disease"] == disease)
        & (fc["kind"] == "backtest")
        & (fc["origin_week"] >= TEST_FROM)
        & fc["elevated_obs"].notna()
    ]
    hs = headline_h(cfg)
    fig, axes = plt.subplots(1, len(hs), figsize=(12, 3.4), dpi=150, sharey=True)
    fig.patch.set_facecolor(SURF)
    bins = np.linspace(0, 1, 11)
    rows = []
    for ax, h in zip(axes, hs, strict=True):
        ax.set_facecolor(SURF)
        ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls="--")
        for m in ("climatology", "glm", "lightgbm"):
            g = e[(e["model"] == m) & (e["h"] == h)].dropna(subset=["p_elevated"])
            b = np.clip(np.digitize(g["p_elevated"], bins) - 1, 0, 9)
            r = g.groupby(b).agg(
                p=("p_elevated", "mean"), o=("elevated_obs", "mean"), n=("h", "size")
            )
            r = r[r["n"] >= 10]
            ax.plot(r["p"], r["o"], color=COLOR[m], marker=MARKER[m], lw=2, ms=5, label=LABEL[m])
            rows += [{"h": h, "model": m, "bin": i, **v} for i, v in r.to_dict("index").items()]
        _style(ax)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title(h_name(h, cfg), loc="left", color=INK, fontsize=9)
        ax.set_xlabel("forecast P(elevated)", color=INK2, fontsize=8)
    axes[0].set_ylabel("observed share elevated", color=INK2, fontsize=8)
    axes[0].legend(frameon=False, fontsize=7, labelcolor=INK2, loc="upper left")
    fig.suptitle(
        f"{disease}: reliability, test origins 2025-26 (bins with >= 10 forecasts)",
        x=0.01, ha="left", fontsize=11,
    )  # fmt: skip
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ explainability


def importance(live: dict, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gain importance and mean |contribution| (LightGBM pred_contrib = TreeSHAP) of the live
    models on their own training rows."""
    reg, cls = live["lgbm"]
    tr = live["train"]
    X = lgbm_frame(tr, cfg)
    if len(X) > 20000:
        X = X.sample(20000, random_state=0)
    out = []
    for name, m in (("count (Poisson)", reg), ("elevated (binary)", cls)):
        if m is None:
            continue
        gain = pd.Series(m.booster_.feature_importance("gain"), index=m.booster_.feature_name())
        contrib = m.predict(X, pred_contrib=True)
        shap = pd.Series(np.abs(contrib[:, :-1]).mean(0), index=m.booster_.feature_name())
        out.append(
            pd.DataFrame({"model": name, "gain %": 100 * gain / gain.sum(), "mean |SHAP|": shap})
            .sort_values("mean |SHAP|", ascending=False)
            .rename_axis("feature")
        )
    return out[0], out[1] if len(out) > 1 else pd.DataFrame()


def rain_lag(live: dict, cfg) -> pd.DataFrame:
    """Per rain lag k (weeks before the target week): model view (mean SHAP of rain_lk on the
    log-odds of 'elevated' when that week's rain was heavy, i.e. >= the district's 90th
    percentile of weekly rain) and data view (share elevated after heavy rain / share elevated
    otherwise, one row per district-target week)."""
    _, cls = live["lgbm"]
    tr = live["train"].copy()
    X = lgbm_frame(tr, cfg)
    contrib = cls.predict(X, pred_contrib=True)
    names = cls.booster_.feature_name()
    p90 = tr.groupby("area", observed=True)["rain_l2"].quantile(0.9)
    one = tr[tr["h"] == 1]
    rows = []
    for k in cfg["rain_lags"]:
        c = f"rain_l{k}"
        heavy = tr[c].to_numpy() >= p90.reindex(tr["area"]).to_numpy()
        s = contrib[:, names.index(c)]
        h1 = one[c].to_numpy() >= p90.reindex(one["area"]).to_numpy()
        e = one["elevated"].to_numpy()
        rows.append(
            {
                "rain lag (weeks before target)": k,
                "model: mean SHAP if heavy rain (log-odds)": float(s[heavy].mean()),
                "model: mean SHAP otherwise": float(s[~heavy].mean()),
                "data: share elevated after heavy rain %": 100 * float(e[h1].mean()),
                "data: share elevated otherwise %": 100 * float(e[~h1].mean()),
                "data: ratio": float(e[h1].mean() / e[~h1].mean()),
                "heavy-rain district-weeks": int(h1.sum()),
            }
        )
    return pd.DataFrame(rows)


def rain_figure(rl: pd.DataFrame, disease: str, path) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    k = rl["rain lag (weeks before target)"]
    for ax, col, ttl in (
        (axes[0], "model: mean SHAP if heavy rain (log-odds)",
         "Model: push on P(elevated) when that week was very wet"),
        (axes[1], "data: ratio", "Data: share elevated after a very wet week / otherwise"),
    ):  # fmt: skip
        ax.set_facecolor(SURF)
        ax.bar(k, rl[col], color="#1baf7a", width=0.6)
        ax.axhline(0 if "SHAP" in col else 1, color=MUTED, lw=1)
        _style(ax)
        ax.grid(axis="x", visible=False)
        ax.set_xticks(list(k))
        ax.set_xlabel("weeks between the rain and the target week", color=INK2, fontsize=8)
        ax.set_title(ttl, loc="left", color=INK, fontsize=9)
    fig.suptitle(
        f"{disease}: risk after heavy rain (very wet = district's own top 10% of weeks)",
        x=0.01, ha="left", fontsize=11,
    )  # fmt: skip
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


# ------------------------------------------------------------------ NDCU


def ndcu_check(fc: pd.DataFrame, cfg) -> pd.DataFrame:
    """Dengue 2026: forecast elevated (dashboard class model, p >= 0.5) vs NDCU district flags."""
    from radar_lk.radar.backtest import _concordance

    flags = pd.read_parquet(CLEAN_DIR / "ndcu_flags.parquet")
    n = flags.groupby(["district", "epi_week"]).size().rename("n_moh").reset_index()
    weeks = set(flags["epi_week"])
    d = fc[(fc["disease"] == "dengue") & (fc["target_year"] == 2026) & fc["observed"].notna()]
    d = d.assign(epi_week=d["target_week"].str[-2:].astype(int))
    d = d[d["epi_week"].isin(weeks)]
    rows = []
    for h in headline_h(cfg):
        g = d[(d["h"] == h) & d["dashboard_class"]]
        x = g[["area", "epi_week", "p_elevated", "elevated_obs"]].merge(
            n.rename(columns={"district": "area"}), on=["area", "epi_week"], how="left"
        )
        x["n_moh"] = x["n_moh"].fillna(0)
        model = g["model"].iloc[0] if len(g) else ""
        for thr in (1, 3):
            x["ndcu"] = x["n_moh"] >= thr
            for who, col in (
                ("forecast", x["p_elevated"] >= 0.5),
                ("observed", x["elevated_obs"] == 1),
            ):
                r = _concordance(x.assign(alert_shown=col), thr)
                r.pop("xcorr")
                rows.append({"h": h, "model": model if who == "forecast" else "observed (truth)",
                             "NDCU-positive": f">= {thr} MOH", **r})  # fmt: skip
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ document


def headline_table(tr: pd.DataFrame, disease: str, cfg) -> pd.DataFrame:
    a = tr[(tr["scope"] == TEST) & (tr["disease"] == disease) & tr["h"].isin(headline_h(cfg))]
    rows = []
    for m in MODELS:
        r = {"model": LABEL[m]}
        for h in headline_h(cfg):
            g = a[(a["model"] == m) & (a["h"] == h)].iloc[0]
            r[f"{h_name(h, cfg)} BSS"] = g["BSS vs persistence"]
            r[f"{h_name(h, cfg)} MASE"] = g["MASE vs persistence"]
            r[f"{h_name(h, cfg)} cov90 %"] = g["coverage90 %"]
        rows.append(r)
    return pd.DataFrame(rows)


def display_section(a: pd.DataFrame) -> list[str]:
    """Disclosed post-hoc display change: calibrated baseline probabilities (test origins)."""
    t = a[(a["scope"] == TEST) & a["model"].isin(["persistence", "climatology"])]
    w = t.pivot_table(index="h", columns="model", values=["Brier", "Brier (display)"])
    rows = pd.DataFrame(
        {
            "h": w.index,
            "persistence Brier (0/1, as evaluated)": w[("Brier", "persistence")].to_numpy(),
            "persistence Brier (calibrated display)": w[
                ("Brier (display)", "persistence")
            ].to_numpy(),
            "climatology Brier (as evaluated)": w[("Brier", "climatology")].to_numpy(),
            "climatology Brier (calibrated display)": w[
                ("Brier (display)", "climatology")
            ].to_numpy(),
        }
    )
    return [
        "### Baseline probabilities as displayed (post-hoc display change, disclosed)",
        "",
        "Persistence gives a 0/1 probability and climatology a frequency over one to four past "
        "years, so where they are the selected model the dashboard would print 0% or 100%. "
        "**After model selection and evaluation**, the displayed probability of these two "
        "baselines was changed to an empirical frequency estimated past-only (expanding window, "
        "per disease and horizon, from earlier forecasts whose target was already reported): "
        "persistence shows P(elevated at t+h | elevated status at t), Laplace-smoothed; "
        "climatology shows the district's own past frequency at that time of year, smoothed with "
        "two pseudo-weeks at the 20% base rate. The selected model at each horizon is unchanged, "
        "and every other number in this report (selection, BSS, reliability) still uses the "
        "probabilities as evaluated. Brier on the test origins (2025-26), lower is better:",
        "",
        md(rows),
        "",
    ]


def aci_section(a: pd.DataFrame, sel: pd.DataFrame, cfg) -> list[str]:
    """Static vs adaptive (ACI) count-interval coverage for the selected count models."""
    pick = sel.set_index("h")["selected count model"]
    rows = []
    for scope in ("2024-25 targets", "2026 targets", TEST):
        g = a[a["scope"] == scope]
        g = g[g["model"].to_numpy() == pick.reindex(g["h"]).to_numpy()]
        w = g["n"] / g["n"].sum()
        rows.append(
            {
                "scope (selected count models, all horizons)": scope,
                "n": int(g["n"].sum()),
                "80% static": float((g["coverage80 %"] * w).sum()),
                "80% ACI": float((g["coverage80 ACI %"] * w).sum()),
                "90% static": float((g["coverage90 %"] * w).sum()),
                "90% ACI": float((g["coverage90 ACI %"] * w).sum()),
                "90% width static": float((g["width90"] * w).sum()),
                "90% width ACI": float((g["width90 ACI"] * w).sum()),
            }
        )
    why = a["interval reason"].iloc[0]
    return [
        "### Count intervals: static split-conformal vs adaptive conformal (ACI)",
        "",
        "ACI (Gibbs & Candes 2021) keeps the same rolling pool of past-only scores but adapts "
        "the working miscoverage online: when a forecast's target is reported, the miscoverage "
        f"moves by gamma = {cfg['aci_gamma']} x (nominal - miss), per forecast, with gamma fixed "
        "a priori. The dashboard uses ACI only if it brings 2026 coverage closer to nominal "
        f"without moving 2024-25 coverage more than {cfg['aci_tolerance_pp']} points from "
        "nominal.",
        "",
        md(pd.DataFrame(rows), fmt="{:.1f}"),
        "",
        f"**{why}.**",
        "",
    ]


def write(cfg, fc: pd.DataFrame, tr: pd.DataFrame, lives: dict) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    L, H = cfg["L"], cfg["H"]
    out = [
        "# Outlook backtest",
        "",
        f"Generated {date.today()} by `python -m radar_lk.outlook.backtest`. Primary data: "
        "Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1, `extraction_valid` RDHS "
        "rows, weekly counts as first printed); rainfall, temperature and humidity: Open-Meteo "
        "(CC BY 4.0); external check: National Dengue Control Unit (NDCU) Weekly Dengue Update. "
        "This is the proposal's fallback after the NDCU MOH outlook was judged NO-GO: a "
        "district-level outlook, leptospirosis primary, dengue secondary, from one disease-"
        "agnostic engine. Outputs are population-level signals for planning, not predictions "
        "about any person.",
        "",
        "## Design: filling the publication gap",
        "",
        f"- The WER reports a week about **L = {L} weeks** after it ends (`publication_lag_weeks`, "
        "measured from the PDFs). Rainfall is observed in near real time. From the latest "
        f"reported week t (the origin) the outlook forecasts t+1 .. t+{H}: at the time of use "
        f"(about t+{L}) h = {L + 1} is **this week** and h = {H} **next week**; h = 1, 2 are the "
        "proposal's horizons (weeks already over but not yet reported).",
        "- Targets: (i) the weekly count; (ii) **elevated** = count >= that district's 80th "
        "percentile of its counts in the 104 weeks before t (past-only), floored at 1 case.",
        "- Features: counts y_t..y_t-3, 4- and 8-week means, same week last year, mean count of "
        "neighbouring districts at t (HDX polygons; Kalmunai adjacent to Ampara and Batticaloa by "
        "rule, `config/district_adjacency.csv`), reporting completeness at t, district, h, "
        "Fourier terms of the target's week of year, and weather relative to the TARGET week: "
        "rain at lags 2..8, the 4-week rain sum ending at lag 2, mean temperature and humidity "
        "at lags 2-4. Lag >= 2 is enforced in code (`features.weather_at`) and tested; for "
        "targets up to now + 2 all of it is observed at the time of use.",
        "- Models (fixed settings, nothing tuned on test data): persistence; seasonal "
        "climatology (district mean / elevated frequency for the target's week of year +-1 in "
        "earlier years); NB GLM (counts) / L2 logistic regression (class); LightGBM "
        "(Poisson / binary).",
        "- Rolling origin, expanding window: test origins 2024-W01 to the latest week, refit "
        "every 4 weeks on rows whose target week is <= the refit origin. 2023 origins are "
        "forecast too but only to fill the calibration pools.",
        "- Uncertainty: counts, rolling split-conformal on past-only residuals normalised by "
        "sqrt(pred + 1), pool = the last 52 origins with observed targets, same model and "
        "horizon (80% and 90%). Probabilities (GLM and LightGBM): inductive **Venn-Abers** "
        "(`venn-abers` package) on the same pool; `p_elevated` is the calibrated probability "
        "and [`p_lo`, `p_hi`] its Venn-Abers range. Baselines keep their own probability for "
        "evaluation; the dashboard shows them calibrated (see 'Baseline probabilities as "
        "displayed').",
        "- Skill: MASE = MAE / persistence MAE on the same rows; BSS = 1 - Brier / reference "
        "Brier; recall and precision at p >= 0.5. Every model is scored on the same "
        "district-weeks.",
        "",
    ]
    for d in cfg["diseases"]:
        a = tr[tr["disease"] == d]
        sk = FIG / f"outlook_{d}_skill.png"
        rel = FIG / f"outlook_{d}_reliability.png"
        skill_figure(tr, d, sk, cfg)
        reliability_figure(fc, d, rel, cfg)
        sel = a[a["scope"] == TEST].drop_duplicates("h")[
            ["h", "selected count model", "count selection reason", "selected probability model",
             "probability selection reason"]
        ]  # fmt: skip
        n_eval = fc[(fc["disease"] == d) & (fc["kind"] == "backtest")]["origin_week"]
        out += [
            f"## {d.capitalize()}",
            "",
            f"Backtest origins {n_eval.min()} to {n_eval.max()} ({n_eval.nunique()} origins x 26 "
            f"districts x up to {H} horizons). **Models are selected on 2024 origins only; every "
            "number below is on the untouched 2025-26 origins** unless the heading says "
            "otherwise.",
            "",
            "### Headline (test origins 2025-26): Brier skill vs persistence (BSS), MASE vs "
            "persistence, 90% interval coverage (static split-conformal)",
            "",
            md(headline_table(tr, d, cfg), fmt="{:.2f}"),
            "",
            f"![skill]({sk.relative_to(DOC.parent).as_posix()})",
            "",
            "### Model selection (2024 origins) -> what the dashboard shows",
            "",
            "Candidates: persistence, seasonal climatology, NB GLM / logistic, LightGBM. Counts "
            "are selected by MASE, P(elevated) by Brier, on 2024 origins only; any model within "
            "0.01 of the best is a tie and the simplest of the tied models is kept (persistence < "
            "climatology < GLM < LightGBM). This replaces the earlier rule (LightGBM unless "
            "persistence beats it), which looked at all years and ignored the GLM.",
            "",
            md(sel.assign(**{c: sel[c].map(LABEL) for c in ("selected count model",
                                                            "selected probability model")})),
            "",
        ]  # fmt: skip
        ts = a[a["scope"] == TEST]
        pick = sel.set_index("h")
        sc = ts[ts["model"].to_numpy() == pick.reindex(ts["h"])["selected count model"].to_numpy()]
        sp = ts[
            ts["model"].to_numpy() == pick.reindex(ts["h"])["selected probability model"].to_numpy()
        ]
        lg = ts[ts["model"] == "lightgbm"].set_index("h")
        cmp_ = pd.DataFrame(
            {
                "h": sc["h"].to_numpy(),
                "selected count model": sc["model"].map(LABEL).to_numpy(),
                "its MASE (test)": sc["MASE vs persistence"].to_numpy(),
                "LightGBM MASE (test)": lg.loc[sc["h"], "MASE vs persistence"].to_numpy(),
            }
        ).merge(
            pd.DataFrame(
                {
                    "h": sp["h"].to_numpy(),
                    "selected probability model": sp["model"].map(LABEL).to_numpy(),
                    "its BSS vs persistence (test)": sp["BSS vs persistence"].to_numpy(),
                    "its BSS vs climatology (test)": sp["BSS vs climatology"].to_numpy(),
                    "LightGBM BSS vs persistence (test)": lg.loc[
                        sp["h"], "BSS vs persistence"
                    ].to_numpy(),
                }
            ),
            on="h",
        )
        beat = (cmp_["its MASE (test)"] < 1).all() and (
            cmp_["its BSS vs persistence (test)"] > 0
        ).all()
        out += [
            "How the selected models do on the untouched test (2025-26 origins):",
            "",
            md(cmp_, fmt="{:.3f}"),
            "",
            "The selected models beat persistence on both targets at every horizon on the test."
            if beat
            else "**At some horizons a selected model does not beat persistence on the test "
            "(MASE >= 1 or BSS <= 0); see the table.**",
            "",
        ]
        cnt = ts[
            ["model", "h", "n", "MAE", "RMSE", "MASE vs persistence", "coverage80 %", "width80",
             "coverage90 %", "width90", "coverage80 ACI %", "coverage90 ACI %", "width90 ACI"]
        ]  # fmt: skip
        cls = ts[
            ["model", "h", "n_class", "base rate %", "Brier", "BSS vs persistence",
             "BSS vs climatology", "recall", "precision", "AUROC", "PR-AUC", "mean p range"]
        ]  # fmt: skip
        out += [
            "### Counts, every horizon (test)",
            "",
            md(cnt.assign(model=cnt["model"].map(LABEL)).sort_values(["h", "model"])),
            "",
            "### Elevated, every horizon (test)",
            "",
            md(cls.assign(model=cls["model"].map(LABEL)).sort_values(["h", "model"])),
            "",
            f"![reliability]({rel.relative_to(DOC.parent).as_posix()})",
            "",
            "`mean p range` is the width of the Venn-Abers calibration range. It is narrow "
            "because the calibration pool is large and it describes calibration uncertainty "
            "only; outbreak uncertainty is carried by the count interval. The dashboard shows "
            "the range only in a tooltip, labelled 'calibration range'.",
            "",
        ]
        out += display_section(a)
        out += aci_section(a, sel, cfg)
        y26 = a[(a["scope"] == "2026 targets") & a["h"].isin(headline_h(cfg))]
        out += [
            "### 2026 separately (targets in 2026)",
            "",
            md(
                y26.assign(model=y26["model"].map(LABEL))[
                    [
                        "model",
                        "h",
                        "n",
                        "MASE vs persistence",
                        "BSS vs persistence",
                        "BSS vs climatology",
                        "AUROC",
                        "coverage90 %",
                        "coverage90 ACI %",
                    ]
                ].sort_values(["h", "model"])
            ),  # fmt: skip
            "",
        ]
        live = lives.get(d, {})
        if live.get("lgbm"):
            imp_c, imp_b = importance(live, cfg)
            out += [
                "### What drives LightGBM (live models, on their training rows)",
                "",
                "Mean |SHAP| is LightGBM's own TreeSHAP (`pred_contrib`), on the log scale of "
                "the model (log count / log-odds). Gain = share of split gain.",
                "",
                "Elevated (binary), top 12:",
                "",
                md(imp_b.head(12).drop(columns="model"), index=True),
                "",
                "Count (Poisson), top 8:",
                "",
                md(imp_c.head(8).drop(columns="model"), index=True),
                "",
            ]
            rl = rain_lag(live, cfg)
            rf = FIG / f"outlook_{d}_rain_lag.png"
            rain_figure(rl, d, rf)
            km = int(
                rl.loc[
                    rl["model: mean SHAP if heavy rain (log-odds)"].idxmax(),
                    "rain lag (weeks before target)",
                ]
            )
            kd = int(rl.loc[rl["data: ratio"].idxmax(), "rain lag (weeks before target)"])
            out += [
                "### Rainfall lag",
                "",
                md(rl, fmt="{:.2f}"),
                "",
                f"![rain lag]({rf.relative_to(DOC.parent).as_posix()})",
                "",
                f"**Finding: {d} risk rises about {km} weeks after a very wet week in the "
                f"model (largest push on P(elevated)); in the raw data the excess is largest "
                f"{kd} weeks after.** Association, not proof of cause: wet weeks also cluster "
                "in the monsoon seasons the Fourier terms describe.",
                "",
            ]
        lv = fc[
            (fc["disease"] == d)
            & (fc["kind"] == "live")
            & fc["dashboard_class"]
            & fc["h"].isin([L + 1, H])
        ]
        if len(lv):
            top = lv.sort_values("p_elevated", ascending=False).head(10)
            out += [
                f"### Live outlook (origin {lv['origin_week'].iloc[0]}, as of "
                f"{lv['as_of'].iloc[0]}): highest P(elevated) for this week and next week",
                "",
                md(
                    top[
                        [
                            "area",
                            "target_week",
                            "h",
                            "model",
                            "p_elevated",
                            "p_lo",
                            "p_hi",
                            "pred_count",
                            "lo90",
                            "hi90",
                            "elevated_threshold",
                        ]
                    ],
                    fmt="{:.2f}",
                ),  # fmt: skip
                "",
            ]
    if "dengue" in cfg["diseases"]:
        nd = ndcu_check(fc, cfg)
        out += [
            "## Dengue: 2026 forecasts vs NDCU district flags",
            "",
            "Forecast elevated (dashboard class model at that horizon, P >= 0.5) vs NDCU: a "
            "district is NDCU-positive when >= 1 (or >= 3) of its MOH areas is on that week's "
            "high-risk list. The row 'observed (truth)' compares the observed elevated flag "
            "itself, so it shows how far the two definitions can agree at best: NDCU flags "
            "absolute MOH burden, 'elevated' is relative to the district's own past.",
            "",
            md(
                nd[
                    [
                        "h",
                        "model",
                        "NDCU-positive",
                        "district-weeks",
                        "both",
                        "agreement %",
                        "kappa",
                        "radar sensitivity vs NDCU %",
                        "share of radar alerts with NDCU flag %",
                        "NDCU onsets",
                        "onsets with a radar alert within +-4 wk",
                    ]
                ].rename(
                    columns={
                        "radar sensitivity vs NDCU %": "share of NDCU flags forecast %",
                        "share of radar alerts with NDCU flag %": "share of forecasts flagged %",
                        "onsets with a radar alert within +-4 wk": "onsets forecast within +-4 wk",
                    }
                ),
                fmt="{:.1f}",
            ),  # fmt: skip
            "",
        ]
    out += [
        "## Limitations",
        "",
        "- 2.6 seasons of training history at the first test origin (2022-2023), 4.6 at the last; "
        "the seasonal terms and the climatology baseline rest on few years.",
        "- Weather is one Open-Meteo point per district (centroid), not an areal average; "
        "Kalmunai uses its town point.",
        "- The first-printed weekly counts are under-notified and late reports raise them later; "
        "the target is what a Regional Epidemiologist would have seen, not true incidence.",
        "- Venn-Abers and conformal pools pool all districts: coverage holds on average, not "
        "for every district.",
        "- Rows where any model has no forecast are left out of the comparison; all models are "
        "scored on the same district-weeks.",
        "",
    ]
    DOC.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {DOC}")
