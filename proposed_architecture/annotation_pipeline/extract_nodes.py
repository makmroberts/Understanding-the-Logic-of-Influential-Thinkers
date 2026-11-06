from dotenv import load_dotenv
from pathlib import Path

load_dotenv(
    Path(__file__).resolve().parent.parent / ".env"
)

# Defining what a valid node structure looks like
from ast import main
from pydantic import BaseModel, Field

class ArgumentNode(BaseModel):
    role: str
    text: str
    label: str
    explicit: bool
    paragraph_ids: list[str] = Field(default_factory=list)


class NodeExtraction(BaseModel):
    nodes: list[ArgumentNode]


# load the ontology
import yaml

def load_ontology(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        ontology = yaml.safe_load(file)

    if not isinstance(ontology, dict):
        raise ValueError("Ontology must be a YAML dictionary.")

    if not ontology.get("roles"):
        raise ValueError("Ontology does not define any roles.")

    return ontology

# prep the article text 
def prepare_article_text(markdown_text: str) -> str:
    """
    Convert numbered Markdown paragraphs into the
    format expected by the node extraction prompt.
    """
    body = markdown_text.split("## Body", 1)[1]
    body = body.split("## Figures", 1)[0]

    paragraphs = re.findall(
        r"<!-- (p\d+) -->\s*(.*?)(?=<!-- p\d+ -->|\Z)",
        body,
        flags=re.DOTALL
    )

    formatted = [
        f"{paragraph_id}: {text.strip()}"
        for paragraph_id, text in paragraphs
    ]

    return "\n\n".join(formatted)

# put together the LLM prompt
def build_prompt(article_text: str, ontology: dict) -> str:

    role_definitions = "\n".join(
        f"- {role}: {details['definition']}"
        + (
            f"\n  Guidance: {details['guidance']}"
            if "guidance" in details
            else ""
        )
        for role, details in ontology["roles"].items()
    )

    extraction_rules = "\n".join(
        f"- {rule}: {description}"
        for rule, description in ontology.get(
            "extraction_rules", {}
        ).items()
    )

    prompt = f"""
You are analyzing an article to reconstruct the author's
argument and reasoning.

ARGUMENT ONTOLOGY:
{role_definitions}

ONTOLOGY-SPECIFIC EXTRACTION RULES:
{extraction_rules}

EXTRACTION INSTRUCTIONS:

1. Identify the individual components of the author's argument.
2. Assign each component exactly one role from the ontology.
3. Prefer fine-grained claims over broad summaries.
4. Do not force the article into a predetermined flowchart.
5. Include stated and hidden assumptions when relevant.
6. Distinguish directly stated claims from inferred claims.
7. Preserve the original meaning of the author's reasoning.
8. Reference relevant paragraph IDs from the article.
9. Do not invent unsupported claims.
10. Do not extract relationships between nodes yet.

Return a JSON object containing a "nodes" list.

Each node must contain:
- role: argument role from the ontology
- text: full argument statement
- label: short descriptive label
- explicit: boolean
- paragraph_ids: list of paragraph IDs

ARTICLE:
{article_text}
"""
    return prompt

# connect to openrouter for testing 
import os
import json
from openai import OpenAI

def call_llm(prompt: str) -> NodeExtraction:

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
    )

    response = client.chat.completions.create(
        model=os.environ["OPENROUTER_MODEL"],
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an argument annotation assistant. "
                    "Return only a valid JSON object."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("The model returned an empty response.")

    data = json.loads(content)

    return NodeExtraction.model_validate(data)


# validate the nodes we got 
import re

def validate_nodes(
    extraction: NodeExtraction,
    ontology: dict,
    article_text: str
) -> list[dict]:

    allowed_roles = set(ontology["roles"].keys())

    valid_paragraphs = set(
        re.findall(r"(?m)^(p\d+):", article_text)
    )

    nodes = []

    for i, node in enumerate(extraction.nodes, start=1):

        if node.role not in allowed_roles:
            raise ValueError(
                f"Invalid ontology role: {node.role}"
            )

        for paragraph_id in node.paragraph_ids:
            if paragraph_id not in valid_paragraphs:
                raise ValueError(
                    f"Invalid paragraph ID: {paragraph_id}"
                )

        nodes.append({
            "id": f"n{i:03d}",
            "role": node.role,
            "content": {
                "text": node.text,
                "label": node.label,
                "explicit": node.explicit
            },
            "source": {
                "passages": [
                    {"paragraph_id": p}
                    for p in node.paragraph_ids
                ]
            }
        })

    return nodes

# the main attraction (main extraction function)
def extract_nodes(
    article_text: str,
    ontology_path: str
) -> list[dict]:

    ontology = load_ontology(ontology_path)

    prompt = build_prompt(article_text, ontology)

    extraction = call_llm(prompt)

    nodes = validate_nodes(
        extraction,
        ontology,
        article_text
    )

    return nodes


# let's give it a try
from pathlib import Path

if __name__ == "__main__":

    article_path = Path(
        "../internal/extracted/"
        "2025-07-07_chinas-stealth-trade-surplus.md"
    )
    ontology_path = "config/proposed_ontology.yaml"

    markdown_text = article_path.read_text(encoding="utf-8")
    article_text = prepare_article_text(markdown_text)

    nodes = extract_nodes(article_text, ontology_path)

    output_path = Path("data/annotations/nodes.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps({"nodes": nodes}, indent=2),
        encoding="utf-8"
    )

    print(f"Successfully extracted {len(nodes)} nodes.")
    print(f"Saved results to {output_path}")