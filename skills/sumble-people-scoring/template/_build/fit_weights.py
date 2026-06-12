"""Stage 3b — fit the factor weights to the gold set (regularized).

Runs AFTER build_config.py. Reads config.json (default weights = policy
priors) plus data.csv (with `is_icp_gold`), and nudges ONLY the top-level
factor blend (jf / seniority / skills / 1P signals) toward better separation
of the gold people — deliberately a little, not a lot. The per-JF ranges are
FROZEN: that's where overfitting would otherwise live, exactly like the
frozen within-category weights in the account-scoring fit.

Anti-overfit design (same machinery as sumble-account-scoring fit_weights.py):
  * Low DOF — only the 3-6 factor weights move.
  * Shrinkage to the priors — objective = AUC(gold) - lam * ||w - w0||^2.
  * Box bounds — no weight drifts more than WEIGHT_BAND points from default.
  * K-fold CV picks lam on held-out gold via the 1-SE rule over PAIRED
    per-fold gains vs the defaults.
  * Adopt-only-if-it-generalizes — the fit replaces the priors only when the
    mean held-out AUC gain clears both an absolute floor and one standard
    error of the per-fold gains.
  * Small-gold guard — fewer than MIN_GOLD_FOR_FIT gold rows -> keep priors.

Deterministic: stratified round-robin folds over person_id (no RNG) +
derivative-free coordinate ascent. Same config + same data.csv -> same fit.

The fitted weights land in config.json as each weight's `current` value (the
`default` stays the prior, so the app's sliders show both), plus a
`_weight_fit` audit block; a report goes to _raw/_weight_fit_report.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

# --- Policy constants (fixed; the agent does not pick these per run) ----------
MIN_GOLD_FOR_FIT = 20
MIN_NONGOLD_FOR_FIT = 40
MAX_NONGOLD_FIT = 5000
N_FOLDS = 5
WEIGHT_BAND = 20.0  # a factor weight may move +/- this many points
LAMBDA_GRID = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
ADOPT_FLOOR_AUC = 0.002
ADOPT_SE_MULT = 1.0
N_SWEEPS = 8
STEP_POINTS = [-10.0, -5.0, -2.5, -1.25, 1.25, 2.5, 5.0, 10.0]


def _f(val: object, default: float = 0.0) -> float:
    if val in (None, "", "null"):
        return default
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# --- Per-row factor scores (the app/score_leads formula; weights factored out) --


def factor_scores(row: dict, config: dict) -> dict[str, float]:
    sen = config.get("seniority", {})
    rank = _f(row.get(sen.get("rank_column", "job_level_rank")))
    max_rank = _f(row.get(sen.get("max_rank_column", "max_job_level_rank")))
    sen_frac = (rank / max_rank) if max_rank > 0 else 0.0

    jfr_all = config.get("job_function_ranges", {}) or {}
    default_rng = config.get("default_jf_range", {}) or {"min": 0.5, "max": 0.85}
    jf_slug = (row.get("job_function_slug") or "").strip()
    rng = jfr_all.get(jf_slug, default_rng)
    jf_score = _f(rng.get("min")) + (_f(rng.get("max")) - _f(rng.get("min"))) * sen_frac

    cap = config.get("skill_cap", 5) or 5
    skill_score = min(_f(row.get("skill_count")), cap) / cap

    out = {"jf": jf_score, "seniority": sen_frac, "skills": skill_score}
    for sig in config.get("one_p_signals", []) or []:
        key = sig.get("weight_key") or f"1p_{sig.get('key')}"
        out[key] = _f(row.get(sig.get("norm_column") or f"{sig.get('key')}_norm"))
    return out


def score_rows(f_rows: list[dict[str, float]], weights: dict[str, float]) -> list[float]:
    return [
        sum((weights.get(k, 0.0) / 100.0) * v for k, v in fs.items()) for fs in f_rows
    ]


# --- Metrics (identical to the account-scoring fit) -----------------------------


def auc(scores: list[float], labels: list[int], idxs: list[int]) -> float:
    """Rank-based AUC (Mann-Whitney) over the given row indices, tie-aware."""
    order = sorted(idxs, key=lambda i: scores[i])
    ranks: dict[int, float] = {}
    j = 0
    n = len(order)
    while j < n:
        k = j
        while k + 1 < n and scores[order[k + 1]] == scores[order[j]]:
            k += 1
        avg = (j + k) / 2.0 + 1.0
        for m in range(j, k + 1):
            ranks[order[m]] = avg
        j = k + 1
    n_pos = sum(1 for i in idxs if labels[i] == 1)
    n_neg = len(idxs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    sum_pos = sum(ranks[i] for i in idxs if labels[i] == 1)
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def lift_at_decile(scores: list[float], labels: list[int]) -> float:
    n = len(scores)
    total_gold = sum(labels)
    if n == 0 or total_gold == 0:
        return 0.0
    order = sorted(range(n), key=lambda i: scores[i], reverse=True)
    k = max(1, int(0.1 * n))
    top_gold = sum(labels[i] for i in order[:k])
    baseline = total_gold / n
    return (top_gold / k) / baseline if baseline > 0 else 0.0


# --- Optimizer -------------------------------------------------------------------


def _shrink(weights: dict[str, float], w0: dict[str, float]) -> float:
    return sum(((v - w0[k]) / 100.0) ** 2 for k, v in weights.items())


def _renorm_group(
    vals: dict[str, float], key: str, new_v: float, boxes: dict[str, tuple[float, float]]
) -> dict[str, float]:
    """Set vals[key]=new_v, spread the remainder proportionally, water-fill to
    the boxes so the group sums to 100 (when feasible)."""
    keys = list(vals.keys())
    if len(keys) == 1:
        return {keys[0]: 100.0}
    lo, hi = boxes[key]
    new_v = max(lo, min(hi, new_v))
    others = [k for k in keys if k != key]
    other_sum = sum(vals[k] for k in others)
    remaining = 100.0 - new_v
    out = {key: new_v}
    if other_sum <= 0:
        share = remaining / len(others)
        for k in others:
            out[k] = share
    else:
        for k in others:
            out[k] = remaining * vals[k] / other_sum
    for _ in range(8):
        for k in others:
            blo, bhi = boxes[k]
            out[k] = max(blo, min(bhi, out[k]))
        residual = remaining - sum(out[k] for k in others)
        if abs(residual) < 1e-9:
            break
        free = [
            k
            for k in others
            if (residual > 0 and out[k] < boxes[k][1] - 1e-12)
            or (residual < 0 and out[k] > boxes[k][0] + 1e-12)
        ]
        if not free:
            break
        share = residual / len(free)
        for k in free:
            out[k] += share
    return out


def optimize(
    f_rows: list[dict[str, float]],
    labels: list[int],
    train_idxs: list[int],
    w0: dict[str, float],
    boxes: dict[str, tuple[float, float]],
    lam: float,
) -> dict[str, float]:
    weights = dict(w0)

    def obj(w: dict[str, float]) -> float:
        sc = score_rows(f_rows, w)
        return auc(sc, labels, train_idxs) - lam * _shrink(w, w0)

    best = obj(weights)
    for _ in range(N_SWEEPS):
        improved = False
        for delta in STEP_POINTS:
            for k in weights:
                trial = _renorm_group(weights, k, weights[k] + delta, boxes)
                val = obj(trial)
                if val > best + 1e-12:
                    best, weights, improved = val, trial, True
        if not improved:
            break
    return weights


# --- Cross-validation -------------------------------------------------------------


def stratified_folds(rows: list[dict], labels: list[int]) -> list[int]:
    """Deterministic stratified round-robin over person_id — no RNG."""
    fold = [0] * len(rows)
    for lab in (1, 0):
        members = [i for i in range(len(rows)) if labels[i] == lab]
        members.sort(key=lambda i: str(rows[i].get("person_id") or i))
        for pos, i in enumerate(members):
            fold[i] = pos % N_FOLDS
    return fold


def cv_fold_aucs(
    f_rows: list[dict[str, float]],
    labels: list[int],
    folds: list[int],
    w0: dict[str, float],
    boxes: dict[str, tuple[float, float]],
    lam: float,
    fit: bool,
) -> dict[int, float]:
    out: dict[int, float] = {}
    for f in range(N_FOLDS):
        train = [i for i in range(len(f_rows)) if folds[i] != f]
        held = [i for i in range(len(f_rows)) if folds[i] == f]
        n_pos = sum(labels[i] for i in held)
        if not held or n_pos == 0 or n_pos == len(held):
            continue
        w = optimize(f_rows, labels, train, w0, boxes, lam) if fit else w0
        scores = score_rows(f_rows, w)
        out[f] = auc(scores, labels, held)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _se(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var / len(xs))


# --- Main --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit factor weights to gold (regularized).")
    ap.add_argument("--raw", required=True, help="absolute path to the _raw directory")
    args = ap.parse_args()
    raw = Path(args.raw).resolve()
    out_root = raw.parent
    config_path = out_root / "config.json"
    data_path = out_root / "data.csv"
    report_path = raw / "_weight_fit_report.json"

    def write_report(status: str, extra: dict | None = None) -> None:
        report_path.write_text(json.dumps({"status": status, **(extra or {})}, indent=2))
        print(f"[fit] {status}")

    if not config_path.exists() or not data_path.exists():
        write_report("skipped_missing_inputs")
        return
    config: dict[str, Any] = json.loads(config_path.read_text())
    with data_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or "is_icp_gold" not in rows[0]:
        write_report("skipped_no_gold_column")
        return

    labels = [1 if int(_f(r.get("is_icp_gold"))) == 1 else 0 for r in rows]
    n_gold, n_nongold = sum(labels), len(labels) - sum(labels)
    if n_gold < MIN_GOLD_FOR_FIT or n_nongold < MIN_NONGOLD_FOR_FIT:
        write_report(
            "skipped_small_gold",
            {
                "n_gold": n_gold,
                "n_nongold": n_nongold,
                "min_gold": MIN_GOLD_FOR_FIT,
                "note": "too few gold — kept priors",
            },
        )
        return

    weights_cfg = config.get("weights") or {}
    w0 = {k: _f(v.get("default")) for k, v in weights_cfg.items()}
    tot = sum(w0.values()) or 1.0
    w0 = {k: 100.0 * v / tot for k, v in w0.items()}
    if len(w0) < 2:
        write_report("skipped_single_factor")
        return
    boxes = {
        k: (max(0.0, v - WEIGHT_BAND), min(100.0, v + WEIGHT_BAND)) for k, v in w0.items()
    }

    f_rows = [factor_scores(r, config) for r in rows]

    gold_idx = [i for i, lab in enumerate(labels) if lab == 1]
    non_idx = [i for i, lab in enumerate(labels) if lab == 0]
    if len(non_idx) > MAX_NONGOLD_FIT:
        non_sorted = sorted(non_idx, key=lambda i: str(rows[i].get("person_id") or i))
        stride = len(non_sorted) / MAX_NONGOLD_FIT
        non_idx = [non_sorted[int(j * stride)] for j in range(MAX_NONGOLD_FIT)]
    fit_idx = sorted(gold_idx + non_idx)
    f_fit = [f_rows[i] for i in fit_idx]
    labels_fit = [labels[i] for i in fit_idx]
    rows_fit = [rows[i] for i in fit_idx]
    folds = stratified_folds(rows_fit, labels_fit)

    default_folds = cv_fold_aucs(f_fit, labels_fit, folds, w0, boxes, 0.0, fit=False)
    if not default_folds:
        write_report("skipped_no_evaluable_folds", {"n_gold": n_gold})
        return
    lam_folds = {
        lam: cv_fold_aucs(f_fit, labels_fit, folds, w0, boxes, lam, fit=True)
        for lam in LAMBDA_GRID
    }
    common = sorted(default_folds)
    lam_gain: dict[float, float] = {}
    lam_gain_se: dict[float, float] = {}
    for lam, fold_aucs in lam_folds.items():
        if set(fold_aucs) != set(common):
            continue
        gains = [fold_aucs[f] - default_folds[f] for f in common]
        lam_gain[lam] = _mean(gains)
        lam_gain_se[lam] = _se(gains)

    top_lam = max(lam_gain, key=lambda lam: lam_gain[lam])
    floor_gain = lam_gain[top_lam] - lam_gain_se[top_lam]
    best_lam = max(lam for lam in lam_gain if lam_gain[lam] >= floor_gain)

    mean_gain = lam_gain[best_lam]
    se_gain = lam_gain_se[best_lam]
    adopt_threshold = max(ADOPT_FLOOR_AUC, ADOPT_SE_MULT * se_gain)
    default_auc = _mean([default_folds[f] for f in common])
    fitted_auc = _mean([lam_folds[best_lam][f] for f in common])

    base_scores = score_rows(f_rows, w0)
    base_lift = lift_at_decile(base_scores, labels)

    common_report = {
        "n_gold": n_gold,
        "n_nongold": n_nongold,
        "n_fit_nongold": len(non_idx),
        "lambda": best_lam,
        "default_heldout_auc": round(default_auc, 4),
        "fitted_heldout_auc": round(fitted_auc, 4),
        "heldout_auc_gain": round(mean_gain, 4),
        "gain_se": round(se_gain, 4),
        "adopt_threshold": round(adopt_threshold, 4),
        "lambda_gain_curve": {str(lam): round(g, 4) for lam, g in sorted(lam_gain.items())},
        "default_lift_at_decile": round(base_lift, 3),
    }

    if mean_gain < adopt_threshold:
        # Keep priors: current = default for every factor.
        for k, v in weights_cfg.items():
            v["current"] = v.get("default")
        config.pop("_weight_fit", None)
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        write_report("kept_defaults_no_generalizing_gain", common_report)
        return

    fitted = optimize(f_fit, labels_fit, list(range(len(f_fit))), w0, boxes, best_lam)
    fit_scores = score_rows(f_rows, fitted)
    fit_lift = lift_at_decile(fit_scores, labels)

    for k, v in weights_cfg.items():
        if k in fitted:
            v["current"] = round(fitted[k], 1)
    config["_weight_fit"] = {
        "method": "regularized_factor_fit_to_gold",
        "lambda_rule": "1se",
        **common_report,
        "fitted_lift_at_decile": round(fit_lift, 3),
        "weights_before": {k: round(v, 2) for k, v in w0.items()},
        "weights_after": {k: round(v, 2) for k, v in fitted.items()},
        "note": (
            "Per-JF ranges are frozen; only the factor blend was fit, shrunk "
            "toward the priors and adopted only because held-out AUC improved. "
            "These are the app's starting sliders — still fully tunable."
        ),
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    write_report("adopted_fit", config["_weight_fit"])


if __name__ == "__main__":
    main()
