"""
Tests for app.core.llm_pricing — the pure cost-calculation function
that sits between "tokens the provider says we used" and "what
appears in the cost dashboard". Kept independent of the DB/agent
fixtures since it's pure arithmetic.
"""
import pytest

from app.core.llm_pricing import calculate_cost_usd
from app.core.config import get_settings


def test_known_model_uses_configured_rate_and_is_not_estimated():
    settings = get_settings()
    model = "openai/gpt-oss-120b"
    assert model in settings.llm_pricing_input_per_million

    cost, is_estimated = calculate_cost_usd(model, prompt_tokens=1_000_000, completion_tokens=0)

    assert cost == pytest.approx(settings.llm_pricing_input_per_million[model])
    assert is_estimated is False


def test_unknown_model_falls_back_and_is_flagged_estimated():
    cost, is_estimated = calculate_cost_usd(
        "some-brand-new-model-not-in-the-table", prompt_tokens=1_000_000, completion_tokens=0
    )

    assert cost > 0
    assert is_estimated is True


def test_zero_tokens_costs_nothing():
    cost, is_estimated = calculate_cost_usd("openai/gpt-oss-120b", prompt_tokens=0, completion_tokens=0)
    assert cost == 0.0


def test_local_provider_is_always_free_and_not_estimated(monkeypatch):
    from app.core import llm_pricing

    monkeypatch.setattr(llm_pricing.settings, "llm_provider", "local")
    cost, is_estimated = llm_pricing.calculate_cost_usd("llama3.1", prompt_tokens=50_000, completion_tokens=50_000)

    assert cost == 0.0
    assert is_estimated is False


def test_prompt_and_completion_tokens_priced_independently():
    model = "openai/gpt-oss-120b"
    settings = get_settings()
    input_rate = settings.llm_pricing_input_per_million[model]
    output_rate = settings.llm_pricing_output_per_million[model]

    cost, _ = calculate_cost_usd(model, prompt_tokens=1_000_000, completion_tokens=1_000_000)

    assert cost == pytest.approx(input_rate + output_rate)
