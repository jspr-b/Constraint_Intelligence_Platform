"""The mapping wizard's one AI module (ADR-0011 §4).

The AI only suggests: which field an open column is, and later what a code means or how to fix
a data problem. It never decides, never changes a flow and never makes a number; every
suggestion is marked "suggested by AI" and the client confirms it.

What may leave the app is fixed here and nowhere else (``privacy_payload``): file and column
names, and at most 5 anonymised example values per column. Never whole files, never personal
columns, never figures to calculate, never plant, company or account names.

Without a key (``CIP_ANTHROPIC_API_KEY``) nothing is sent and the wizard runs on rules; the
page says "AI not connected". An error, a timeout or a cost limit gives the same fallback with
a plain reason. The import never waits on the AI.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol

from fastapi import Depends

from cip_api.settings import Settings, get_settings

AiState = Literal["not_connected", "connected", "limit_reached", "error"]
MAX_EXAMPLES = 5
MAX_COLUMNS = 60
"""Open columns asked about in one call; the rest stay for the client to answer."""
MAX_TOKENS = 2000


@dataclass
class Reply:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    """Something that answers a prompt: the Claude client in the app, a fake in tests."""

    def complete(self, system: str, prompt: str, max_tokens: int) -> Reply: ...


class ClaudeProvider:
    """Anthropic's Messages API through the official SDK, with a timeout and retries."""

    def __init__(self, api_key: str, model: str, timeout_s: float, retries: int) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=retries)
        self._model = model

    def complete(self, system: str, prompt: str, max_tokens: int) -> Reply:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return Reply(text, response.usage.input_tokens, response.usage.output_tokens)


def get_ai_provider(settings: Annotated[Settings, Depends(get_settings)]) -> Provider | None:
    """The Claude client when a key is set; None runs the wizard on rules. Tests replace this
    dependency with a fake; the running app never has one."""
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        return None
    return ClaudeProvider(
        settings.anthropic_api_key.get_secret_value(),
        settings.ai_model,
        settings.ai_timeout_s,
        settings.ai_retries,
    )


class AiUnavailableError(Exception):
    def __init__(self, state: AiState) -> None:
        super().__init__(state)
        self.state = state


@dataclass
class Budget:
    """What this import and this month may still spend, in euros. ``spent_eur`` is this
    import's total, earlier recognitions of the same upload included."""

    import_left_eur: float
    month_left_eur: float
    spent_eur: float = 0.0

    def allows(self, eur: float) -> bool:
        return eur <= min(self.import_left_eur, self.month_left_eur)

    def spend(self, eur: float) -> None:
        self.spent_eur += eur
        self.import_left_eur -= eur
        self.month_left_eur -= eur


@dataclass
class Ai:
    provider: Provider | None
    budget: Budget
    eur_per_mtok_in: float
    eur_per_mtok_out: float
    state: AiState = "not_connected"
    sent: list[dict[str, Any]] = field(default_factory=list)
    """Every payload sent, for the privacy test."""

    @classmethod
    def build(
        cls,
        provider: "Provider | None",
        settings: Settings,
        spent_month_eur: float,
        spent_import_eur: float = 0.0,
    ) -> "Ai":
        """The AI for one recognition: the provider (None: no key) and what is left of this
        import's and this month's budget. ``spent_month_eur`` includes this import."""
        budget = Budget(
            settings.ai_max_eur_per_import - spent_import_eur,
            settings.ai_max_eur_per_month - spent_month_eur,
            spent_import_eur,
        )
        return cls(
            provider,
            budget,
            settings.ai_eur_per_mtok_in,
            settings.ai_eur_per_mtok_out,
            state="connected" if provider is not None else "not_connected",
        )

    def ask(self, system: str, payload: dict[str, Any]) -> str:
        """Send one privacy-limited payload; raises ``AiUnavailableError`` instead of failing."""
        if self.provider is None:
            raise AiUnavailableError("not_connected")
        prompt = json.dumps(payload, ensure_ascii=False)
        worst = self._eur(len(system + prompt) // 3, MAX_TOKENS)
        if not self.budget.allows(worst):
            self.state = "limit_reached"
            raise AiUnavailableError("limit_reached")
        self.sent.append(payload)
        try:
            reply = self.provider.complete(system, prompt, MAX_TOKENS)
        except Exception as exc:  # any SDK, network or timeout error: fall back to rules
            self.state = "error"
            raise AiUnavailableError("error") from exc
        self.budget.spend(self._eur(reply.input_tokens, reply.output_tokens))
        return reply.text

    def _eur(self, tokens_in: int, tokens_out: int) -> float:
        return tokens_in / 1e6 * self.eur_per_mtok_in + tokens_out / 1e6 * self.eur_per_mtok_out


# --- what may leave the app -----------------------------------------------------------------


def anonymise(value: str) -> str:
    """The shape of a value without its content: letters become ``a``/``A``, digits ``9``
    (``JOB-24000`` → ``AAA-99999``, ``Laser cutting`` → ``Aaaaa aaaaaaa``)."""
    out = re.sub(r"[A-Z]", "A", value)
    out = re.sub(r"[^\W\d_A]", "a", out)
    return re.sub(r"\d", "9", out)[:40]


def examples(values: Iterable[str]) -> list[str]:
    """At most 5 example values, each only as its shape: enough to tell a date from a code or
    an amount, nothing of the content (a customer or product name never leaves)."""
    shapes = sorted({anonymise(v) for v in sorted(v for v in values if v)[:50]})
    return shapes[:MAX_EXAMPLES]


@dataclass
class OpenColumn:
    table: str
    """File name, or ``file#sheet``."""
    role: str
    column: str
    values: frozenset[str]
    fields: list[str]
    """Fields of the table's role still free: the only answers accepted."""


def privacy_payload(columns: list[OpenColumn]) -> dict[str, Any]:
    """Everything one call sends. Personal columns never get here: they are dropped on read."""
    return {
        "columns": [
            {
                "table": c.table,
                "table_holds": c.role,
                "column": c.column,
                "examples": examples(c.values),
                "fields": c.fields,
            }
            for c in columns[:MAX_COLUMNS]
        ]
    }


# --- column suggestions --------------------------------------------------------------------

COLUMN_SYSTEM = (
    "You help a manufacturing plant map its own data export to a standard model. For each "
    "column you get its table, what the table holds, the column name, up to 5 example values "
    "(numbers and letters may be masked as 9 and a/A) and the fields it may be. Answer only "
    'with JSON: {"suggestions": [{"table": ..., "column": ..., "field": one of its '
    'fields or null, "certainty": "likely" or "unsure", "reason": one short sentence '
    "in plain English}]}. Use null when you cannot tell. Never invent fields."
)


@dataclass
class AiColumnSuggestion:
    table: str
    column: str
    target: str
    sure: Literal["likely", "unsure"]
    reason: str


def suggest_columns(ai: Ai, columns: list[OpenColumn]) -> list[AiColumnSuggestion]:
    """AI suggestions for the open columns; only answers that name an allowed field of an
    asked column are kept. Raises ``AiUnavailableError`` when the AI cannot be used."""
    if not columns:
        return []
    text = ai.ask(COLUMN_SYSTEM, privacy_payload(columns))
    allowed = {(c.table, c.column): set(c.fields) for c in columns[:MAX_COLUMNS]}
    out = []
    seen: set[tuple[str, str]] = set()
    for item in _suggestions(text):
        key = (str(item.get("table")), str(item.get("column")))
        target = item.get("field")
        if key in seen or key not in allowed or target not in allowed[key]:
            continue
        seen.add(key)
        sure: Literal["likely", "unsure"] = (
            "likely" if item.get("certainty") == "likely" else "unsure"
        )
        reason = re.sub(r"\s+", " ", str(item.get("reason") or "")).strip()[:200]
        out.append(AiColumnSuggestion(key[0], key[1], str(target), sure, reason))
    return out


def _suggestions(text: str) -> list[dict[str, Any]]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    items = data.get("suggestions") if isinstance(data, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
