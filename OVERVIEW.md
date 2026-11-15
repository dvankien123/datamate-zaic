# DESCRIPTION

Spreadsheets and simple databases are the most widely used data systems in the world. A shop owner keeps sales and inventory in Excel; a teacher keeps grades and attendance; a clinic keeps patient visits and medicine batches; an HR officer keeps timesheets; a cooperative keeps yields and input costs; a commune office keeps household statistics; a journalist downloads open data from the General Statistics Office; an employee of a large company wants a number from the data warehouse without waiting for the data team. All of them have the data. Almost none of them can write a query. What they want is to ask in plain Vietnamese — “Tháng này bán chạy nhất mặt hàng gì?”, “Tuần rồi bán được bao nhiêu ly trà sữa?”, “Còn ai nợ tiền chưa trả?”, “Thuốc nào sắp hết hạn trong kho?” — and get a correct answer.

DataMate challenges you to build an AI agent that answers natural-language Vietnamese questions directly on structured data (CSV, Excel, SQLite): given the raw files and a question, the agent returns a correct answer — or declines to answer when the data cannot support the question. The competition data is anchored in the world of Vietnamese small businesses — the largest group of spreadsheet users in the country and the one with the richest, messiest real-world data — but the capability you build is general: natural-language question answering over tabular data.

**Input:**
* A data package for one business: one or more files (`.csv`, `.xlsx`, `.sqlite`) plus a short `README.md` describing the business.
* A question in everyday Vietnamese.
* An as-of date: the “today” against which relative time expressions (“tháng này”, “tuần rồi”, “cùng kỳ năm ngoái”) are resolved.
* A rulebook and a solar–lunar calendar, shared by every business of the split (see the Data section).

**Output:**
* A final answer of one of the types in the Evaluation section: a value (`number`, `percent`, `string`, `date`, `boolean`, `list`, `table`), `unanswerable` when the data cannot support the question, or `abstain` when the agent chooses not to answer.

**An example:**  
Input — one line of `questions.jsonl`:
```json
{"id": "q_06de33fa21cc", "business_id": "biz_118", "question": "sp bán dc nhiều nhất tuần rồi là gì", "as_of_date": "2026-03-04"}
```

Output — one line of `submission.jsonl`:
```json
{"id": "q_06de33fa21cc", "type": "string", "answer": "Xi măng Hà Tiên PCB40 bao 50kg"}
```

---

# EVALUATION

## Per-question scoring
Each answer is scored correct, wrong or abstain. An answer of type `abstain` (or a missing answer) is an abstain. Any other answer is correct only if its type equals the reference type and its value matches the reference as follows; otherwise it is wrong. No partial credit.

| Type | Answer content | Example | Matching rule |
| :--- | :--- | :--- | :--- |
| `number` | A numeric value (VND amounts, counts, quantities) | `48250000` | Exact match. Reference values are integers (VND amounts, counts, quantities) or rounded to 2 decimals. |
| `percent` | A percentage value, in percent | `-12.45` | Exact match after rounding to 2 decimal places; the sign must be correct. |
| `string` | A name (product, customer, branch, weekday, ...) | `"Sting dâu 330ml"` | Both the answer and each accepted form of the reference are normalized, then compared for exact equality. Normalization: (1) Unicode NFC; (2) lowercase; (3) every character that is not a letter, a digit or whitespace is replaced by a space; (4) leading/trailing whitespace removed and runs of whitespace collapsed to one space. Diacritics are not removed. Each reference lists its accepted forms: every spelling of the name that occurs in that business’s data, plus its code — after normalization, e.g. `sting dâu 330ml`, `sp0042`. |
| `date` | A date in ISO format | `"2026-08-15"`, `"2025-09"` | Exact match. `yyyy-mm-dd`; questions about a month: `yyyy-mm` (e.g. `"2025-09"`). |
| `boolean` | `true` / `false` | `true` | Exact match. |
| `list` | An ordered list of names or numbers, in the order the question asks for (or the rulebook default) | `["Cà phê sữa", "Bạc xỉu", "Trà đào"]` | Always ordered, and matched position by position. The order is the one the question asks for, or the rulebook default when the question gives none (see Ranking questions below). Elements are matched with the string or number rule. |
| `table` | A small table: column names and rows | `{"columns": [...], "rows": [[...], ...]}` | Columns are matched by normalized name; if the names do not match, by position. Rows are matched as a set; name cells with the string rule, numeric cells with the number rule. |
| `unanswerable` | The data does not contain what is needed to answer | — | Correct if and only if the reference is unanswerable. |
| `abstain` | The agent chooses not to answer | — | Scored as abstain regardless of the reference. |

**Ranking questions.** Rankings use the criterion stated in the question, or the rulebook default when the question gives none, in descending order of that criterion over valid orders only; elements with equal values are ordered by code, ascending. Questions whose reference ranking has a tie at the $k$ boundary (or at rank 1 for “… nhất” questions) are excluded from the test sets. When fewer than $k$ candidates exist, the reference answer is all of them.

## Score
The leaderboard metric is **Penalized Accuracy (PA)** over the $N$ questions of a test set:

$$PA = \frac{1}{N} \sum_{i=1}^{N} s_i, \quad s_i = \begin{cases} 1 & \text{answer } i \text{ is correct} \\ 0 & \text{answer } i \text{ is abstain} \\ -1 & \text{answer } i \text{ is wrong} \end{cases}$$

Any answer given to an unanswerable question counts as wrong. All questions carry equal weight. Ties in the final ranking are broken by total inference time in the organizers’ re-run, then by earlier submission.

---

# DATA

## Business types
The data covers a wide range of Vietnamese small businesses: grocery stores, coffee and bubble-tea shops, restaurants, pharmacies, building-material stores, motorbike repair shops, mother-and-baby stores, and more. The private test includes business types that do not appear in the training or public test data.

Each business covers 12–30 months of activity with seasonality (Tết, Mid-Autumn, public holidays, paydays, weekends) and ranges from a few hundred to about 300,000 rows.

## Package structure
```text
<split>/
├── data/
│   └── <business_id>/
│       ├── *.csv | *.xlsx | *.sqlite   # one or more data files
│       └── README.md                   # business description and notes
├── rulebook.md                         # default rules and vocabulary
├── calendar.csv                        # solar–lunar calendar (Tết)
├── questions.jsonl                     # one question per line
└── answers.jsonl                       # training only
```

Sample record in `questions.jsonl`:
```json
{"id": "q_01234", "business_id": "biz_017", "question": "thang nay hang nao ban cham nhat, ton nhieu ma ban ko dc", "as_of_date": "2026-08-27"}
```

Training businesses also come with `answers.jsonl`, which contains the reference answer for every training question, linked by `"id"`. Each line follows the submission format, plus an `"alias"` field listing other accepted forms of a name answer (alternative spellings found in the data and the item code). Unanswerable questions have `"answer": null`. Submissions do not need to include the `"alias"` field.

Sample record in `answers.jsonl` (the reference answer of the example question in the Description section):
```json
{"id": "q_06de33fa21cc", "type": "string", "answer": "Xi măng Hà Tiên PCB40 bao 50kg", "alias": ["SP0001"]}
```

The quality of `README.md` varies: some businesses come with a full data dictionary, others with a few informal notes, some with almost nothing.

## Splits
| Split | Businesses | Questions | Reference answers |
| :--- | :--- | :--- | :--- |
| Training | 30 | ~3,000 | Yes |
| Public test | 10–20 | ~1,000 | Hidden; scored on the public leaderboard |
| Private test | 10–20 | ~500 | Hidden; released at the private test phase; includes new business types |

## Business rules (default interpretations)
Each split ships its own rulebook (`rulebook.md`), which fixes the default meaning of common terms whenever the question does not say otherwise. The rulebook may differ between splits so your agent must read and apply the rulebook of the split it is answering, not a copy of the training rulebook. Typical rules: revenue = sum of line amounts after line-level discounts (order-level vouchers are not deducted), excluding VAT and delivery fees, excluding cancelled orders and orders with any returned item; “bán chạy” = by quantity; a week runs Monday–Sunday; “tháng này” = the month containing the as-of date, up to and including that date; default cost = weighted-average purchase cost by lot; the Tết window = 23 tháng Chạp to mùng 10 (lunar calendar).

## Submission format
**Submission file.** In both rounds you upload a `submission.jsonl` file, one JSON object per line:
```json
{"id": "q_01234", "type": "string",  "answer": "Sting dâu 330ml"}
{"id": "q_01235", "type": "number",  "answer": 48250000}
{"id": "q_01236", "type": "percent", "answer": -12.45}
{"id": "q_01237", "type": "date",    "answer": "2026-08-15"}
{"id": "q_01238", "type": "boolean", "answer": true}
{"id": "q_01239", "type": "list",    "answer": ["Cà phê sữa", "Bạc xỉu", "Trà đào"]}
{"id": "q_01240", "type": "table",   "answer": {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000], ["Anh Tú", 1500000]]}}
{"id": "q_01241", "type": "unanswerable", "reason": "Dữ liệu không có giá vốn nên không tính được lợi nhuận"}
{"id": "q_01242", "type": "abstain"}
```
Questions missing from the file are scored as `abstain`. The `reason` field is optional. The number of submissions per day follows the general regulations.

**Docker image.** The image (see Competition rounds in the Rule section) must contain the source code (training and inference), the model weights and a `predict.sh` that reads the test set from `/data` and writes `/result/submission.jsonl`, together with a README. It should also write a per-question log to `/result/logs/`, in any format, containing at least the question id, the final answer and the elapsed time — plus anything else that shows how the answer was reached (e.g. generated code, execution output). The organizers use these logs to resolve differences between your uploaded result and their re-run (Rule 8).

## Competition rounds
The competition runs on a leaderboard with two rounds:
* **Round 1 — Public test:** teams develop their solutions, run them on the public test set and upload `submission.jsonl`. Scores appear on the public leaderboard and are for reference only during development.
* **Final solution submission:** before the solution deadline, the final solution is submitted as a Docker image, following the organizers’ separate Docker guideline. For scoring, the organizers mount the test set into the container at `/data` and collect `/result/submission.jsonl`.
* **Round 2 — Private test:** after teams submit and freeze their solutions, the organizers release the private test set. Teams run their frozen solution on it and upload `submission.jsonl`. The final ranking is based on the organizers’ re-run of the submitted Docker images (Rule 8).

---

# RULE

## Technical requirements
Every solution must meet all of the following requirements:
1. **Teams and eligibility** follow the general regulations of Zalo AI Challenge 2026.
2. **Models.** You may use any model whose weights were publicly released before 26 October 2026 under a licence that permits such use, and you may fine-tune it freely. Across all models used at inference by your solution (language models, embedding models, rerankers, classifiers), whether loaded at the same time or not, the total number of parameters must not exceed 15 billion, counting all parameters of mixture-of-experts models. Any quantization is allowed. The models used must be declared in the solution README.
3. **No external services.** Inference must run fully offline inside your Docker image: no calls to commercial LLM APIs, no downloads, no network access of any kind. The image is run with networking disabled.
4. **No human in the loop.** Answers must be produced by your system without manual intervention. Hard-coding answers, or logic keyed on question or business identifiers, is prohibited.
5. **Code execution.** Your agent may generate and execute code inside the container; this is expected but not required. The data directory is mounted read-only; write temporary files elsewhere.
6. **Data.** You may use the provided training data, data you synthesize yourself, and publicly available datasets and models. You may not use the public or private test data for training, nor collect answers to test questions by any means.
7. **Compute reference.** Solutions are verified on a machine with $2 \times \text{NVIDIA RTX 5090}$ (32 GB VRAM each, 64 GB total), 512 GB RAM. Your solution must process the entire private test set within 6 hours of wall-clock time on this machine, including model loading. Blackwell GPUs require CUDA $\ge$ 12.8 and a matching PyTorch/vLLM build; the Docker guideline specifies the base image to use.
8. **Final score and reproducibility.** The score of the organizers’ re-run of your submitted Docker image on the private test set is your final score. The `submission.jsonl` you upload during the private test phase determines only the provisional leaderboard and which teams are re-run. Your solution must be deterministic enough that the two runs agree: a solution is considered reproducible if $|PA(\text{uploaded}) - PA(\text{re-run})| \le 0.03$. If the difference exceeds 0.03, the organizers will examine the logs written by your image (see Submission format, Section Data), may run the image once more, and may request additional information from the team; if the difference cannot be explained, the entry is disqualified. If the re-run exceeds the time limit of Rule 7 or terminates early, only the answers written to `/result/submission.jsonl` before termination are scored; the rest count as abstain.