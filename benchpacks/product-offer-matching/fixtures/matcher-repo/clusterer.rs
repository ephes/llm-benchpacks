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

fn header_index(headers: &[String], name: &str) -> Result<usize, String> {
    headers
        .iter()
        .position(|value| value == name)
        .ok_or_else(|| format!("missing required column {name}"))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let _train_path = arg_value(&args, "--train")?;
    let predict_path = arg_value(&args, "--predict")?;
    let output_path = arg_value(&args, "--output")?;
    let pair_input_path = arg_value(&args, "--pair-input")?;
    let pair_scores_path = arg_value(&args, "--pair-scores")?;

    let predict = fs::read_to_string(predict_path)?;
    let mut lines = predict.lines();
    let header = lines.next().ok_or("prediction input is empty")?;
    let headers = csv_cells(header);
    let offer_id_index = header_index(&headers, "offer_id")?;

    let mut output = fs::File::create(output_path)?;
    writeln!(output, "offer_id,cluster_id")?;
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let cells = csv_cells(line);
        let offer_id = cells.get(offer_id_index).ok_or("row is missing offer_id")?;
        writeln!(output, "{},singleton:{}", offer_id, offer_id)?;
    }

    let pairs = fs::read_to_string(pair_input_path)?;
    let mut pair_lines = pairs.lines();
    let pair_header = pair_lines.next().ok_or("pair input is empty")?;
    let pair_headers = csv_cells(pair_header);
    let pair_id_index = header_index(&pair_headers, "pair_id")?;

    let mut scores = fs::File::create(pair_scores_path)?;
    writeln!(scores, "pair_id,score")?;
    for line in pair_lines {
        if line.trim().is_empty() {
            continue;
        }
        let cells = csv_cells(line);
        let pair_id = cells.get(pair_id_index).ok_or("row is missing pair_id")?;
        writeln!(scores, "{},0.0", pair_id)?;
    }

    io::stdout().flush()?;
    Ok(())
}
