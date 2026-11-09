"""Answer formats for the model steps, built at run time from the ontology and the article.

The allowed values are enums in the schema, so the model cannot return a role, relation,
paragraph or box ID that does not exist. Field order is the order the model writes in:
the excerpt comes before the claim, so the claim is written with the source in view.
"""
from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, create_model

from .config import Ontology

STRICT = ConfigDict(extra="forbid")


def boxes_model(ont: Ontology, para_ids: list[int]):
    attrs = {}
    for a, by_role in ont.attributes.items():
        vals = sorted({v for vs in by_role.values() for v in vs}) + ["none"]
        attrs[a] = (Literal[tuple(vals)], Field(
            description=f"Only for {', '.join(by_role)}; otherwise none."))
    Box = create_model(
        "Box", __config__=STRICT,
        excerpt=(str, Field(description="Words copied exactly from one paragraph that state this "
                            "box, at most about 40 words. Empty when no paragraph states it.")),
        claim=(str, Field(description="The box as one sentence in your own words.")),
        role=(Literal[tuple(ont.roles)], ...),
        explicit=(bool, Field(description="true if the article states it, false if you inferred it.")),
        **attrs,
        paragraphs=(list[Literal[tuple(para_ids)]], Field(
            description="Every paragraph this box draws on, not only the best one.")),
        reason=(str, Field(description="The general rule the author applies at this step, "
                           "in one sentence.")),
    )
    return create_model("Boxes", __config__=STRICT, boxes=(list[Box], ...))


def links_model(ont: Ontology, box_ids: list[str]):
    Ids = Literal[tuple(box_ids)]
    Link = create_model(
        "Link", __config__=STRICT,
        from_box=(Ids, ...),
        relation=(Literal[tuple(ont.relations)], ...),
        to_box=(Ids, ...),
    )
    return create_model("Links", __config__=STRICT, links=(list[Link], ...))

