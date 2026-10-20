use std::env;
use std::fs;
use std::io::{self, Write};
use std::process;

use hpwnr::{convert, fetch, resolve_and_decrypt, unwrap_link, ConvertOps};

fn main() {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let body = subscription_body()?;
    let text = String::from_utf8_lossy(&body);
    let ops = ConvertOps::SINGBOX | ConvertOps::ALL;
    let uris = convert(&text, ops);
    if uris.trim().is_empty() {
        return Err("no supported proxy URIs found in subscription".into());
    }
    io::stdout()
        .write_all(uris.as_bytes())
        .map_err(|e| e.to_string())?;
    if !uris.ends_with('\n') {
        println!();
    }
    Ok(())
}

fn subscription_body() -> Result<Vec<u8>, String> {
    if let Ok(path) = env::var("SUBSCRIPTION_FILE") {
        if path.trim().is_empty() {
            return Err("SUBSCRIPTION_FILE is empty".into());
        }
        return fs::read(&path).map_err(|e| format!("read {path}: {e}"));
    }

    let link = env::var("SUBSCRIPTION_URL").map_err(|_| {
        String::from("set SUBSCRIPTION_URL or SUBSCRIPTION_FILE")
    })?;
    let ua = env::var("HPWNR_UA").unwrap_or_default();
    let hwid = env::var("HPWNR_HWID").unwrap_or_default();

    let normalized = unwrap_link(link.trim());
    let target = match resolve_and_decrypt(&normalized).map_err(|e| e.to_string())? {
        Some(plain) => plain,
        None => normalized,
    };

    fetch(&target, &ua, &hwid).map_err(|e| e.to_string())
}
