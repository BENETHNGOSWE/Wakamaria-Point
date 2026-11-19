"""Who owns a fixture row, and what each writer may do with it.

Two things write ``Wakamaria Match``: the agent, from the provider's fixture
feed, and the screenshot import, from a tip read off a card. Without a rule the
two fight, and the fight is silent. The import blocks the agent from a fixture
the agent could have settled, and a manual row can never settle itself because
it has no provider identity. Meanwhile the import is refused on fixtures the
agent does not cover at all.

The rule, in one line: **the agent wins on anything it can see, and the import
fills the gaps.** That is not arbitrary — only a provider-linked row can ever
have its result fetched, so a fixture the agent can cover should belong to the
agent. A fixture it cannot cover has nothing to lose by being hand-entered.

Pure: no Frappe, no network, no clock.
"""

AGENT = "Agent"


def decide(existing):
    """What the agent should do about a fixture that may already be on the site.

    ``existing`` is None, or a dict with ``provider_match_id`` and
    ``predicted_by``. Returns one of:

    ``create``  nothing there yet
    ``adopt``   a hand-entered row: take it over, so the result can settle
    ``skip``    already ours, or already linked to the provider
    """
    if existing is None:
        return "create"
    if existing.get("provider_match_id"):
        return "skip"
    if existing.get("predicted_by") == AGENT:
        return "skip"
    return "adopt"


def upload_decision(existing):
    """What the screenshot import may do with a row it is about to create.

    ``create``  the fixture is free
    ``skip``    the agent already predicted it; the agent's pick stands
    ``block``   a hand-entered row is already there: a real duplicate
    """
    if existing is None:
        return "create"
    if existing.get("provider_match_id") or existing.get("predicted_by") == AGENT:
        return "skip"
    return "block"
