# ledgr MVP — Implementation Plan Challenge (plan mode)

Artifact challenged: [docs/plans/2026-06-23-ledgr-mvp.md](../plans/2026-06-23-ledgr-mvp.md)

## Context gathered

**What is it?** A 10-task TDD implementation plan for `ledgr`, building 7 modules
(`ledger.py`, `holdings.py`, `xirr.py`, `prices.py`, `report.py`, `table.py`, `cli.py`)
one per task, each test-first, wired into a CLI entrypoint.

**What does it touch?** Ledger text parsing, average-cost-basis math, a hand-rolled
scipy-free XIRR root-finder, live HTTP calls to Yahoo's chart endpoint via raw
`requests`, stdout table rendering, CLI exit codes.

**What does success look like?** The plan executed exactly as written, and six months
from now the spec's 16 closeness checks
([docs/specs/2026-06-23-ledgr-mvp.md](../specs/2026-06-23-ledgr-mvp.md)) still hold
against a real, growing, hand-edited ledger and Yahoo's live (and occasionally flaky,
rate-limited) API.

## Assumptions made during this challenge

- Yahoo's chart endpoint behaves the way it was observed to behave during planning
  (404 for unresolvable, JSON for everything else) — its rate-limiting response shape
  (429 with an error-shaped body) was inferred as plausible, not independently
  reproduced live, since provoking a real rate-limit on demand isn't practical.
- The user's real ledger will eventually include a short-holding-period, large
  percentage-gain position (a speculative buy held days, not years) — inferred from the
  result spec's "fractional shares are valid and common" framing plus ordinary portfolio
  behavior, not from a stated example.

## Raw failure reasons

1. The real Yahoo HTTP path is only exercised once, manually, in Task 8 Step 5 — never
   in the automated suite (every other test mocks `fetch_price`/the HTTP layer). API
   drift has no test to catch it before a real user hits it.
2. `cli.py`'s `main()` catches `(LedgerParseError, LedgerOversellError, LedgerPriceError,
   ValueError)` — a missing/nonexistent ledger path raises `FileNotFoundError` (an
   `OSError`, not caught), producing a raw traceback instead of the spec's clean
   fatal-error UX.
3. `prices.py` only special-cases HTTP 404 as "unresolvable." A 429 (rate-limited) or
   5xx response with a JSON error body falls through the same code path and gets
   misclassified as permanently unresolvable, with no retry — recreating the exact
   "transient vs. permanent conflated" failure the spec added a retry constraint
   specifically to prevent.
4. `xirr()`'s bracket is hardcoded to `[-0.999999, 100.0]` (max 10,000% annualized). A
   real short-holding-period spike can have a true XIRR outside that bracket — the
   solver misreports it as "no sign change" (a bracketing failure) rather than computing
   the legitimate, if extreme, rate.
5. `holdings.py`'s oversell `EPSILON = 1e-9` is far tighter than realistic
   floating-point/transcription drift from brokerage-statement copy-paste — a genuine
   full-sell can spuriously trigger `OversellError` on quantity noise nowhere near the
   spec's intended "sold more than you hold" case.
6. No task installs or runs `ruff`/`mypy` despite the repo's own `.gitignore` reserving
   cache directories for both — type errors in the `float | None` unions threaded
   through `report.py`/`table.py`/`cli.py` are only caught by the specific values the
   chosen tests exercise.

No out-of-mode (result-level) findings — all six indict the path (missing test
coverage, a code-level branching gap, an unvalidated numeric bound, an unvalidated
tolerance, missing tooling), not the destination the spec describes.

## Deep-dive: untested real Yahoo HTTP path

**Failure story.** Five months in, Yahoo restructures the chart endpoint response —
`meta.regularMarketPrice` is replaced by a different field, a known pattern in their
undocumented API's history. `fetch_price` does `price = meta["regularMarketPrice"]`,
gets a `KeyError`, and correctly raises `PriceFetchError` after one retry per the Task 5
contract. Nothing in CI notices: `tests/test_prices.py` builds its `_response()`
fixtures by hand with the old shape baked in; the mocks never know the real endpoint
changed. Every test stays green. Task 8 Step 5's smoke command ran once, months
earlier, against the old shape, then never again — it isn't part of any repeatable
job.

The user runs `ledgr ~/portfolio.txt` and gets a hard failure for every ticker, because
the "no silent skip/fallback" constraint does exactly what it was designed to do —
refuse to print a table on bad data. The tool is 100% broken for 100% of users, with
zero advance signal, because the only artifact that would have caught the drift (a real
HTTP call) was deliberately excluded from the automated suite.

**Underlying assumption.** The mocked fixture's shape in `test_prices.py` will continue
to match Yahoo's real, undocumented, versionless JSON response shape indefinitely, with
no mechanism re-checking that match after Task 8 ships.

**Early warning signs.**
- `git log -- tests/test_prices.py` shows the fixture payload hasn't changed since
  Task 5's commit, while `PriceFetchError` counts rise in the field.
- No test marked for live/real-network execution ever hits
  `query2.finance.yahoo.com` post-merge.

## Deep-dive: missing-file traceback gap

**Failure story.** Task 8 lands clean: `--help`, a valid ledger, and a malformed line
all pass against `except (LedgerParseError, LedgerOversellError, LedgerPriceError,
ValueError)`. Task 9's fixtures add oversell and empty-ledger cases, both already
covered via `ValueError`. Task 10's self-review cross-references checks 6/7/8/13/14 to
specific tests — but the spec never named "missing ledger file" as a closeness check,
so the self-review had nothing pointing at it.

Three weeks later a user fat-fingers the path — `legder.txt` instead of `ledger.txt` —
and runs `uv run ledgr legder.txt`. `Path(...).read_text()` raises `FileNotFoundError`,
a subclass of `OSError`, not caught by `main()`'s except tuple. Python prints a full
traceback straight to the terminal — the exact outcome the spec's fatal-error
constraint was written to prevent. Every test that calls `main()` first writes a real
file via `tmp_path`, so this branch is structurally unreachable from the suite.

**Underlying assumption.** The fatal-condition list in the spec's Constraints
("malformed line, oversell, unresolvable ticker, non-CAD currency, empty ledger") was
silently treated as exhaustive, when it only enumerates parse/business failures and
omits the I/O boundary that runs before any of that logic executes.

**Early warning signs.**
- Every `main()` call in the test suite constructs a real file first — zero tests pass
  a nonexistent path.
- The except tuple in `cli.py` contains no `OSError`/`IOError` — visible by reading
  `main()` alone, no test run needed.

## Deep-dive: 429/5xx misclassified as unresolvable

**Failure story.** Six weeks post-launch, `ledgr` throws `UnresolvableTickerError` for
tickers that are unambiguously valid. Users rerun seconds later and it works. The
pattern correlates with refresh frequency: polling multiple holdings back-to-back trips
Yahoo's rate limiter, which returns HTTP 429 with a `chart.error`-shaped JSON body —
same shape as a genuine "ticker not found" response. `fetch_price` only checks
`status_code == 404`; everything else, including 429 and 5xx, falls through to the
`resp.json()` block, finds `chart.get("error")` truthy, and raises
`UnresolvableTickerError` immediately — zero retries, despite `RETRY_COUNT = 1` sitting
unused for this path.

The bug shipped clean because Task 5's tests only exercise two shapes: a 404
unresolvable, and a transient network *exception* that retries. Nobody wrote a test for
"non-404 status with an error-shaped body" — the exact case the spec's retry
constraint was written to prevent, now reintroduced as a structural code bug instead of
a missing spec constraint.

**Underlying assumption.** A `chart.error`-shaped JSON body only ever accompanies a
genuinely nonexistent ticker, never a transient/rate-limited response — so status code
404 is the sole gate needed to distinguish permanent from temporary failure.

**Early warning signs.**
- No test combines a non-404, non-200 status code with an error-shaped JSON body.
- `UnresolvableTickerError` rate spikes correlate with request volume/burstiness rather
  than specific tickers, and resolve on manual retry.

## Deep-dive: XIRR bracket too narrow

**Failure story.** Task 4 lands clean: five tests pass. The only bracket-failure test
exercises a position still underwater after a year — one shape of failure. Nobody
writes the case the bracket math can't handle: a position bought days ago, up
several-fold. `_npv(hi=100, flows)` discounts the terminal payoff by `(1+100)^(t/365)`
with `t` near zero — the exponent is a fraction near 0, so the discount barely bites,
and `f_hi` stays the same sign as `f_lo`. The solver raises `XIRRError("no sign change
in cash flows; cannot bracket a root")` — the same exception text a genuinely broken
ledger row would raise.

Five months later it fires in production: a speculative buy is up 340% within days, and
the CLI dies with "cannot bracket a root." This is a legitimate, closed-form-computable
XIRR that the bracket is too narrow to reach, indistinguishable in the error message
from genuine non-convergence. The closeness check (16) wanted explicit non-convergence
reporting; Task 4's tests confirm the message exists, not that the bracket covers the
legitimate domain.

**Underlying assumption.** `hi=100.0` was taken for granted as "obviously enough
headroom," without checking it against short-elapsed-time single-buy cash flows where
the closed form already proves rates can exceed it.

**Early warning signs.**
- Zero test fixtures with `t < ~30 days` between a buy and the valuation date.
- `XIRRError` carries one message template for two semantically different failures (bad
  data vs. bracket-too-narrow).

## Deep-dive: EPSILON too tight for real quantities

**Failure story.** Task 3 lands clean: four tests green, the only oversell test uses a
50% overshoot. `EPSILON = 1e-9` is reused from the planning-time verification script's
root-finder tolerance, pasted into `holdings.py` without re-deriving it for the new
domain. Five months later the user sells out of a holding entirely; their brokerage
statement's fractional-share quantity differs from an earlier hand-typed buy line by
~8e-8 of rounding drift — 80x past `EPSILON`. The full-sell trips `OversellError` on
noise, not a real oversell, and the tool refuses to print a table by design.

The user has no resolution path beyond reverse-engineering which ledger entry to retype
with a fudged digit until the float math clears `quantity + EPSILON` — editing the
ledger to lie about what they bought, to satisfy an internal tolerance they don't know
exists.

**Underlying assumption.** A tolerance validated against pure floating-point arithmetic
in a root-finder is also valid for human-transcribed brokerage data entered by hand
over years.

**Early warning signs.**
- `EPSILON` is a single shared-looking constant value with no comment distinguishing
  "numerical convergence tolerance" from "real-world entry-precision tolerance."
- Zero test cases where sell quantity is close-but-not-exact to held quantity.

## Deep-dive: no lint/typecheck task

**Failure story.** Five months later a contributor threads a new option through
`report.py` and one branch assigns `current_price = "pending"` (a string) where the
dataclass declares `float | None`. `table.py`'s `_format_row` does
`f"{r.current_price:.2f}"` on the non-`None` branch; on a `str` that's a `TypeError`,
but only for the new path. Every existing test constructs `TickerReport` with `None` or
a real `float` — none exercises the new branch, so the full suite stays green and ships.
`mypy --strict` would have flagged the assignment immediately from the signatures
alone, zero test inputs required — but `mypy` was never added; Task 1 added `requests`
and `pytest` only.

**Underlying assumption.** Test coverage of today's specific values is being treated as
equivalent to type-correctness across all future code paths.

**Early warning signs.**
- `.mypy_cache/`/`.ruff_cache/` sit in `.gitignore` from project inception with no
  corresponding `[tool.mypy]`/`[tool.ruff]` config or dev dependency.
- Task 10's self-review checks tests against spec checks, never asks what static
  analysis would catch that tests don't.

## Synthesis

### Most likely failure

**429/5xx misclassification (#3).** Yahoo's chart endpoint is well known for
undocumented, aggressive rate-limiting. Any user with more than a couple of tickers,
refreshing more than occasionally, hits this within weeks — not an edge case, the
default behavior of the only HTTP code path the tool has.

### Most dangerous failure

**Untested real Yahoo path (#1).** A single response-shape change makes the tool 100%
non-functional for 100% of users instantly, with zero test in the suite — fully
mocked — ever catching it before release. Unlike #3 (intermittent, self-resolves on
retry), this is total and silent until a real user hits it.

### Hidden assumption

Every test across this plan — `xirr.py`, `holdings.py`, `prices.py`, `cli.py`, and the
missing type-checker — validates the implementation against the specific values the
test author already imagined, never against the actual external system (Yahoo's real
API) or input distribution (real users' real ledgers, real floating-point drift, real
extreme-but-legitimate cash flows) it ultimately serves. This is the same pattern the
result-mode challenge already surfaced ("closeness checks validate that the calculation
matches its own formula, not that the output matches financial reality"), recurring at
the plan level as "tests validate that the code matches the test author's imagined
inputs, not the actual external system's behavior."

### Revised artifact — concrete changes

1. **Branch on status code, not just exception type, in `prices.py`** (failure #3).
   Treat any non-200, non-404 response (429, 5xx) as retry-eligible using the existing
   `RETRY_COUNT` budget, not a special "malformed response" path. Only a confirmed
   `404` short-circuits to `UnresolvableTickerError`. Add
   `test_fetch_price_retries_on_429_then_succeeds` and
   `test_fetch_price_raises_price_fetch_error_on_persistent_429`.

2. **Convert the one-off manual smoke into a named, marked live test** (failure #1).
   Add a `tests/test_prices_live.py` test marked `@pytest.mark.live`, excluded from the
   default `pytest` run via `addopts = "-m 'not live'"`, hitting the real Yahoo endpoint
   for a known-good ticker. Documented in the README as a manual pre-release check
   (not wired into default CI, to avoid flakiness from a third-party rate limiter on
   every contributor run).

3. **Catch `OSError` in `cli.py`'s `main()`** (failure #2). Add it to the except tuple
   alongside the existing custom exceptions; add
   `test_main_exits_nonzero_on_missing_ledger_file`.

4. **Widen the XIRR bracket** (failure #4). Raise `hi` from `100.0` to `1000.0`
   (100,000% annualized) — comfortably covers any plausible short-holding-period gain
   while keeping the existing safeguarded Newton/bisection solver as the single code
   path (no closed-form special-case, avoiding a second way to compute the same value).
   Add a test with a multi-day holding period and a large gain confirming a real rate is
   returned, not `XIRRError`.

5. **Widen and rename the oversell tolerance** (failure #5). Replace
   `EPSILON = 1e-9` in `holdings.py` with `QUANTITY_EPSILON = 1e-6` — comfortably
   absorbs realistic fractional-share transcription drift (4-6 decimal places is
   typical) while staying far below any genuine oversell. Add a test with a
   close-but-not-exact full-sell (off by `5e-7`) that succeeds rather than raising
   `OversellError`.

6. **Add `ruff` + `mypy` to Task 1, run both in Task 10** (failure #6). Dev
   dependencies only, default (non-strict) config — enough to catch the kind of
   type-incompatible assignment in the deep-dive, without MVP-inappropriate friction
   from `--strict`.

### Pre-execution checklist

1. Confirm the 429-retry change shares `RETRY_COUNT` with the existing
   exception-retry path rather than getting a separate budget (maps to #3) — simpler,
   one retry budget total per fetch.
2. Confirm the live test stays excluded from default `pytest`/CI runs and is documented
   as a manual pre-release check only (maps to #1) — avoids flakiness from depending on
   a third-party rate limiter in every contributor's test run.
3. Confirm `hi=1000.0` is an acceptable bracket ceiling, or supply a more
   defensible value before it's hardcoded into a test fixture (maps to #4).
4. Confirm `QUANTITY_EPSILON = 1e-6` is an acceptable tolerance before it's hardcoded
   into a test fixture (maps to #5) — too loose risks masking a small genuine oversell.
5. Confirm non-strict `mypy` (vs. `--strict`) is the right default for this MVP (maps
   to #6).
