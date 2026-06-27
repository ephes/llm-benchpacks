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
