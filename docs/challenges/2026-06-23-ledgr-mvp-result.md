# ledgr MVP — Result Spec Challenge (result mode)

Artifact challenged: [docs/specs/2026-06-23-ledgr-mvp.md](../specs/2026-06-23-ledgr-mvp.md)

## Context gathered

**What is it?** A result spec for `ledgr`, a Python CLI (pre-implementation) that reads a
plain-text ledger of buy-only transactions for CAD-listed securities and reports current
value and annualized money-weighted return (XIRR), per holding and in aggregate, using a
live yfinance price lookup.

**What does it touch?** A ledger-line parser, a yfinance price-fetch step, an XIRR
root-finder (explicitly required to avoid scipy/numpy), and a stdout table formatter.
No persisted state — every run is a fresh read + fresh fetch + fresh compute.

**What does success look like?** All 11 closeness checks in the spec pass: correct table
output, correct per-ticker and aggregate XIRR, live price fetch, fail-loud on malformed
lines / unresolvable tickers / empty ledgers, no scipy/numpy dependency, working `uv run`
entrypoint and `--help`.

## Assumptions made during this challenge

- The user's real ledger will eventually include at least one bond-like instrument
  (inferred from the original conversation's framing: "bond or ETF or something").
- The user is the sole operator of their own ledger file, hand-edited over a long period
  (months to years), not a shared or programmatically generated file.
- yfinance's `fast_info.currency` (or `info["currency"]`) field is available on the same
  API call already needed for price — not independently verified against the live API,
  inferred from general yfinance API shape.

## Frame

It is six months from now. We achieved the result exactly as specified — every closeness
check passed at ship time — and the work has failed regardless. Looking back to
understand why.

## Raw failure reasons

1. Dividend/coupon exclusion guts bond accuracy — a bond's total return is mostly coupon
   income, not price appreciation; excluding distributions (an explicit non-goal) makes
   `ledgr` report near-zero or negative yield on a bond performing exactly as expected.
2. No sell support means the ledger goes stale the first time the user rebalances — the
   day they sell a holding there's no way to represent it, and the report keeps showing
   phantom quantity.
3. Silent currency wrongness — no currency field exists to validate a ticker's actual
   listing currency against the CAD assumption; a USD ticker entered by habit produces
   confidently wrong numbers, not an error.
4. One bad line blocks the entire report — fail-loud-on-any-malformed-line means a single
   old, previously-unvalidated typo discovered months later blacks out the whole report.
5. The closeness checks never exercise the XIRR root-finder's actual hard case — check 5
   only validates a single-buy closed-form reduction (no iteration at all); no check
   exercises multiple, unevenly-spaced buys where a scipy-free Newton's-method/bisection
   implementation is most likely to fail to converge.
6. yfinance flakiness vs. permanent unresolvability are conflated — a transient lookup
   hiccup triggers the same fatal, run-stopping error as a genuinely bad ticker.
7. The "no scipy/numpy" constraint is checkable but gameable — closeness check 11 inspects
   direct `pyproject.toml` dependencies only; a small XIRR package could pass the literal
   check while transitively pulling in numpy/scipy.

No out-of-mode (plan-level) findings were generated — all seven reasons indict the
specified destination itself (wrong target, under-specified check, missing constraint),
not the path to building it.

## Deep-dive: dividend/coupon exclusion guts bond accuracy

**Failure story.** Six months in, a user loads a ledger mixing `XEQT.TO` equity buys with
`XBB.TO` bond-fund buys. The table prints clean; closeness checks 1–11 all pass exactly as
written. The bond row shows Yield near zero, sometimes negative, even though the bond fund
has been paying its coupon on schedule and trading near par the whole time. Closeness
check 2 computes XIRR strictly from buy cash flows and one terminal mark-to-market — the
exact formula in the spec, executed exactly as specified. But a bond's total return is
mostly coupon, not price drift toward par; with distributions excluded by the non-goals
section, the cash-flow series ledgr feeds into XIRR is missing the majority of the bond's
actual return. The tool isn't buggy — it's accurate to a formula that excludes the
dominant return mechanism of the asset class in the product's own name.

The failure surfaces socially: a user holding `XBB.TO` says the yield number is "obviously
wrong," citing a brokerage statement showing healthy total return. The non-goals section
is technically correct and useless to anyone holding bonds. Trust in the whole TOTAL row
erodes — if bonds are silently wrong, why trust the equity numbers either?

**Underlying assumption.** XIRR-on-price-only is meaningful for any CAD-listed security,
when it is only meaningful for instruments whose total return is dominated by price
change.

**Early warning signs.**
- No closeness check ever runs the formula against a bond ticker and compares to that
  bond's published yield-to-maturity or trailing distribution yield.
- The spec's own example ledger includes `VAB.TO` (a bond ETF) purely for table-formatting
  demonstration, never to validate the Yield column against any external bond benchmark.

## Deep-dive: no sell support stales the ledger

**Failure story.** Every closeness check is green at ship date. Two months in, the user
sells half their `XEQT.TO` position to rebalance into `VAB.TO`. They open the ledger
looking for a `sell` line — there isn't one; the grammar has no disposal verb. They try
commenting out the original buy line with `#`, which deletes cost basis for shares they
still partially hold, corrupting the cash-flow series in the other direction. They settle
on leaving the buy lines as-is, the only move the format allows. `ledgr` keeps reporting
the full pre-sale quantity, because closeness check 1 only ever validated "quantity held"
against the buy lines themselves — there was never a check for "quantity still held after
disposal," because disposal doesn't exist in the model. Current Value for `XEQT.TO` is now
systematically overstated; the TOTAL row inherits the same overstatement.

The failure isn't a bug — checks 6/7/8 all still pass, the parser is correct for the
grammar it has. The grammar stopped matching the user's actual portfolio the moment a
real-world action (rebalancing) fell outside "buy-and-hold," which the spec named as a
non-goal rather than a deferred requirement.

**Underlying assumption.** "Buy-and-hold" describes how the user manages their portfolio,
when it only describes the transaction type the tool parses — real holders rebalance.

**Early warning signs.**
- Ledger files in the wild accumulate `#`-commented-out buy lines (an undocumented manual
  workaround for "I sold this").
- Issue/support requests asking "how do I record a sale" or "why doesn't TOTAL match my
  brokerage statement" appear within weeks of any user holding past one rebalance cycle.

## Deep-dive: silent currency wrongness

**Failure story.** Month two: the user copy-pastes a buy line from a US brokerage
statement — `buy VOO 15 @ 410.22 on 2024-11-03` — same grammar as every other line, no
entry friction. The parser checks shape only; `VOO` matches the ticker regex fine.
yfinance resolves `VOO` without complaint — it's real and heavily traded, just listed on
NYSE Arca, not the TSX. Closeness check 7 (unresolvable ticker → fatal) never fires,
because the ticker *is* resolvable. None of the checks construct a USD ticker, so this path
was never exercised pre-ship.

The real damage lands at print time: yfinance returns `VOO`'s price in USD, `ledgr` treats
it as CAD per spec convention, and cost basis sits in the same column as CAD-denominated
rows. The TOTAL row sums CAD and USD cost basis as if both were CAD; per-ticker and
portfolio XIRR blend a ~35% phantom currency swing into what looks like a return number.
Nothing crashes, nothing prints red — the table renders with the same formatting
confidence as every correct row before it. That's what makes it dangerous: no error
signature to grep for.

**Underlying assumption.** "Every ticker I'll ever type is CAD-listed" stays true forever,
when the actual enforcement of that fact is zero — it's a comment in the user's head, not
a check in the code.

**Early warning signs.**
- A ledger line where the ticker has no CAD-exchange suffix (`.TO`/`.V`/`.NE`/`.CN`) —
  grep the ledger for bare-letter tickers.
- yfinance's returned `info["currency"]` / `fast_info.currency` for a resolved ticker is
  not `"CAD"` — available from the same API call already used for price, unused by the
  spec's current design.

## Deep-dive: one bad line blocks the entire report

**Failure story.** The ledger lives in `~/finance/ledgr.txt`, 50 lines, hand-edited across
three years of paydays. The user adds a new buy and fat-fingers the date
(`2026-13-23`). Per closeness check 6 the tool exits non-zero, names the line, quits —
that part works as designed.

The real failure shows up two weeks earlier: the user wanted a portfolio check before
rebalancing, ran `ledgr`, and got the same kind of error — this time on a typo from eight
months ago that had sat silently in the file because nothing had ever validated it until
the moment something needed the whole table. The ledger had been "working" by accident: no
run had touched that line since it was written. The first run that did treated a stale,
long-buried typo exactly like a fresh one — total report blackout, zero visibility into 49
correct holdings, on a day the user specifically wanted current value before trading. The
brainstorm conversation chose "fail loudly" reasoning about a single bad *new* entry caught
immediately after typing it; nobody modeled the file as an accreting artifact where a
defect from buy #12 surfaces, at maximum severity, during the read for buy #50.

**Underlying assumption.** Malformed lines get caught near the moment they're written, not
discovered months later when the whole file is re-read for an unrelated holding.

**Early warning signs.**
- No "validate on save" / "lint the ledger separately from running it" path exists —
  absence means zero error-catching happens until the user actually needs the report.
- Time-to-first-run-after-edit exceeds zero in the normal workflow (lines accumulate via a
  text editor, not `ledgr` itself, before the next invocation) — that gap is exactly where
  a stale typo waits undetected.

## Deep-dive: XIRR checks never exercise the hard case

**Failure story.** Check 5 ships green because it isn't really testing the root-finder —
`(current_value/cost_basis)^(1/years) - 1` is algebra, not iteration. The Newton's-method
implementation written to satisfy checks 1–3 never gets a single assertion against a
known-correct multi-flow answer; those checks only assert *shape* (right columns, right
rows), not *value*. Six months later a user loads a real ledger: a position bought in three
unevenly-spaced tranches, one during a 40% drawdown, now sitting near break-even. The
aggregate cash-flow function has a near-flat region around the root — Newton's derivative
term shrinks toward zero, the iterate overshoots, and the implementation either oscillates
forever (no convergence guard catches it, because nobody wrote the adversarial case to know
what "stuck" looks like) or silently returns after a fixed iteration cap with an answer
wrong by 20 points. The TOTAL row prints a confident, plausible-looking percentage. Nothing
in the tool signals doubt.

The deeper failure: the spec's own constraint section flagged the lightweight root-finder
as the risky, custom-built piece — the one explicitly not outsourced to scipy — yet the
closeness checks budgeted zero verification effort against the one case that breaks
lightweight root-finders (near-zero or deeply negative aggregate return, irregular
cash-flow spacing).

**Underlying assumption.** The single-buy closed-form check was assumed to be a proxy for
root-finder correctness, when it exercises no root-finding at all.

**Early warning signs.**
- No closeness-check fixture has ≥2 buys at different dates with a numerically asserted
  expected XIRR value (not just "a number prints").
- A synthetic ledger with deliberately offsetting buys (deep loss + deep gain, irregular
  dates) has never been run through the implemented root-finder pre-ship with iteration
  count / convergence flag inspected.

## Deep-dive: yfinance flakiness conflated with permanent unresolvability

**Failure story.** Three weeks post-ship, a user runs `ledgr` on a 40-line ledger covering
eleven tickers — the same file they've run successfully for a month. It exits non-zero:
`Error: unresolvable ticker XEQT.TO`, their largest holding, fetched fine yesterday. They
re-run it twice, get the same error, and spend twenty minutes diffing the ledger against a
backup before it works again an hour later.

What happened: yfinance, scraping Yahoo's undocumented endpoints, hit a rate-limit window
or a transient malformed response — the exact failure mode the spec's own non-goals
section already acknowledges ("no SLA, can break if Yahoo changes their site"). Inside the
code that produced the same signal as a delisted ticker: `None` price, an exception, or an
empty dataframe. Closeness check 7 was written, and passed at ship time, by testing exactly
one scenario — a genuinely bad ticker — never a live API hiccup, because there's no way to
provoke Yahoo's flakiness on demand in a test. The check's wording, "a ticker yfinance
cannot resolve," reads as one condition but is actually two unrelated ones wearing the same
exception type.

The real damage isn't the crash — it's what the crash trains the user to do. After the
third unexplained failure, they stop trusting the tool's "no" at face value and start
blanket-retrying every error, including the one time a ticker really was mistyped. The
tool's entire pitch — "tell me the real number right now" — depends on its errors being
informative.

**Underlying assumption.** A single API call's failure always means the same thing, so one
error path can serve both "this ticker will never resolve" and "Yahoo didn't answer this
time."

**Early warning signs.**
- The same ticker fails on run N and succeeds on run N+1 with no ledger change between
  runs.
- Failure rate on a fixed, known-good ticker list exceeds 0% over a week of scheduled runs
  — any nonzero rate on tickers verified to exist is pure transient noise.

## Deep-dive: "no scipy/numpy" constraint is gameable

**Failure story.** Implementation lands. The dev reaches for a PyPI XIRR convenience
package instead of hand-rolling Newton's method — not `pyxirr` (Rust-backed, genuinely
zero extra runtime dep) but a pure-Python finance utility that wraps `scipy.optimize`
under the hood. `pyproject.toml` gets one new line; `uv sync` pulls it down; nobody reads
`uv.lock`. Closeness check 11 runs exactly as written — grep `pyproject.toml`, no `scipy`,
no `numpy` — green. Six weeks later someone tries to vendor `ledgr` into a constrained
environment (a Lambda layer, an Alpine container, an offline analyst box) and the install
drags in scipy's compiled BLAS/LAPACK wheels — tens of MB of platform-specific binaries,
the exact thing "lightweight" was supposed to prevent.

The root failure: the check encoded a verification *procedure* ("inspect pyproject.toml")
instead of the *property* it stood in for ("small install footprint"). The procedure was
satisfiable without the property holding.

**Underlying assumption.** Direct dependency list and total install footprint were treated
as the same thing to verify, when only the lockfile's full resolved closure tells the truth
about footprint.

**Early warning signs.**
- `uv.lock` (or `pip show <pkg> --requires` / `pipdeptree`) lists scipy or numpy anywhere
  in the resolved tree, even though `pyproject.toml`'s `dependencies` array doesn't name
  them.
- `du -sh .venv` (or wheel download size during `uv sync`) jumps by tens of MB the moment
  the XIRR package is added.

## Synthesis

### Most likely failure

**Dividend/coupon exclusion gutting bond accuracy (#1).** Unlike the other failure modes,
which trigger only on an edge-case event (a sale, a USD ticker, a stale typo, a rare
cash-flow shape), this one fires on *every single run* that includes a bond holding — and
the user's own framing of the tool ("bond or ETF or something") makes a bond entry close
to certain, not hypothetical. It's the failure most likely to be hit first and hit
repeatedly.

### Most dangerous failure

**Silent currency wrongness (#3).** Every other failure mode either crashes loudly
(checks 4, 6) or produces a number the user can sanity-check against a brokerage statement
and recognize as wrong (#1, #2, #5). Currency wrongness produces a confidently formatted,
internally consistent table that is simply incorrect by tens of thousands of dollars, with
no error signature to grep for and no visual cue that anything is off. It's the one mode
that could survive undetected for months and inform a real financial decision.

### Hidden assumption

Across #1, #5, and #3, the same pattern recurs: **the closeness checks validate that the
calculation matches its own formula, not that the output matches financial reality.**
Check 2/3 verify XIRR is computed correctly from the cash flows it's given — they never ask
whether those cash flows are the *right* ones (missing distributions) or *correctly priced
in the right currency*. Check 5 verifies the formula reduces correctly for one buy — it
never asks whether the formula converges for the buy patterns real portfolios actually
have. The spec specified "compute X correctly" when the real ask was "tell me the truth
about my portfolio" — a gap closeness checks expressed in formula terms can't catch.

### Revised artifact — concrete changes

1. **Bond/distribution limitation must be visible, not buried in non-goals** (failure #1).
   Add closeness check: the Yield column header or an adjacent note in the table output
   states explicitly that yield reflects price appreciation only and excludes
   distributions/coupons — so the number is never mistaken for total return. Cheap,
   doesn't expand scope, prevents the silent-misread failure mode.

2. **Currency must be validated, not assumed** (failure #3). Add closeness check: for each
   resolved ticker, the tool checks yfinance's reported listing currency against CAD and
   fails loudly (consistent with the existing "fail loud" convention) if it doesn't match
   — same severity as an unresolvable ticker, zero new scope (no FX conversion needed,
   just a guard).

3. **Malformed-line errors should batch, not trickle** (failure #4). Add closeness check: a
   ledger with multiple malformed lines reports every malformed line in one error output
   (not just the first), so a user fixes all defects in a single pass rather than
   discovering them one run at a time over months.

4. **XIRR root-finder needs a real multi-cash-flow correctness check** (failure #5). Add
   closeness check: a ledger with ≥3 buys at irregular dates, including a deep-drawdown-
   then-partial-recovery pattern, produces an XIRR matching an independently verified
   reference value within tolerance; and the root-finder must detect and report
   non-convergence rather than silently returning an unguarded iteration result.

5. **Transient vs. permanent price-fetch failure must be distinguished** (failure #6). Add
   constraint: a price-fetch failure is retried at least once (bounded, short backoff)
   before being classified "unresolvable"; the fatal error text must distinguish "no data
   returned after retry" from a malformed/unparseable response, so users aren't trained to
   distrust every error equally.

6. **"No scipy/numpy" must mean the resolved dependency graph, not just direct deps**
   (failure #7). Reword closeness check 11: the *resolved* dependency tree (`uv.lock`, or
   `uv tree` output) contains no scipy/numpy, not merely the direct `dependencies` array in
   `pyproject.toml`.

7. **No sell support is a genuine open scope question, not a quiet revision** (failure
   #2). This is the one finding big enough to need the user's call rather than a silent
   spec edit: either (a) pull minimal sell support into v1 scope now, given how likely and
   how damaging the staleness is, or (b) keep it parked, but add an explicit closeness
   check that the ledger format's documentation states the known limitation plainly
   ("disposals are not supported; selling a holding requires manually editing/removing the
   relevant buy line(s), which discards that cost-basis history") so the gap is a
   documented tradeoff, not a discovered one.

### Pre-execution checklist

1. Confirm with the user: pull minimal sell support into v1, or keep parked + documented
   (maps to failure #2 — the one true scope decision here).
2. Confirm yfinance actually exposes a per-ticker currency field reliably for CAD-listed
   tickers (`fast_info.currency` or `info["currency"]`) before committing to the currency
   guard as a closeness check (maps to failure #3) — this was an inference, not verified
   against the live API.
3. Before implementation, write the adversarial multi-buy XIRR test case (deep drawdown +
   recovery, irregular dates) and confirm a scipy-free root-finder converges on it — per
   the refactor-validate-premise discipline, prove the riskiest case before building the
   easy cases around it (maps to failure #5).
4. Decide the retry count/backoff for price-fetch transient-failure handling (maps to
   failure #6) — small enough to leave to planning, but the *existence* of a retry is now
   a spec-level constraint, not optional.
5. Decide whether "every malformed line reported at once" requires a two-pass parse
   (collect all errors, then report) or can be done in one pass with deferred reporting —
   left to planning, but the *batched-error* behavior itself is now spec-level (maps to
   failure #4).
