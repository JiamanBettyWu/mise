"""anthropic 1.x removed `temperature` from messages.create()'s signature.

The trip planner still needs it (#120) and sends it via `extra_body`. The
other fakes in this suite accept `**kwargs`, so a plain-kwarg regression
would pass CI and raise TypeError on every POST /trips/plan in prod. This
binds the real kwargs against the installed SDK's signature.
"""

import inspect
import json
from types import SimpleNamespace

import pytest
from anthropic.resources.messages import Messages

import services.claude as claude
import services.trip_planner as tp
from services.claude import sampling_params

_CREATE_SIG = inspect.signature(Messages.create)


class _SignatureCheckingClient:
    """Fake client whose create() rejects anything the real SDK would."""

    def __init__(self, text: str):
        self.messages = self
        self.text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        _CREATE_SIG.bind(None, **kwargs)  # TypeError on a removed kwarg
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)],
            stop_reason="end_turn",
            usage=None,
        )


def test_signature_check_rejects_plain_temperature():
    fake = _SignatureCheckingClient("{}")
    with pytest.raises(TypeError):
        fake.create(model="m", max_tokens=1, messages=[], temperature=0.2)


def test_recommend_packing_plan_binds_against_real_sdk(monkeypatch):
    plan = {"item_ids": ["a"], "gaps": [], "essentials": [], "reasoning": "ok"}
    fake = _SignatureCheckingClient(json.dumps(plan))
    monkeypatch.setattr(claude, "client", lambda: fake)

    out = tp.recommend_packing_plan(["weather", "catalog"])

    assert out.item_ids == ["a"]
    assert fake.last_kwargs["model"] == tp.MODEL
    # #120's low temperature still reaches the wire, via extra_body.
    assert fake.last_kwargs["extra_body"] == {"temperature": 0.2}
    assert "temperature" not in fake.last_kwargs


@pytest.mark.parametrize(
    "model",
    ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
)
def test_sampling_params_for_accepting_models(model):
    assert sampling_params(model, 0.2) == {"extra_body": {"temperature": 0.2}}


@pytest.mark.parametrize(
    "model",
    ["claude-opus-4-7", "claude-sonnet-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
)
def test_sampling_params_dropped_for_rejecting_models(model):
    assert sampling_params(model, 0.2) == {}
