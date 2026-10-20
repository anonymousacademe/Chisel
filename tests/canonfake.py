"""Fakes for the canon proposal: the front ends call ``propose_canon`` (a CanonProposal), older fakes return a list."""

from chisel.ai.continuity import CanonProposal


def proposal_of(fn):
    """A fake of ``propose_canon`` from one written for ``propose_canon_updates`` (it returns the list of updates)."""
    def fake(*args, **kwargs):
        return CanonProposal(list(fn(*args, **kwargs)))
    return fake
