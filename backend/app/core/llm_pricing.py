"""
NEXUS — LLM cost calculation.

Isolated from app/agents/base.py on purpose: pricing tables go stale
independently of agent logic and this keeps the "how much did this
call cost" math unit-testable without spinning up an agent or a DB
session.
"""
from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()

# Fallback rate applied when a model string isn't in the configured
# pricing tables (e.g. a brand-new Groq model NEXUS hasn't been told
# the price of yet). Deliberately non-zero: silently recording $0 for
# an unknown model would hide real spend from the cost dashboard,
# which is worse than a rough estimate that's visibly using a
# fallback (see `is_estimated` on TokenUsage).
FALLBACK_INPUT_PER_MILLION = 0.50
FALLBACK_OUTPUT_PER_MILLION = 1.00


def calculate_cost_usd(model_name: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, bool]:
    """
    Returns (cost_usd, is_estimated).

    is_estimated is True when the model wasn't found in the pricing
    table and the fallback rate was used, or when running against the
    local (self-hosted) provider — the caller can use this to render
    the cost as "~$0.0031" instead of "$0.0031" in the UI.
    """
    if settings.llm_provider == "local":
        # Local inference has no per-token API cost. It isn't "free" in
        # the sense of hardware/electricity, but there is no metered
        # spend to attribute to a request, so this is 0 and NOT
        # estimated — it's exact by definition.
        return 0.0, False

    input_rate = settings.llm_pricing_input_per_million.get(model_name)
    output_rate = settings.llm_pricing_output_per_million.get(model_name)
    is_estimated = input_rate is None or output_rate is None
    input_rate = input_rate if input_rate is not None else FALLBACK_INPUT_PER_MILLION
    output_rate = output_rate if output_rate is not None else FALLBACK_OUTPUT_PER_MILLION

    cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    return round(cost, 8), is_estimated
