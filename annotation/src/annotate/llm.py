"""The one door to the model service in settings.yaml `gateway` (OpenRouter; the Duke AI Gateway
is kept there as a comment): structured output, a response cache and a call record.

Every call is cached under a hash of everything that shapes the answer (model, messages,
schema, parameters, repeat index), so re-running a step costs nothing and returns the same
answer. `repeat` > 0 asks the same question again on purpose, for the consistency report.
Every call, cached or not, is appended to the article's calls.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from .config import path, settings


class GatewayError(RuntimeError):
    pass


def _refused(model: str, e: APIStatusError) -> GatewayError:
    """A plain reason, without the key details the Gateway puts in its message."""
    msg = str(e.message)
    if "budget" in msg.lower():
        m = re.search(r"Current cost: ([\d.]+), Max budget: ([\d.]+)", msg)
        spent = f" (spent ${float(m.group(1)):.2f} of ${float(m.group(2)):.2f})" if m else ""
        return GatewayError(f"the key's budget is used up{spent}; run again after it resets "
                            "or with a higher budget")
    if e.status_code == 402 or "credit" in msg.lower():
        return GatewayError("the account's credit is used up; top it up, then run the same "
                            "command again (finished steps come from the cache)")
    clean = re.sub(r"Key=\S+|sk-\S+", "[key]", msg)
    return GatewayError(f"{model}: the Gateway refused the request ({e.status_code}): {clean[:300]}")


def _key() -> str:
    env = settings()["gateway"]["key_env"]
    k = os.environ.get(env, "")
    if not k and os.name == "nt":                 # set with setx, not yet in this shell
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, env)[0]
        except OSError:
            k = ""
    if not k.strip():
        raise GatewayError(f"the Gateway key is not set: put it in the user environment variable {env}")
    return k.strip()


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def strict_schema(model_cls) -> dict:
    """Pydantic JSON schema with $refs inlined, which every provider behind the Gateway accepts."""
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(x):
        if isinstance(x, dict):
            if "$ref" in x:
                return walk(defs[x["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in x.items() if k != "title"}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(schema)


class Gateway:
    def __init__(self, calls_file: Path):
        self._client = None
        self.calls_file = calls_file
        self.cache = path("cache")
        self._checked = False

    @property
    def client(self) -> OpenAI:
        if self._client is None:                       # only when a call is not in the cache
            g = settings()["gateway"]
            self._client = OpenAI(base_url=g["base_url"], api_key=_key(),
                                  timeout=g.get("timeout_s", 600), max_retries=5)
        return self._client

    def check(self) -> None:
        """Fail early and plainly when the Gateway is out of reach (usually: VPN off)."""
        try:
            self.client.with_options(timeout=15, max_retries=0).models.list()
        except (APIConnectionError, APITimeoutError) as e:
            raise GatewayError(f"{settings()['gateway']['base_url']} is not reachable "
                               "(for the Duke Gateway, the Duke VPN must be on)") from e
        except APIStatusError as e:
            raise _refused("models", e) from e

    def ask(self, *, step: str, model: str, messages: list[dict], schema,
            params: dict | None = None, repeat: int = 0) -> tuple[str, dict]:
        """Returns (raw JSON text, record). Validation is the caller's job, so it can retry.
        `schema` is a Pydantic model class, or a ready JSON schema dict (label_facets builds one)."""
        params = dict(params or {})
        name = getattr(schema, "__name__", step)
        if not isinstance(schema, dict):
            schema = strict_schema(schema)
        rf = {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
        extra = settings()["gateway"].get("extra_body") or {}
        key = sha({"model": model, "messages": messages, "schema": schema,
                   "params": params, "extra": extra, "repeat": repeat})
        rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "step": step,
               "model": model, "params": params, "repeat": repeat, "key": key,
               "prompt_sha": sha(messages), "schema_sha": sha(schema)}
        hit = self.cache / f"{key}.json"
        if hit.exists():
            cached = json.loads(hit.read_text(encoding="utf-8"))
            rec.update(cached["record"], cached=True)
            self._log(rec, cached["text"])
            return cached["text"], rec

        if not self._checked:                          # only when the network is really needed
            self.check()
            self._checked = True
        t0 = time.time()
        try:
            raw = self.client.chat.completions.with_raw_response.create(
                model=model, messages=messages, response_format=rf,
                **({"extra_body": extra} if extra else {}), **params)
        except RateLimitError as e:
            raise GatewayError(f"{model}: rate or daily limit reached ({e}); run the same command "
                               "again later and it resumes from the last finished step") from e
        except (APIConnectionError, APITimeoutError) as e:
            raise GatewayError(f"{settings()['gateway']['base_url']} is not reachable "
                               "(for the Duke Gateway, the Duke VPN must be on)") from e
        except APIStatusError as e:
            raise _refused(model, e) from e
        resp = raw.parse()
        choice = resp.choices[0]
        text = choice.message.content or ""
        u = resp.usage
        cost = raw.headers.get("x-litellm-response-cost")             # Duke Gateway (LiteLLM)
        if cost is None and u is not None:                              # OpenRouter usage accounting
            cost = getattr(u, "cost", None) or (getattr(u, "model_extra", None) or {}).get("cost")
        rec.update(cached=False, seconds=round(time.time() - t0, 1),
                   request_id=raw.headers.get("x-request-id") or resp.id,
                   served_model=resp.model, finish=choice.finish_reason,
                   tokens_in=getattr(u, "prompt_tokens", 0), tokens_out=getattr(u, "completion_tokens", 0),
                   cost_usd=float(cost) if cost else None)
        if choice.finish_reason == "length":
            rec["error"] = "the answer was cut off at max_tokens; make it shorter"
        elif choice.finish_reason not in ("stop", None) or not text.strip():
            rec["error"] = f"no usable answer (finish: {choice.finish_reason}, {len(text)} characters)"
        self.cache.mkdir(parents=True, exist_ok=True)
        if "error" not in rec:
            keep = {k: rec[k] for k in ("request_id", "served_model", "finish", "tokens_in",
                                        "tokens_out", "cost_usd", "seconds")}
            hit.write_text(json.dumps({"record": keep, "text": text}, ensure_ascii=False),
                           encoding="utf-8")
        self._log(rec, text)
        return text, rec

    def _log(self, rec: dict, text: str) -> None:
        self.calls_file.parent.mkdir(parents=True, exist_ok=True)
        with self.calls_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**rec, "response": text}, ensure_ascii=False) + "\n")
