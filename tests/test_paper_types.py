"""The shared research-mode types (core/paper/types.py): they import, are frozen, and keep the contract's fields."""

import dataclasses

import pytest

from chisel.core.paper import types as t


def test_contract_types_exist_and_are_frozen():
    for name in ("CiteRef", "Citation", "Placement", "ObjectRef", "Num", "RefObject", "Annotation", "ZItem", "Flag"):
        cls = getattr(t, name)
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen, name


def test_citation_and_ref_fields():
    ref = t.CiteRef("smith2024", locator="p. 12", suppress_author=True)
    cite = t.Citation([ref], 0, 22, "[[@smith2024, p. 12]]", "bracketed")
    assert cite.refs[0].key == "smith2024" and cite.refs[0].prefix == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.key = "other"


def test_zitem_defaults_and_numbering_key():
    item = t.ZItem(key="ABCD1234", version=None, csl={"title": "T"}, citation_key=None)
    assert item.notes == [] and item.annotations == [] and item.deleted is False
    numbering: t.Numbering = {"fig:flow-model": t.Num(1, "1")}
    assert numbering["fig:flow-model"].display == "1"


def test_the_package_does_not_shadow_the_notebook_module():
    from chisel.core import research

    assert hasattr(research, "list_notes")
