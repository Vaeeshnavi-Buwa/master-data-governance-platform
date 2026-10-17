# Master Data Governance Platform

## What is this project?

Big manufacturing companies keep a record in SAP for every material they buy or make and every supplier they buy from. This is called master data. When it is wrong, real things go wrong too: orders get placed for the wrong quantity, shipments get stuck at customs, and the same item ends up saved under two or three different codes.

I work with this kind of data in my job, so I wanted to build something that:

1. finds the mistakes automatically,
2. finds duplicate records (the same material or supplier saved more than once),
3. gives every mistake an owner, and
4. puts a rupee value on what the mistakes cost.

**Live dashboard:** [open here](https://vaeeshnavi-buwa.github.io/master-data-governance-platform/dashboard/standalone.html)

## The data

Real company data can't be shared, so I created my own. I wrote a Python script that builds a realistic SAP extract for a made-up packaging company called Kestrel Flexibles:

- 8 factories (India, Thailand, Poland, Germany, USA, Mexico)
- about 50,000 materials and 12,000 suppliers, around 500,000 rows in total
- the same table and field names SAP uses (MARA, MARC, MAKT, MBEW for materials and LFA1, LFB1, LFBK for suppliers)

While building the data, I planted mistakes and duplicates on purpose and kept a list of every one. Because I know the right answer, I can check exactly how many of them my checks catch and how many they get wrong.

Kestrel Flexibles is not a real company. None of this data comes from my employer.

## What I did

**Step 1: Built the data** (`src/01_generate_data.py`)
Created the tables above with planted mistakes, for example missing tax numbers, a reorder point of zero, wrong units and copied bank details.

**Step 2: Checked each file before using it** (`src/02_validate_landing_gx.py`)
I used Great Expectations to check basics like missing IDs, codes that aren't allowed and row counts. If a file fails a serious check, the pipeline stops, so wrong numbers never reach the dashboard.

**Step 3: Found duplicate records** (`src/03_entity_resolution.py`)
This was the hardest part. See the next section.

**Step 4: Wrote 26 data quality rules** (`dbt_mdg/`)
Each rule checks one thing, for example "finished goods must have a valid barcode". Each rule has an owner (Procurement, Finance and so on), a severity and a deadline for fixing. The rules run in dbt on a DuckDB database and give a score for every factory and every owner, month by month.

**Step 5: Estimated the cost** (`src/05_cost_model.py`)
I linked each open mistake to the stock, purchases and shipments it affects. I didn't know the exact cost of each type of mistake, so I gave each one a low, likely and high value and ran 20,000 simulations (Monte Carlo). That gives a range instead of one number that looks more certain than it is.

**Step 6: Built a dashboard** (`src/06_build_dashboard.py`)
One HTML page that shows the scores, trends, owners and costs.

## The duplicate problem: what didn't work and what did

My first attempt used **fuzzy matching**. It compares two descriptions and gives a similarity score out of 100, and anything above 90 counts as a duplicate. It's the most common way people try to find duplicates.

It didn't work. In packaging, many materials that are genuinely different have almost the same description:

```
FILM BOPP MET 20MIC 1020MM
FILM BOPP MET 25MIC 1020MM
```

These two are 96% similar as text, but they are different products. Fuzzy matching flagged them as duplicates. Out of every 1,000 pairs it flagged, only about 1 was a real duplicate, which came to 1.23 million false alarms. Nobody can review that many.

So I changed the approach in two ways:

1. **Cleaned the text first.** I expanded abbreviations (`PLN` to `PLAIN`, `LAMI` to `LAMINATE`), wrote units the same way every time (`20 MICRON`, `20U` and `20MIC` all become one form) and fixed common typos. I treated numbers separately from words, because a different number usually means a different product.
2. **Used Splink instead of a single score.** Splink compares each field separately (the words in the description, the numbers in the description, material group, manufacturer part number and barcode) and learns from the data how much each match or mismatch matters. It gives a probability that two records are the same.

I also didn't trust one cut-off for everything:

- **0.95 and above:** merged automatically
- **between 0.5 and 0.95:** sent to a person to check
- **below 0.5:** not a duplicate

One thing surprised me. At first I included weight and unit of measure in the model, and the results were bad (13% precision). Within one material group these fields are nearly the same for everything, so they were just repeating information the model already had. When I removed them, precision went up to 99.4%.

## Results

**Duplicates**

| | Fuzzy matching | My approach (Splink) |
|---|---|---|
| Materials: share of flagged pairs that were real duplicates | 0.1% | 99.4% |
| Materials: share of real duplicates found | 62.8% | 97.4% |
| Suppliers: share of flagged pairs that were real duplicates | 15.0% | 100% |
| Suppliers: share of real duplicates found | 60.4% | 97.6% |

- 2,282 groups of duplicate materials merged into one clean record each
- ₹10.6 Cr of stock was sitting on duplicate material codes

**Data quality** (the made-up company "fixes" its data from April 2026)

| | March 2026 | September 2026 |
|---|---|---|
| Overall quality score | 95.3% | 97.7% |
| Materials with zero mistakes | 50.8% | 69.5% |
| Suppliers with zero mistakes | 73.7% | 82.8% |

**Cost**

- Estimated cost of bad master data: about **₹25 Cr a year** (likely range ₹20 Cr to ₹33 Cr)
- Just 3 rules cause almost half of that cost: missing customs (HS) codes, duplicate materials and reorder points set to zero

**Checking the checks**
23 of the 26 rules caught every planted mistake and flagged nothing wrongly. That's only possible because I planted the mistakes myself, so on real data I would expect lower numbers.

## Conclusion

- **Clean the data before you match it.** Expanding abbreviations and fixing units did more for duplicate detection than any model setting.
- **Simple fuzzy matching doesn't work for product data** where small number differences matter.
- **More fields don't always help a model.** Removing two fields made it far better.
- **A rupee figure gets attention.** "97.7% quality score" means little to a manager. "₹25 Cr a year, mostly from three problems" tells them where to start.
- **Every rule needs an owner.** Finding mistakes is easy. Getting them fixed depends on someone being responsible.

## Limitations

- The data is made up, so real SAP data would be messier and the results lower.
- The cost values are my estimates. A finance team would need to check them.
- Customer data and bills of materials are not included.

## How to run it

You need Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run_pipeline.sh
```

It takes about 3 minutes. Then open `dashboard/standalone.html` in your browser.

## Folder guide

| Folder / file | What's inside |
|---|---|
| `src/` | Python scripts for each step |
| `src/config.py` | factories, owners, rules and dates in one place |
| `dbt_mdg/` | the 26 rules, scores and tests (SQL) |
| `gx/` | Great Expectations checks |
| `config/cost_assumptions.yaml` | low, likely and high cost for each type of mistake |
| `dashboard/` | the dashboard |
| `docs/01_governance_operating_model.md` | who owns which data, deadlines, escalation |
| `docs/02_data_dictionary.md` | every table and field used |

## Tools

Python (pandas, NumPy), SQL, dbt, DuckDB, Great Expectations, Splink, RapidFuzz
