"""Budget ledger. Every metered call (initial, repair, critic, retry) reserves first.

A ledger can be persisted so a restarted batch keeps its consumed allowance.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from humour_engine.contracts.analysis import Budget


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def estimate_tokens(text: str) -> int:
    # conservative: ~3.5 chars per token, rounded up
    return max(1, -(-len(text) * 2 // 7))


@dataclass
class Reservation:
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


@dataclass
class BudgetLedger:
    budget: Budget
    price_per_mtok_in: float | None = None
    price_per_mtok_out: float | None = None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    cost_usd: float = 0.0
    cost_known: bool = True
    events: list[dict] = field(default_factory=list)

    def remaining_calls(self) -> int:
        return self.budget.max_model_calls - self.calls

    def reserve(self, input_tokens: int, max_output_tokens: int, *, retry: bool = False) -> Reservation:
        b = self.budget
        if self.calls + 1 > b.max_model_calls:
            raise BudgetExceeded("max_model_calls reached")
        if self.input_tokens + input_tokens > b.max_input_tokens:
            raise BudgetExceeded("max_input_tokens would be exceeded")
        out = min(max_output_tokens, b.max_output_tokens - self.output_tokens)
        if out <= 0:
            raise BudgetExceeded("max_output_tokens reached")
        cost = None
        if self.price_per_mtok_in is not None and self.price_per_mtok_out is not None:
            cost = (input_tokens * self.price_per_mtok_in + out * self.price_per_mtok_out) / 1e6
        if b.max_cost_usd is not None:
            if cost is None:
                raise BudgetExceeded("strict dollar cap requested but current pricing is unknown; stopped before charging")
            if self.cost_usd + cost > b.max_cost_usd:
                raise BudgetExceeded("max_cost_usd would be exceeded")
        # reserve the maximum; settle() replaces it with actuals
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += out
        if retry:
            self.retries += 1
        if cost is not None:
            self.cost_usd += cost
        else:
            self.cost_known = False
        self.events.append({"event": "reserve", "in": input_tokens, "out": out, "retry": retry})
        return Reservation(input_tokens, out, cost)

    def settle(self, r: Reservation, actual_in: int | None, actual_out: int | None) -> None:
        """Replace a reservation with measured usage. Unknown actuals keep the reservation."""
        if actual_in is not None:
            self.input_tokens += actual_in - r.input_tokens
        if actual_out is not None:
            self.output_tokens += actual_out - r.output_tokens
        if r.cost_usd is not None and actual_in is not None and actual_out is not None:
            new = (actual_in * (self.price_per_mtok_in or 0) + actual_out * (self.price_per_mtok_out or 0)) / 1e6
            self.cost_usd += new - r.cost_usd
        self.events.append({"event": "settle", "in": actual_in, "out": actual_out})

    def snapshot(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "retries": self.retries,
            "cost_usd": self.cost_usd if self.cost_known else None,
        }


class PersistentBudgetStore:
    """SQLite-backed batch budget so restarts never reset the spend allowance."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("create table if not exists budgets (run_id text primary key, budget text, state text)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def load(self, run_id: str, budget: Budget) -> BudgetLedger:
        with self._conn() as c:
            row = c.execute("select budget, state from budgets where run_id=?", (run_id,)).fetchone()
        if row is None:
            ledger = BudgetLedger(budget=budget)
            self.save(run_id, ledger)
            return ledger
        stored_budget = Budget.model_validate_json(row[0])
        if stored_budget != budget:
            raise ValueError("run budget differs from the stored budget; a new run id is required to change it")
        st = json.loads(row[1])
        return BudgetLedger(
            budget=stored_budget,
            calls=st["calls"],
            input_tokens=st["input_tokens"],
            output_tokens=st["output_tokens"],
            retries=st["retries"],
            cost_usd=st["cost_usd"] or 0.0,
            cost_known=st["cost_usd"] is not None,
        )

    def save(self, run_id: str, ledger: BudgetLedger) -> None:
        with self._conn() as c:
            c.execute(
                "insert into budgets(run_id,budget,state) values(?,?,?) "
                "on conflict(run_id) do update set state=excluded.state",
                (run_id, ledger.budget.model_dump_json(), json.dumps(ledger.snapshot())),
            )
