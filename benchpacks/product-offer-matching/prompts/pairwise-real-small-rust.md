You are running inside the prepared repository workspace for this benchmark
case. Implement the Rust product-offer matcher by editing the workspace file
directly.

Allowed repo-root path to edit:

- `matcher.rs`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Python matcher.

Task:

Write a deterministic product-offer matcher. The program must read visible
labeled training pairs from `data/train.csv`, read unlabeled prediction pairs
from `data/test_pairs.csv`, and write `predictions.csv` with exactly one
`pair_id,label` row for every prediction pair. Label `1` means the two offers
refer to the same product; label `0` means they do not.

Use a single Rust source file that compiles with `rustc` and the Rust standard
library only. Do not use Cargo, network access, external crates, or external
services. Do not hardcode test `pair_id` values or labels.

CSV schemas:

`data/train.csv` columns:

```text
pair_id,brand_left,title_left,description_left,price_left,priceCurrency_left,brand_right,title_right,description_right,price_right,priceCurrency_right,label
```

`data/test_pairs.csv` columns:

```text
pair_id,brand_left,title_left,description_left,price_left,priceCurrency_left,brand_right,title_right,description_right,price_right,priceCurrency_right
```

Current file: `matcher.rs`

```rust
use std::env;
use std::fs;
use std::io::{self, Write};

fn arg_value(args: &[String], name: &str) -> Result<String, String> {
    args.windows(2)
        .find(|pair| pair[0] == name)
        .map(|pair| pair[1].clone())
        .ok_or_else(|| format!("missing required argument {name}"))
}

fn csv_cells(line: &str) -> Vec<String> {
    let mut cells = Vec::new();
    let mut cell = String::new();
    let mut chars = line.chars().peekable();
    let mut quoted = false;
    while let Some(ch) = chars.next() {
        if quoted {
            if ch == '"' {
                if chars.peek() == Some(&'"') {
                    chars.next();
                    cell.push('"');
                } else {
                    quoted = false;
                }
            } else {
                cell.push(ch);
            }
        } else if ch == '"' {
            quoted = true;
        } else if ch == ',' {
            cells.push(cell);
            cell = String::new();
        } else {
            cell.push(ch);
        }
    }
    cells.push(cell);
    cells
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let _train_path = arg_value(&args, "--train")?;
    let predict_path = arg_value(&args, "--predict")?;
    let output_path = arg_value(&args, "--output")?;

    let predict = fs::read_to_string(predict_path)?;
    let mut lines = predict.lines();
    let header = lines.next().ok_or("prediction input is empty")?;
    let headers = csv_cells(header);
    let pair_id_index = headers
        .iter()
        .position(|value| value == "pair_id")
        .ok_or("prediction input is missing pair_id")?;

    let mut output = fs::File::create(output_path)?;
    writeln!(output, "pair_id,label")?;
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let cells = csv_cells(line);
        let pair_id = cells.get(pair_id_index).ok_or("row is missing pair_id")?;
        writeln!(output, "{},0", pair_id)?;
    }

    io::stdout().flush()?;
    Ok(())
}
```

Useful implementation ideas:

- Normalize text case, punctuation, whitespace, and simple Unicode variants.
- Compare title, brand, and description tokens.
- Extract model-like tokens such as capacities, part numbers, hyphenated
  identifiers, and alphanumeric product codes.
- Use visible `label` values in `data/train.csv` to tune a threshold or simple
  weighted rule.
- Treat matching brands, model identifiers, and high title-token overlap as
  positive evidence.
- Treat conflicting capacities, product families, or very low overlap as
  negative evidence.

Local commands the verifier will run:

```sh
rustc matcher.rs -O -o <verifier-temp>/matcher-rust
<verifier-temp>/matcher-rust --train data/train.csv --predict data/test_pairs.csv --output predictions.csv
```

Verifier contract:

- `predictions.csv` must have header `pair_id,label`.
- Every `pair_id` from `data/test_pairs.csv` must appear exactly once.
- No unknown or duplicate ids are allowed.
- Labels must be exactly `0` or `1`.
- Positive-class F1 against hidden labels must be at least `0.70`.

Edit `matcher.rs` directly and exit when done.
