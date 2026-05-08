from __future__ import annotations

import math
import random
from collections.abc import Callable

from harness_backend.config.settings import SETTINGS


def metropolis_hastings_discrete(
    candidates: list[str],
    score_fn: Callable[[str], float],
    steps: int | None = None,
    temperature: float | None = None,
    seed: int | None = None,
) -> str:
    """
    MCMC sur espace fini d'actions: chaîne de Metropolis-Hastings avec noyau uniforme sur les voisins.
    La distribution cible est ~ softmax(score / T) ; utile pour stabiliser le choix sous bruit LLM.
    """
    uniq = [c for c in dict.fromkeys(candidates) if c]
    if not uniq:
        return "FINISH"
    if len(uniq) == 1:
        return uniq[0]
    rng = random.Random(seed)
    n_steps = int(steps if steps is not None else SETTINGS.reasoning_mcmc_steps)
    temp = float(temperature if temperature is not None else SETTINGS.reasoning_mcmc_temperature)
    temp = max(1e-6, temp)

    idx = int(rng.randrange(len(uniq)))
    for _ in range(max(1, n_steps)):
        j = int(rng.randrange(len(uniq)))
        if j == idx:
            continue
        si = score_fn(uniq[idx])
        sj = score_fn(uniq[j])
        alpha = min(1.0, math.exp((sj - si) / temp))
        if rng.random() < alpha:
            idx = j
    return uniq[idx]


def build_action_candidates(
    llm_action: str,
    query: str,
    executed: set[str],
    markov_fn: Callable[[str, set[str], int], list[str]],
) -> list[str]:
    out: list[str] = []
    if llm_action and llm_action != "FINISH":
        out.append(llm_action)
    out.extend(markov_fn(query, executed, max_extra=3))
    for a in ("stock_check", "classification_run", "recipe_compute", "prediction_regression", "FINISH"):
        if a not in out and a != "FINISH":
            out.append(a)
        if len(out) >= 6:
            break
    if "FINISH" not in out:
        out.append("FINISH")
    return [c for c in dict.fromkeys(out)]
