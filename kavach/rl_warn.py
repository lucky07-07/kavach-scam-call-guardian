# When to warn: a reinforcement-learning policy on top of the code Judge.
# In a live call Kavach must decide after every caller turn whether to warn now or wait. Warning too early on a genuine
# call costs trust; warning after the scam has turned harmful (the OTP is already shared) is too late. The Judge still
# decides what counts as evidence (the caller's own words, verified in code); this policy only decides WHEN to speak.
#
#   episode  one ICFD-31k call; a decision after each caller turn on the call so far
#   state    (distinct verified request/threat tactics so far 0-3, caller turns that carried such evidence 0-3,
#            softer signs 0/1/2+, red line fired, caller turn 1-5+)
#   actions  WAIT, WARN (warning ends the episode)
#   reward   scam: +1 if warned by the turn where ICFD marks it harmful, minus 0.25 per caller turn later (floor 0.2);
#            -1 if never warned. genuine: -1.5 for a false alarm, +0.2 for staying silent
#   learner  direct policy search from the Judge's rule (default; --learner fqi / q for fitted Q-iteration or online
#            Q-learning, which mis-estimate here because the compact state aliases different calls); trained on ICFD
#            train calls, evaluated on held-out calls
#   baseline the Judge alone: warn at the first caller turn with verified request/threat evidence
#
# Usage: .venv\Scripts\python -m kavach.rl_warn [--n 3000]      -> data/rl/policy.json, data/rl/report.json
import argparse, io, json, random, sys
from collections import defaultdict
from pathlib import Path

import zstandard

from kavach.rules import REQUEST_OR_THREAT, TACTICS, caller_lines, red_lines, verify

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "icfd31k" / "raw" / "source_conversations"
OUT = ROOT / "data" / "rl"
WAIT, WARN = 0, 1
R_EARLY, R_LATE_STEP, R_LATE_MIN, R_MISS, R_FALSE, R_QUIET = 1.0, 0.25, 0.2, -1.0, -1.5, 0.2


def load(split):
    rows = []
    for f in sorted(RAW.glob(f"{split}-*.jsonl.zst")):
        with zstandard.ZstdDecompressor().stream_reader(open(f, "rb")) as r:
            rows += [json.loads(l) for l in io.TextIOWrapper(r, encoding="utf-8") if l.strip()]
    return rows


def episode(x):
    # -> {"scam", "harm_step", "steps": [state, ...]} with one decision per caller turn
    turns = [t for t in x["transcript"] if t["speaker"] in ("Agent", "Customer") and (t.get("text") or "").strip()]
    harm_t = next((c.get("timestamp") for c in x.get("chunk_level_analysis") or [] if c.get("verdict_at_chunk") == "YES"), None)
    lines, steps, hard, soft, red, harm_step, hard_turns = [], [], set(), set(), False, None, 0
    for t in turns:
        lines.append(f"{'Caller' if t['speaker'] == 'Agent' else 'User'}: {' '.join(t['text'].split())}")
        if t["speaker"] != "Agent":
            continue
        call = "\n".join(lines)
        line = caller_lines(call)[-1]
        found = {k for k in TACTICS if verify(k, line, call) == "ok"}   # every tactic the code would accept on this line
        rl = {e["tactic"] for e in red_lines("Caller: " + line)}
        turn_hard = (found | rl) & REQUEST_OR_THREAT
        hard_turns += bool(turn_hard)
        hard |= turn_hard
        soft |= found - REQUEST_OR_THREAT
        red = red or bool(rl)
        i = len(steps)
        # scams stack different demands and repeat them; a genuine call mentions one payment once
        steps.append((min(len(hard), 3), min(hard_turns, 3), min(len(soft), 2), int(red), min(i, 4)))
        if harm_step is None and harm_t is not None and (t.get("timestamp_end") or 0) >= harm_t:
            harm_step = i
    scam = x["final_verdict"] == "YES"
    return {"scam": scam, "harm_step": harm_step if scam else None, "steps": steps}


def reward_warn(ep, i):
    if not ep["scam"]:
        return R_FALSE
    harm = ep["harm_step"] if ep["harm_step"] is not None else len(ep["steps"]) - 1
    return R_EARLY if i <= harm else max(R_LATE_MIN, R_EARLY - R_LATE_STEP * (i - harm))


def reward_end(ep):
    return R_MISS if ep["scam"] else R_QUIET


def run(policy, ep):
    # -> (reward, warned step or None)
    for i, s in enumerate(ep["steps"]):
        if policy(s) == WARN:
            return reward_warn(ep, i), i
    return reward_end(ep), None


def q_learning(episodes, passes=40, alpha=0.05, eps=0.3, seed=0):
    rng = random.Random(seed)
    Q = defaultdict(lambda: [0.0, 0.0])
    for p in range(passes):
        order = episodes[:]
        rng.shuffle(order)
        e = eps * (1 - p / passes)
        for ep in order:
            for i, s in enumerate(ep["steps"]):
                a = rng.randrange(2) if rng.random() < e else int(Q[s][WARN] > Q[s][WAIT])
                last = i == len(ep["steps"]) - 1
                if a == WARN:
                    Q[s][WARN] += alpha * (reward_warn(ep, i) - Q[s][WARN])
                    break
                target = reward_end(ep) if last else max(Q[ep["steps"][i + 1]])
                Q[s][WAIT] += alpha * (target - Q[s][WAIT])
    return dict(Q)


def fitted_q(episodes, iterations=30):
    # batch RL: the evidence a call produces does not depend on the action, so the logged calls are all the experience
    # there is. Repeatedly re-estimate Q(s, WARN) and Q(s, WAIT) = E[best value of the next state, or the end of call]
    warn, wait_next = defaultdict(list), defaultdict(list)
    for ep in episodes:
        for i, s in enumerate(ep["steps"]):
            warn[s].append(reward_warn(ep, i))
            wait_next[s].append(ep["steps"][i + 1] if i + 1 < len(ep["steps"]) else ("END", reward_end(ep)))
    q_warn = {s: sum(v) / len(v) for s, v in warn.items()}
    Q = {s: [0.0, q_warn[s]] for s in warn}
    for _ in range(iterations):
        new = {}
        for s, nexts in wait_next.items():
            vals = [n[1] if n[0] == "END" else max(Q[n]) for n in nexts]
            new[s] = [sum(vals) / len(vals), q_warn[s]]
        if all(abs(new[s][0] - Q[s][0]) < 1e-6 for s in Q):
            Q = new
            break
        Q = new
    return Q


def policy_search(episodes, init, passes=4):
    # direct policy search: the compact state aliases very different calls, so value-based learners (Q-learning,
    # fitted Q) mis-estimate. Instead evaluate whole policies by replaying them on the logged calls, starting from
    # the Judge's own rule and flipping one state's action at a time, keeping a flip only if the total reward rises
    states = sorted({s for ep in episodes for s in ep["steps"]}, key=lambda s: -sum(s in ep["steps"] for ep in episodes[:2000]))
    act = {s: init(s) for s in states}
    total = lambda: sum(run(lambda s: act.get(s, WAIT), ep)[0] for ep in episodes)
    best = total()
    for _ in range(passes):
        improved = False
        for s in states:
            act[s] ^= 1
            score = total()
            if score > best + 1e-9:
                best, improved = score, True
            else:
                act[s] ^= 1
        if not improved:
            break
    return {s: ([0.0, 1.0] if a == WARN else [1.0, 0.0]) for s, a in act.items()}


def evaluate(policy, episodes):
    scams = [e for e in episodes if e["scam"]]
    genuine = [e for e in episodes if not e["scam"]]
    res = [(e, *run(policy, e)) for e in episodes]
    caught = [(e, i) for e, r, i in res if e["scam"] and i is not None]
    on_time = sum(i <= (e["harm_step"] if e["harm_step"] is not None else 99) for e, i in caught)
    lead = [((e["harm_step"] or 0) - i) for e, i in caught if e["harm_step"] is not None]
    return {"scams_warned": f"{len(caught)}/{len(scams)}", "scams_warned_in_time": f"{on_time}/{len(scams)}",
            "false_alarms": f"{sum(1 for e, r, i in res if not e['scam'] and i is not None)}/{len(genuine)}",
            "mean_turns_before_harm": round(sum(lead) / max(len(lead), 1), 2),
            "mean_reward": round(sum(r for _, r, _ in res) / len(res), 3)}


def paired_gap(a, b, episodes, n=2000, seed=0):
    # paired bootstrap over held-out calls: 95% interval for mean reward of policy a minus policy b
    d = [run(a, e)[0] - run(b, e)[0] for e in episodes]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return {"mean": round(sum(d) / len(d), 4), "ci95": [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=3000, help="calls per class for training")
    p.add_argument("--learner", choices=["search", "fqi", "q"], default="search", help="policy search (default), fitted Q-iteration or Q-learning")
    a = p.parse_args()
    rows = [x for x in load("train") if x["final_verdict"] in ("YES", "NO")]
    rng = random.Random(2026)
    rng.shuffle(rows)
    cut = int(len(rows) * 0.8)   # held-out calls never seen in training
    pick = lambda xs, k: [x for x in xs if x["final_verdict"] == "YES"][:k] + [x for x in xs if x["final_verdict"] == "NO"][:k]
    train_rows, test_rows = pick(rows[:cut], a.n), pick(rows[cut:], max(500, a.n // 3))
    print(f"featurising {len(train_rows)} train and {len(test_rows)} held-out calls with the code Judge…", flush=True)
    train = [episode(x) for x in train_rows]
    test = [episode(x) for x in test_rows]
    judge0 = lambda s: int(s[0] >= 1)
    Q = {"fqi": lambda: fitted_q(train), "q": lambda: q_learning(train), "search": lambda: policy_search(train, judge0)}[a.learner]()
    learned = lambda s: int(Q.get(s, [0, 0])[WARN] > Q.get(s, [0, 0])[WAIT])
    judge = lambda s: int(s[0] >= 1)                       # baseline: warn on the first verified request/threat
    judge_soft = lambda s: int(s[0] >= 1 or s[2] >= 2)      # baseline: also warn on two softer signs
    report = {"held_out": {"rl_policy": evaluate(learned, test), "judge_first_evidence": evaluate(judge, test),
                           "judge_or_two_soft_signs": evaluate(judge_soft, test)},
              "train": {"rl_policy": evaluate(learned, train), "judge_first_evidence": evaluate(judge, train)},
              "rl_minus_judge_held_out": paired_gap(learned, judge, test),
              "states_learned": len(Q), "learner": a.learner, "calls": {"train": len(train), "held_out": len(test)},
              "reward": {"early": R_EARLY, "late_step": -R_LATE_STEP, "miss": R_MISS, "false_alarm": R_FALSE, "quiet": R_QUIET}}
    OUT.mkdir(parents=True, exist_ok=True)
    policy = {",".join(map(str, s)): {"wait": round(q[WAIT], 3), "warn": round(q[WARN], 3), "action": "WARN" if q[WARN] > q[WAIT] else "WAIT"}
              for s, q in sorted(Q.items())}
    (OUT / "policy.json").write_text(json.dumps(policy, indent=1), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["held_out"], indent=2))
    print("rl - judge (held-out):", report["rl_minus_judge_held_out"])
    print("states:", len(Q), "| WARN:", sum(q[WARN] > q[WAIT] for q in Q.values()))


if __name__ == "__main__":
    main()
