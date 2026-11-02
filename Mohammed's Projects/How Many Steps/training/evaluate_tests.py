"""How well the live step counter on the UNO Q did on the counted Test walks.

    python evaluate_tests.py          (from this folder)

Uses the Test walks listed in data/test_paces.csv (their pace, the course
length, and the phase), the live count the board saved for each in
data/live_counts.csv, and the real counts in data/trials.csv (with
data/trial_corrections.csv).

Each phase is reported on its own. "before the fix" (Test T06-T17) was
counted live by the 22-feature model; those walks showed the sensor-angle
problem and so chose the fix (the 10 direction-free features), which means
they can't test the fix fairly. Walks recorded after the redeploy are the
fair test, compared with the current model's leave-one-out errors.

1. For each walk: the live count vs the real count, and the live distance vs
   the course length; whether the error was within the live +/-; and the
   plain peak counter (train_steps.peak_count) on the same recording.
2. Per pace: average and worst error, and the error as a % of the true total;
   next to the leave-one-out error from training (results_per_trial.csv),
   i.e. what training predicted for unseen trials.
3. For the walks before the fix, a diagnostic: the committee retrained with
   all 22 features and with only the 10 direction-free ones, counting the
   same walks. It shows why the fix was chosen.
4. Saves test_results.csv (per walk), one plot per phase
   (../media/test_walks.png before the fix, test_walks_after_fix.png after),
   and the "Test walks" section of results.md (train_steps.py keeps that
   section when it rewrites the file).
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save figures to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np

import train_steps as ts
import check_recordings as cr  # imported by train_steps from ../data

HERE = Path(__file__).resolve().parent
RESULTS_MD = HERE / "results.md"
MARKER = "<!-- test walks: written by evaluate_tests.py -->"
PACES = ts.PACES
BEFORE = "before the fix"
# Each phase: the leave-one-out results of the model that counted it live, and its plot
PHASES = {
    BEFORE: {"loo": HERE / "results_per_trial_22features.csv", "plot": "test_walks.png",
             "model": "the 22-feature model"},
    "after the fix": {"loo": HERE / "results_per_trial.csv", "plot": "test_walks_after_fix.png",
                      "model": "the direction-free model"},
}


def load_walks():
    """One dict per walk in test_paces.csv, with its real and live numbers."""
    trials = {t["file"]: t for t in cr.load_trials()}
    with open(cr.DATA / "live_counts.csv", newline="") as f:
        live = {r["file"]: r for r in csv.DictReader(f)}
    with open(cr.DATA / "test_paces.csv", newline="") as f:
        paces = list(csv.DictReader(f))
    walks = []
    for p in paces:
        t, lv = trials[p["file"]], live[p["file"]]
        ankle, _ = cr.load_ankle(p["file"])
        w = {"name": p["file"][:-4], "pace": p["pace"], "course_m": float(p["course_m"]), "phase": p["phase"],
             "true": int(t["steps"]), "live": float(lv["live_steps"]), "live_unc": float(lv["live_steps_unc"]),
             "live_m": float(lv["live_distance_m"]), "live_m_unc": float(lv["live_distance_unc"]),
             "peak": ts.peak_count({"ankle": ankle, "stomp_i": None}), "ankle": ankle}
        w["err"] = w["live"] - w["true"]
        w["m_err"] = w["live_m"] - w["course_m"]
        w["peak_err"] = w["peak"] - w["true"]
        walks.append(w)
    return walks


def loo_by_pace(path):
    """Training's leave-one-out error per pace (ankle only), as % of the true
    total, from a results_per_trial file: what training expected on unseen trials."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for p in PACES:
        r = [x for x in rows if x["activity"] == p]
        steps = sum(abs(float(x["ankle_steps"]) - float(x["true_steps"])) for x in r) / sum(float(x["true_steps"]) for x in r)
        dist = sum(abs(float(x["ankle_m"]) - float(x["true_m"])) for x in r) / sum(float(x["true_m"]) for x in r)
        out[p] = (100 * steps, 100 * dist)
    return out


def direction_free_diagnostic(walks):
    """Retrain the committee on the training trials twice, with all 22
    features and with only the 10 direction-free ones, and count each walk's
    moving stretch the training way (train_steps.clip_seconds). This is how
    the fix was chosen, for the walks before it."""
    full = ts.clip_features
    combined = lambda x: np.concatenate([ts.per_axis_features(x), ts.direction_free_features(x)])
    trials = [ts.load_trial(t) for t in ts.good_trials()]
    results = {}
    for label, features in [("all 22 features", combined), ("direction-free only", ts.direction_free_features)]:
        ts.clip_features = features
        X = np.vstack([ts.trial_clips(tr, False)[0] for tr in trials])
        y = np.vstack([ts.trial_clips(tr, False)[1] for tr in trials])
        nets = [ts.train_net(X, y, seed=k)[:3] for k in range(ts.N_NETS)]
        totals = []
        for w in walks:
            moving = np.flatnonzero(np.linalg.norm(w["ankle"][:, 3:], axis=1) > ts.MOVING_DPS)
            tr = {"lo": moving[0], "hi": moving[-1] + 1}
            Xw = np.array([features(w["ankle"][s:s + ts.CLIP]) for s in ts.clip_starts(tr)])
            out = np.mean([ts.predict(n, m, s, Xw) for n, m, s in nets], axis=0)
            totals.append(float((out[:, 0] * ts.clip_seconds(tr)).sum()))
        results[label] = totals
    ts.clip_features = full
    return results


# ---- Tables ------------------------------------------------------------------------------
def per_walk_table(walks):
    lines = ["| Walk | Pace | Your count | Live count | Error | Within ±? | Peak counter | Live distance (of 20 m) |",
             "|---|---|---|---|---|---|---|---|"]
    for w in walks:
        lines.append(f"| {w['name'][9:]} | {w['pace'].replace('_', ' ')} | {w['true']} | {w['live']:.1f} ± {w['live_unc']:.1f} "
                     f"| {w['err']:+.1f} | {'yes' if abs(w['err']) <= w['live_unc'] else 'no'} | {w['peak']} ({w['peak_err']:+d}) "
                     f"| {w['live_m']:.1f} ± {w['live_m_unc']:.1f} m ({w['m_err']:+.1f}) |")
    return "\n".join(lines)


def per_pace_table(walks, loo):
    lines = ["| Pace | Live: average error | Live: worst | Live: error % | Training expected (leave-one-out) "
             "| Peak counter: error % | Live distance: average error | Distance error % | Training expected (distance) |",
             "|---|---|---|---|---|---|---|---|---|"]
    groups = PACES + ["All"]
    for g in groups:
        ws = [w for w in walks if g == "All" or w["pace"] == g]
        true = sum(w["true"] for w in ws)
        err = [w["err"] for w in ws]
        worst = max(err, key=abs)
        pct = 100 * sum(abs(e) for e in err) / true
        peak_pct = 100 * sum(abs(w["peak_err"]) for w in ws) / true
        m_err = [w["m_err"] for w in ws]
        m_pct = 100 * sum(abs(e) for e in m_err) / sum(w["course_m"] for w in ws)
        expected = (f"{loo[g][0]:.1f}%", f"{loo[g][1]:.1f}%") if g in loo else \
            (f"{np.mean([v[0] for v in loo.values()]):.1f}% (average)", f"{np.mean([v[1] for v in loo.values()]):.1f}% (average)")
        # Average error = the average size of the error (low and high don't cancel out);
        # worst = the biggest one, with its sign (- = counted too few)
        lines.append(f"| {g.replace('_', ' ')} | {np.mean(np.abs(err)):.1f} steps | {worst:+.1f} | {pct:.1f}% | {expected[0]} "
                     f"| {peak_pct:.1f}% | {np.mean(np.abs(m_err)):.1f} m | {m_pct:.1f}% | {expected[1]} |")
    return "\n".join(lines)


def diagnostic_table(walks, diag):
    lines = ["| Walk | Your count | Retrained, all 22 features | Retrained, direction-free only |", "|---|---|---|---|"]
    for w, a, b in zip(walks, diag["all 22 features"], diag["direction-free only"]):
        lines.append(f"| {w['name'][9:]} | {w['true']} | {a:.1f} | {b:.1f} |")
    averages = [f"{label}: {np.abs(np.array(diag[label]) - [w['true'] for w in walks]).mean():.1f} steps"
                for label in diag]
    return "\n".join(lines) + "\n\nAverage error per walk: " + "; ".join(averages) + "."


# ---- Plot ----------------------------------------------------------------------------------
def plot(walks, path, phase):
    """Left: steps error per walk (live with its ±, and the peak counter),
    grouped by pace. Right: live distance error vs the 20 m course."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), facecolor="#fcfcfb")
    walks = sorted(walks, key=lambda w: PACES.index(w["pace"]))
    group = [PACES.index(w["pace"]) for w in walks]
    x = np.arange(len(walks)) + np.array(group) * 0.8                        # a gap between paces
    ax = axes[0]
    ax.axhline(0, color=ts.MUTED, lw=1, ls="--", zorder=0)
    ax.errorbar(x - 0.12, [w["err"] for w in walks], yerr=[w["live_unc"] for w in walks], fmt="o", ms=7,
                color=ts.BLUE, mec="#fcfcfb", mew=1, elinewidth=1.4, capsize=3, label="live count on the board (± shown)")
    ax.plot(x + 0.12, [w["peak_err"] for w in walks], "^", ms=7, color=ts.AQUA, mec="#fcfcfb", mew=1,
            label="peak counter (no net)")
    ax.set_ylabel("Estimate − your count (steps)", color=ts.INK_2)
    ax.set_title(f"Steps: error on each 20 m walk ({phase})", loc="left", color=ts.INK, fontsize=11)
    ax.legend(frameon=False, labelcolor=ts.INK_2, loc="center left", bbox_to_anchor=(0, 0.62))
    ax = axes[1]
    ax.axhline(0, color=ts.MUTED, lw=1, ls="--", zorder=0)
    ax.errorbar(x, [w["m_err"] for w in walks], yerr=[w["live_m_unc"] for w in walks], fmt="o", ms=7,
                color=ts.BLUE, mec="#fcfcfb", mew=1, elinewidth=1.4, capsize=3)
    ax.set_ylabel("Live distance − 20 m (m)", color=ts.INK_2)
    ax.set_title(f"Distance: error on each 20 m walk ({phase})", loc="left", color=ts.INK, fontsize=11)
    shown = sorted(set(group))
    centres = [x[np.array(group) == g].mean() for g in shown]
    for ax in axes:
        ax.set_xticks(centres, [PACES[g].replace("_", "\n") for g in shown], color=ts.INK_2)
        ts.style(ax)
    fig.text(0.01, 0.01, "Each dot is one walk. Dashed line: exactly right. Error bars: the live ± "
             "(training's typical error for that pace).", color=ts.MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


# ---- Main ------------------------------------------------------------------------------------
def phase_section(phase, walks, diag):
    loo = loo_by_pace(PHASES[phase]["loo"])
    within = sum(abs(w["err"]) <= w["live_unc"] for w in walks)
    text = (f"### {phase[0].upper() + phase[1:]}: counted live by {PHASES[phase]['model']}\n\n"
            + ("These walks showed the sensor-angle problem and chose the fix, so they're the \"before\" "
               "comparison, not a test of the fix.\n\n" if phase == BEFORE else
               "Recorded after the redeploy: the fair test of the fix.\n\n")
            + "Per pace (\"Training expected\" is that model's leave-one-out error):\n\n"
            + per_pace_table(walks, loo) + "\n\nEach walk:\n\n" + per_walk_table(walks) + "\n\n"
            + f"{within} of {len(walks)} walks were within the live ±.\n")
    if diag:
        text += ("\nWhy they came out low: the same committee retrained on the training trials and run on these "
                 "walks the training way (moving stretch only). With all 22 features it undercounts like the board; "
                 "with only the 10 features that don't depend on how the sensor sits on the leg, it's close. This is "
                 "how the fix was chosen.\n\n" + diagnostic_table(walks, diag) + "\n")
    return text


def main():
    walks = load_walks()
    phases = list(dict.fromkeys(w["phase"] for w in walks))      # in the order of test_paces.csv
    by_phase = {p: [w for w in walks if w["phase"] == p] for p in phases}
    diag = direction_free_diagnostic(by_phase[BEFORE]) if BEFORE in by_phase else None

    with open(HERE / "test_results.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["walk", "phase", "pace", "true_steps", "live_steps", "live_steps_unc", "error", "within_unc",
                     "peak_steps", "live_m", "live_m_unc", "m_error", "retrained_all22", "retrained_direction_free"])
        retrained = {}
        if diag:
            for w, a, b in zip(by_phase[BEFORE], diag["all 22 features"], diag["direction-free only"]):
                retrained[w["name"]] = (round(a, 1), round(b, 1))
        for w in walks:
            wr.writerow([w["name"], w["phase"], w["pace"], w["true"], w["live"], w["live_unc"], round(w["err"], 1),
                         abs(w["err"]) <= w["live_unc"], w["peak"], w["live_m"], w["live_m_unc"], round(w["m_err"], 2),
                         *retrained.get(w["name"], ("", ""))])

    section = (f"{MARKER}\n## Test walks: the live count on the board\n\n"
               "Written by `evaluate_tests.py`. Counted walks on the 20 m course, counted live by the UNO Q (no "
               "stomp or phone). The live count is what the board saved for each walk; the peak counter ran on the "
               "same recordings.\n\n"
               + "\n".join(phase_section(p, by_phase[p], diag if p == BEFORE else None) for p in phases))
    if "after the fix" not in by_phase:
        section += "\n### After the fix\n\nNo test walks yet (Test T18 and up, after the redeploy).\n"
    # Replace this section in results.md, keeping what train_steps.py wrote above it
    text = RESULTS_MD.read_text()
    RESULTS_MD.write_text(text.split(MARKER)[0].rstrip() + "\n\n" + section)

    for p in phases:
        plot(by_phase[p], ts.MEDIA / PHASES[p]["plot"], p)
    print(section)


if __name__ == "__main__":
    main()
