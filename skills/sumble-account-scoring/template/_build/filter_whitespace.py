"""Stage 5 (optional) — filter whitespace rows by criteria or an LLM/web-research call.

Provider-AGNOSTIC: one common interface, five interchangeable backends the user
can bring their own API key for:

  anthropic  Claude + server-side web search   (default model claude-sonnet-4-6)
  openai     Responses API + web_search tool   (default model gpt-5-mini)
  gemini     generateContent + Google grounding (default model gemini-2.5-flash)
  parallel   Parallel Task API (research + structured output in one call)
  exa        Exa /answer (search + answer in one call)

Each backend answers the same question per account — "does this company fit the
ICP?" — and returns {"fit": bool, "reason": "<one sentence>"}. The script never
DROPS rows: it writes ws_fit / ws_fit_reason / ws_filter_provider columns into
data.csv and appends an `llm_fit` / `llm_unfit` tag to the row's `tags`, so the
app's existing tag chips can filter visually with zero app changes. Re-run
score_sheet to refresh score.csv (done automatically at the end).

Also supports a no-LLM `--mode criteria` pass over columns already in data.csv
(employee count, country, industry, tags, any numeric signal) via a rules JSON.

Design notes:
- stdlib only (urllib, csv, json, concurrent.futures) — no pip installs.
- Checkpointed: results append to _raw/ws_filter_results.jsonl as they land;
  re-running skips already-classified org_ids (resume after interrupt).
- Bounded: --top N (by current rank in score.csv) filters only the head of the
  whitespace list — the tail never mattered. Recommend 2000.
- Honest spend: --estimate-only prints cost/time; the real run asks for
  confirmation unless --yes.

API keys resolve from, in order:
  1. --api-key                explicit flag
  2. --key-cmd "<command>"    any command whose stdout is the key — works with
                              every secret manager (gcloud secrets / op read /
                              aws secretsmanager / pass ...); value stays
                              in-process, never printed or written
  3. the provider's standard env var (ANTHROPIC_API_KEY / OPENAI_API_KEY /
     GEMINI_API_KEY / PARALLEL_API_KEY / EXA_API_KEY)
  4. --env-file of KEY=VALUE lines (gitignored file)
  5. ~/.config/sumble/<provider>_api_key — save it ONCE with --set-key, which
     prompts with hidden input (never lands in chat transcripts or shell
     history) and writes the file chmod 600. The portable default for users
     without a secret manager.
Keys never land in any output file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "parallel": "PARALLEL_API_KEY",
    "exa": "EXA_API_KEY",
}
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5-mini",
    "gemini": "gemini-2.5-flash",
    "parallel": "base",  # Task API processor: lite | base | core
    "exa": "",  # /answer has no model knob
}
# Rough all-in cost per 1,000 accounts (search/grounding fees + tokens), USD.
EST_COST_PER_1K = {
    "anthropic": 35.0,
    "openai": 17.0,
    "gemini": 38.0,  # $35/1K grounding after 1,500 free/day + tokens
    "parallel": 10.0,  # base processor; lite ~$5, core ~$25
    "exa": 5.0,
}
EST_SECONDS_PER_CALL = {
    "anthropic": 12.0,
    "openai": 10.0,
    "gemini": 8.0,
    "parallel": 60.0,  # async deep research; high concurrency offsets latency
    "exa": 8.0,
}

EVIDENCE_COLUMNS = [
    "name",
    "url",
    "industry",
    "employee_count_int",
    "headquarters_country",
    "tags",
]


# --- HTTP ----------------------------------------------------------------------


def http_json(
    url: str,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = 180,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"content-type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_json_retry(*args: Any, retries: int = 5, **kwargs: Any) -> dict:
    """Retry on 429/5xx with exponential backoff; raise other errors."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return http_json(*args, **kwargs)
        except urllib.error.HTTPError as e:
            if e.code in (408, 429, 500, 502, 503, 504, 529):
                last = e
                time.sleep(min(2**attempt + 1, 60))
                continue
            detail = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(min(2**attempt + 1, 60))
    raise RuntimeError(f"retries exhausted: {last}")


# --- Prompt + response parsing --------------------------------------------------


def build_prompt(icp_prompt: str, row: dict[str, str]) -> str:
    lines = []
    for col in EVIDENCE_COLUMNS:
        val = (row.get(col) or "").strip()
        if val:
            lines.append(f"- {col}: {val}")
    evidence = "\n".join(lines) or "- (no firmographic data available)"
    return (
        f"{icp_prompt.strip()}\n\n"
        f"Company to evaluate:\n{evidence}\n\n"
        "Research the company on the web if needed (its website is the most "
        "reliable source — beware same-named companies; trust the domain above). "
        "Then respond with STRICT JSON only, no prose before or after:\n"
        '{"fit": true or false, "reason": "<one sentence explaining why>"}'
    )


def parse_verdict(text: str) -> tuple[bool, str]:
    """Extract {"fit": bool, "reason": str} from model text, defensively."""
    if not text:
        raise ValueError("empty response")
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        for candidate in (text[start : end + 1],):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and "fit" in obj:
                    return bool(obj["fit"]), str(obj.get("reason", "")).strip()
            except json.JSONDecodeError:
                pass
    m = re.search(r'"fit"\s*:\s*(true|false)', text, re.I)
    if m:
        reason = ""
        rm = re.search(r'"reason"\s*:\s*"([^"]*)"', text)
        if rm:
            reason = rm.group(1)
        return m.group(1).lower() == "true", reason
    raise ValueError(f"unparseable verdict: {text[:200]}")


# --- Provider adapters ----------------------------------------------------------
# Each takes (key, model, prompt) and returns the raw text to parse.


def call_anthropic(key: str, model: str, prompt: str) -> str:
    resp = http_json_retry(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        body={
            "model": model,
            "max_tokens": 1024,
            "tools": [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
            ],
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return "".join(
        b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"
    )


def call_openai(key: str, model: str, prompt: str) -> str:
    resp = http_json_retry(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}"},
        body={"model": model, "tools": [{"type": "web_search"}], "input": prompt},
    )
    if resp.get("output_text"):
        return resp["output_text"]
    parts: list[str] = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
    return "".join(parts)


def call_gemini(key: str, model: str, prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    resp = http_json_retry(
        url,
        headers={"x-goog-api-key": key},
        body={
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        },
    )
    candidates = resp.get("candidates") or []
    if not candidates:
        raise ValueError(f"no candidates: {json.dumps(resp)[:200]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def call_parallel(key: str, model: str, prompt: str) -> str:
    """Parallel Task API: create a run, then block on its result endpoint."""
    run = http_json_retry(
        "https://api.parallel.ai/v1/tasks/runs",
        headers={"x-api-key": key},
        body={
            "input": prompt,
            "processor": model,
            "task_spec": {
                "output_schema": {
                    "type": "json",
                    "json_schema": {
                        "type": "object",
                        "properties": {
                            "fit": {
                                "type": "boolean",
                                "description": "true if the company fits the ICP",
                            },
                            "reason": {
                                "type": "string",
                                "description": "one sentence explaining why",
                            },
                        },
                        "required": ["fit", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
        },
    )
    run_id = run.get("run_id") or run.get("id")
    if not run_id:
        raise ValueError(f"no run id: {json.dumps(run)[:200]}")
    result = http_json_retry(
        f"https://api.parallel.ai/v1/tasks/runs/{run_id}/result?timeout=600",
        method="GET",
        headers={"x-api-key": key},
        timeout=620,
    )
    content = result.get("output", {}).get("content")
    if isinstance(content, dict):
        return json.dumps(content)
    return str(content or "")


def call_exa(key: str, _model: str, prompt: str) -> str:
    resp = http_json_retry(
        "https://api.exa.ai/answer",
        headers={"x-api-key": key},
        body={"query": prompt, "text": True},
    )
    answer = resp.get("answer", "")
    return answer if isinstance(answer, str) else json.dumps(answer)


CALLERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "gemini": call_gemini,
    "parallel": call_parallel,
    "exa": call_exa,
}


# --- Criteria mode ---------------------------------------------------------------


def _num(val: str) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def apply_rule(row: dict[str, str], rule: dict) -> bool:
    col, op, want = rule["column"], rule["op"], rule["value"]
    have = (row.get(col) or "").strip()
    if op in (">=", "<=", ">", "<"):
        x = _num(have)
        return {
            ">=": x >= float(want),
            "<=": x <= float(want),
            ">": x > float(want),
            "<": x < float(want),
        }[op]
    if op == "==":
        return have == str(want)
    if op == "!=":
        return have != str(want)
    if op == "in":
        return have in [str(v) for v in want]
    if op == "not_in":
        return have not in [str(v) for v in want]
    if op == "contains":  # pipe-delimited membership (tags) or substring
        items = have.split("|") if "|" in have else [have]
        return str(want) in items or str(want) in have
    if op == "not_contains":
        items = have.split("|") if "|" in have else [have]
        return str(want) not in items and str(want) not in have
    raise ValueError(f"unknown op: {op}")


def criteria_verdict(row: dict[str, str], rules: list[dict]) -> tuple[bool, str]:
    for rule in rules:
        if not apply_rule(row, rule):
            desc = rule.get("label") or (
                f"{rule['column']} {rule['op']} {rule['value']}"
            )
            return False, f"fails: {desc}"
    return True, "meets all criteria"


# --- Data plumbing ---------------------------------------------------------------


def load_rows(out_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    with (out_dir / "data.csv").open() as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def load_ranks(out_dir: Path) -> dict[str, int]:
    path = out_dir / "score.csv"
    ranks: dict[str, int] = {}
    if path.exists():
        with path.open() as fh:
            for row in csv.DictReader(fh):
                try:
                    ranks[row["org_id"]] = int(row.get("rank") or 0)
                except (KeyError, ValueError):
                    continue
    return ranks


def select_targets(
    rows: list[dict[str, str]], ranks: dict[str, int], top: int | None
) -> list[dict[str, str]]:
    ws = [
        r for r in rows if (r.get("account_category") or "").startswith("whitespace")
    ]
    ws.sort(key=lambda r: ranks.get(r.get("org_id", ""), 10**9))
    return ws[:top] if top else ws


def merge_results(
    out_dir: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
    results: dict[str, dict],
    provider: str,
) -> None:
    new_cols = ["ws_fit", "ws_fit_reason", "ws_filter_provider"]
    for col in new_cols:
        if col not in fieldnames:
            fieldnames.append(col)
    for row in rows:
        res = results.get(row.get("org_id", ""))
        if res is None:
            row.setdefault("ws_fit", "")
            row.setdefault("ws_fit_reason", "")
            row.setdefault("ws_filter_provider", "")
            continue
        row["ws_fit"] = "1" if res["fit"] else "0"
        row["ws_fit_reason"] = res["reason"]
        row["ws_filter_provider"] = provider
        tags = [t for t in (row.get("tags") or "").split("|") if t]
        tags = [t for t in tags if t not in ("llm_fit", "llm_unfit")]
        tags.append("llm_fit" if res["fit"] else "llm_unfit")
        row["tags"] = "|".join(tags)
    tmp = out_dir / "data.csv.tmp"
    with tmp.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, out_dir / "data.csv")


def rebuild_score_sheet(out_dir: Path) -> None:
    sys.path.insert(0, str(out_dir))
    try:
        import score_sheet  # noqa: E402  (lives in the app output dir)

        info = score_sheet.build_score_sheet(out_dir)
        print(f"[filter] rebuilt score.csv ({info.get('rows')} rows)")
    except Exception as e:  # non-fatal: app rebuilds it at startup anyway
        print(f"[filter] score.csv not rebuilt ({e}); the app rebuilds at startup")


# --- Main ------------------------------------------------------------------------


KEY_DIR = Path.home() / ".config" / "sumble"
KEY_URLS = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "gemini": "https://aistudio.google.com/apikey",
    "parallel": "https://platform.parallel.ai",
    "exa": "https://dashboard.exa.ai",
}


def key_file_path(provider: str) -> Path:
    return KEY_DIR / f"{provider}_api_key"


def set_key_interactive(provider: str) -> None:
    """Prompt for the key with hidden input and save it chmod 600."""
    import getpass

    print(f"Get your {provider} API key from: {KEY_URLS[provider]}")
    key = getpass.getpass(f"Paste your {provider} API key (input hidden): ").strip()
    if not key:
        sys.exit("No key entered — nothing saved.")
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    path = key_file_path(provider)
    path.write_text(key + "\n")
    path.chmod(0o600)
    print(f"Saved to {path} (chmod 600). Future runs find it automatically.")


def resolve_key(args: argparse.Namespace) -> str:
    if args.api_key:
        return args.api_key
    if args.key_cmd:
        import subprocess

        proc = subprocess.run(
            args.key_cmd, shell=True, capture_output=True, text=True
        )
        if proc.returncode != 0:
            sys.exit(f"--key-cmd failed: {proc.stderr.strip()[:300]}")
        key = proc.stdout.strip()
        if key:
            return key
        sys.exit("--key-cmd succeeded but produced no output.")
    env_name = ENV_KEYS[args.provider]
    key = os.environ.get(env_name, "")
    if key:
        return key
    if args.env_file:
        for line in Path(args.env_file).read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{env_name}="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    return val
    path = key_file_path(args.provider)
    if path.exists():
        val = path.read_text().strip()
        if val:
            return val
    sys.exit(
        f"No API key found for {args.provider}.\n"
        f"  Easiest: save it once (hidden input, stored chmod 600):\n"
        f"    python3 {sys.argv[0]} --provider {args.provider} --set-key\n"
        f"  Or: set {env_name}, pass --api-key, point --env-file at a "
        f"KEY=VALUE file,\n"
        f"  or use a secret manager: --key-cmd \"gcloud secrets versions "
        f"access latest --secret={env_name}\"\n"
        f"  Get a key: {KEY_URLS[args.provider]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter whitespace rows by criteria or an LLM/web-research call."
    )
    parser.add_argument("--dir", default=None, help="app output root (has data.csv)")
    parser.add_argument("--mode", choices=["llm", "criteria"], default="llm")
    parser.add_argument("--provider", choices=sorted(CALLERS), default="anthropic")
    parser.add_argument("--model", default=None, help="override the provider default")
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--key-cmd", default=None, help="command whose stdout is the API key"
    )
    parser.add_argument(
        "--set-key",
        action="store_true",
        help="prompt (hidden input) and save the provider key to ~/.config/sumble",
    )
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--prompt-file", default=None, help="ICP prompt (llm mode)")
    parser.add_argument("--rules", default=None, help="rules JSON (criteria mode)")
    parser.add_argument("--top", type=int, default=None, help="only top-N by rank")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the confirm prompt")
    args = parser.parse_args()

    if args.set_key:
        set_key_interactive(args.provider)
        return
    if not args.dir:
        parser.error("--dir is required (the app output root containing data.csv)")

    out_dir = Path(args.dir).resolve()
    raw = out_dir / "_raw"
    raw.mkdir(exist_ok=True)
    checkpoint = raw / "ws_filter_results.jsonl"

    rows, fieldnames = load_rows(out_dir)
    targets = select_targets(rows, load_ranks(out_dir), args.top)
    if not targets:
        sys.exit("No whitespace rows found in data.csv — nothing to filter.")

    # --- criteria mode: instant, free, local --------------------------------
    if args.mode == "criteria":
        if not args.rules:
            sys.exit("--mode criteria requires --rules <rules.json>")
        rules = json.loads(Path(args.rules).read_text())
        results = {}
        for row in targets:
            fit, reason = criteria_verdict(row, rules)
            results[row["org_id"]] = {"fit": fit, "reason": reason}
        n_fit = sum(1 for r in results.values() if r["fit"])
        merge_results(out_dir, rows, fieldnames, results, "criteria")
        rebuild_score_sheet(out_dir)
        print(
            f"[filter] criteria: {n_fit}/{len(results)} whitespace rows fit; "
            "columns ws_fit/ws_fit_reason written; tags llm_fit/llm_unfit applied."
        )
        return

    # --- llm mode ------------------------------------------------------------
    model = args.model or DEFAULT_MODELS[args.provider]
    est_cost = EST_COST_PER_1K[args.provider] * len(targets) / 1000.0
    est_min = (
        EST_SECONDS_PER_CALL[args.provider] * len(targets) / max(args.workers, 1) / 60
    )
    print(
        f"[filter] {len(targets)} whitespace rows via {args.provider}"
        f" ({model or 'default'}), {args.workers} workers\n"
        f"[filter] estimated cost ~${est_cost:,.0f}, "
        f"estimated time ~{est_min:,.0f} min (provider rate limits permitting)"
    )
    if args.estimate_only:
        return
    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    if not args.prompt_file:
        sys.exit("--prompt-file is required in llm mode (the ICP description).")
    icp_prompt = Path(args.prompt_file).read_text()
    key = resolve_key(args)
    caller = CALLERS[args.provider]

    # Verdicts are only comparable under the SAME fit definition. If the ICP
    # prompt changed since the last run, archive the old checkpoint and start
    # fresh rather than silently mixing verdicts from two different prompts.
    prompt_sha = hashlib.sha256(icp_prompt.encode()).hexdigest()
    sha_path = raw / "ws_filter_prompt.sha256"
    if (
        checkpoint.exists()
        and sha_path.exists()
        and sha_path.read_text().strip() != prompt_sha
    ):
        stale = checkpoint.with_name(checkpoint.name + ".stale")
        checkpoint.rename(stale)
        print(
            "[filter] ICP prompt changed since the last run — archived old "
            f"results to {stale.name}; reclassifying from scratch."
        )
    sha_path.write_text(prompt_sha + "\n")

    done: dict[str, dict] = {}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            try:
                rec = json.loads(line)
                done[rec["org_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue
        if done:
            print(f"[filter] resuming: {len(done)} rows already classified")

    todo = [r for r in targets if r.get("org_id") not in done]
    lock = threading.Lock()
    counts = {"ok": 0, "err": 0}

    def work(row: dict[str, str]) -> None:
        org_id = row.get("org_id", "")
        prompt = build_prompt(icp_prompt, row)
        try:
            text = caller(key, model, prompt)
            fit, reason = parse_verdict(text)
        except Exception as e:
            with lock:
                counts["err"] += 1
                print(f"[filter] ERROR {row.get('name', org_id)}: {e}")
            return
        rec = {"org_id": org_id, "fit": fit, "reason": reason}
        with lock:
            done[org_id] = rec
            with checkpoint.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            counts["ok"] += 1
            n = counts["ok"]
            if n % 25 == 0:
                print(f"[filter] {n}/{len(todo)} classified...")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, row) for row in todo]
        for fut in as_completed(futures):
            fut.result()

    results = {oid: rec for oid, rec in done.items()}
    n_fit = sum(1 for r in results.values() if r["fit"])
    merge_results(out_dir, rows, fieldnames, results, args.provider)
    rebuild_score_sheet(out_dir)
    print(
        f"[filter] done: {len(results)} classified ({n_fit} fit, "
        f"{len(results) - n_fit} not fit, {counts['err']} errors).\n"
        "[filter] data.csv now carries ws_fit / ws_fit_reason; whitespace rows are "
        "tagged llm_fit / llm_unfit so the app's tag chips can filter them. "
        "Errors can be retried by re-running (checkpointed)."
    )


if __name__ == "__main__":
    main()
