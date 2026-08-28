# Test data

Catalogue facts and the coefficients fitted from them. These files are the oracle: the
reference tests assert that fitting the points here reproduces the coefficients here, so a
change in either is a change in what the tool promises.

## Where the numbers come from

They describe IMI Hydronic Engineering balancing valves — STAD in DN10–50 and TA-BVS 243 in
DN65–250. What is republished is a numerical table of facts, never catalogue material: the
points and the coefficients, nothing else.

`valve_data_aquapresso.csv` is the table in use. It matches, line for line, the `BV_data` sheet
of the "IMI Aquapresso 1.01" workbook, regenerated in January 2026 when TA-BVS 243 replaced the
STAF range. The point tables are the input that produced it.

## The files

`STAD_DN10.csv` … `TA-BVS_DN250.csv` — 14 point tables, one per valve size.

- The first line is not a header of column labels: it carries the product name and the article
  number, in the catalogue's own spelling.
- Every following line is one point. **Column 1 is the valve setting `n [-]`; column 2 is
  `Kv [m³/h]`.**
- The polynomial runs the other way from the reading order: it answers "which setting gives
  this Kv", so column 2 is x and column 1 is y. Two things say so independently. On one point
  of one valve: the published `STAD DN10` coefficients evaluated at a Kv of `0.054` return
  `0.5053`, against the `0.5` the table lists for that end of the curve, while the same
  coefficients evaluated at `0.5` return `2.52` where the reverse reading would need `0.054` —
  47 times out. Across all fourteen valves the separation is measured by
  `test_the_curve_runs_from_kv_to_setting`, on each valve's worst point rather than its best.
  And the earlier result file of the legacy tool, which did carry Kv as a function of the
  setting, was superseded precisely by inverting the axes.
- STAD tables hold 701 points on a setting step of 0.005 — generated from a curve. TA-BVS
  tables hold 17 catalogue points — raw readings.
- TA-BVS tables write decimals with a comma, quoted: `"61,200"` is 61.2 m³/h. Read as a
  thousands separator it would put 61 200 m³/h through a DN65 valve.

`valve_data_aquapresso.csv` — the expected coefficients, one row per valve size, 14 rows under
one header line. Columns: `x6…x0` in the power basis, descending, then `name`,
`product_number`, `dn`, and the four range bounds `setting_max`, `setting_min`, `kv_max`,
`kv_min`. All 14 rows carry seven coefficients, so degree 6 is the legacy degree for this whole
family.

### The bound columns carry swapped names

In `valve_data_aquapresso.csv`, the columns named `kv_min` / `kv_max` hold the **setting**
range, and the columns named `setting_min` / `setting_max` hold the **Kv** range. For
`STAD DN10` the row reads `setting_max = 1.36`, which is a Kv in m³/h, and `kv_max = 4.0`,
which is a handwheel setting; a DN250 row puts 1170 in a column named for a setting. The names
stayed where they were when the legacy tool inverted its axes, and all fourteen rows are
crossed the same way — nothing here is a one-row slip.

The reader in `tests/legacy_data.py` corrects the names and leaves the numbers untouched, so
the mistake stops at the file boundary. Two measurements hold it in place: reading the columns
at face value turns all fourteen range tests red, and the values themselves are impossible the
other way round.

Anything that later writes this layout back out — an export shaped for the spreadsheet that
consumes it — has to decide whether to reproduce the legacy names or correct them. That is a
decision about the export, and it is not made here.

### One point in TA-BVS DN200 is wrong, and stays wrong

At a setting of 1.5 the table gives a Kv of 20.2, between 19.7 at setting 1 and 38.4 at
setting 2 — a step of 0.5 followed by a step of 18.2, where every other TA-BVS table rises
evenly. The value is exactly the one DN150 carries at the same setting, so it looks like a row
picked from the neighbouring file when the legacy tables were made.

**It must not be corrected.** The published coefficients were fitted through this point: fitting
the table as it stands reproduces them to a relative difference of 2.8e-12, while replacing the
point with an interpolated 27.0 moves the coefficients by 334%. The flaw is also visible in the
fit itself — the two points around it carry the largest residuals of the published curve on its
own data, -0.264 and +0.212, against 0.091 for the next worst.

What this repository asserts is parity with the numbers in use, and those numbers were computed
from this table, defect included. A correction here would turn a passing reference test red for
a reason no one would find.

## What this data is not

It is not a selection table. The `from kv` / `to kv` bounds that a selection table needs are
curatorial — they are chosen, not derived from the data — and they live in the spreadsheet that
consumes the export, not here.

Replacing these numbers with synthetic curves is **not** a single change, and it is worth being
clear about why. The coefficients were computed from these very points, so the two files are not
independent in origin — what is independent is the **implementation**: they were produced by the
legacy tool, and the test asserts that a different program, written from scratch, lands on the
same numbers. That is the whole value, and it is fragile in one specific way. Synthetic points
would need synthetic coefficients, and the only tool at hand to produce them is hydrofit itself —
at which point the test compares the code with its own output and proves nothing. Narrowing what
may be published would therefore mean fitting the replacement curves with something other than
hydrofit, not swapping a fixture.
