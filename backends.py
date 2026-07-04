#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import urllib.request


ERROR_SENTINEL_PREFIX = "ERROR:"


# ---- backends: prompt -> raw text ----
def call_codex(prompt, model):
    out = subprocess.run(["codex", "exec", "--skip-git-repo-check", prompt],
                         capture_output=True, text=True, timeout=180)
    text = out.stdout + "\n" + out.stderr
    # a quota-limited codex answers every case with an error banner; without this
    # guard that scores as [] and a full-suite wipeout masquerades as case failures
    if "hit your usage limit" in text:
        raise RuntimeError("codex usage limit hit; retry after the reset shown in the codex error")
    return text

def call_claude_cli(prompt, model):
    args = ["claude", "-p", prompt] + (["--model", model] if model else [])
    out = subprocess.run(args, capture_output=True, text=True, timeout=180)
    return out.stdout + "\n" + out.stderr

def _http(url, key_header, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json", **key_header})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def call_anthropic(prompt, model):
    key = os.environ["ANTHROPIC_API_KEY"]
    d = _http("https://api.anthropic.com/v1/messages",
              {"x-api-key": key, "anthropic-version": "2023-06-01"},
              {"model": model or "claude-sonnet-4-6", "max_tokens": 200,
               "messages": [{"role": "user", "content": prompt}]})
    return "".join(b.get("text", "") for b in d.get("content", [])) or json.dumps(d)

def _openai_style(url, key, model, prompt):
    d = _http(url, {"authorization": f"Bearer {key}"},
              {"model": model, "max_tokens": 200, "temperature": 0,
               "messages": [{"role": "user", "content": prompt}]})
    return d["choices"][0]["message"]["content"]

def call_openrouter(prompt, model):
    return _openai_style("https://openrouter.ai/api/v1/chat/completions",
                         os.environ["OPENROUTER_API_KEY"], model, prompt)

def call_fireworks(prompt, model):
    return _openai_style("https://api.fireworks.ai/inference/v1/chat/completions",
                         os.environ["FIREWORKS_API_KEY"], model, prompt)


def call_openai(prompt, model):
    return _openai_style("https://api.openai.com/v1/chat/completions",
                         os.environ["OPENAI_API_KEY"], model or "gpt-5.5", prompt)


def call_google(prompt, model):
    key = os.environ["GOOGLE_API_KEY"]
    d = _http(f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.5-pro'}:generateContent",
              {"x-goog-api-key": key},
              {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0, "maxOutputTokens": 200}})
    candidates = d.get("candidates", [])
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    return "".join(part.get("text", "") for part in parts) or json.dumps(d)


BACKENDS = {"codex": call_codex, "claude-cli": call_claude_cli, "anthropic": call_anthropic,
            "openrouter": call_openrouter, "fireworks": call_fireworks,
            "openai": call_openai, "google": call_google}


_BACKEND_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}
_BWS_LOADED = False
def is_error_sentinel(text):
    return isinstance(text, str) and text.startswith(ERROR_SENTINEL_PREFIX)


def call_backend(name, prompt, model=None):
    if name not in BACKENDS:
        return _error_sentinel(name, RuntimeError(f"unknown backend: {name}"))
    try:
        _ensure_backend_auth(name)
        text = BACKENDS[name](prompt, model)
        # Do NOT content-scan for error words here: backends like codex echo the
        # prompt + answer, and analyzed content legitimately contains words like
        # "authentication"/"quota"/"error". Real failures either raise (HTTP 4xx,
        # missing key) and are caught below, or return a banner with no parseable
        # answer — the scorer flags that as error when parse_array() yields None.
        # Adapters guard their own unambiguous quota banners (e.g. call_codex).
        return text
    except Exception as exc:
        return _error_sentinel(name, exc)


def _ensure_backend_auth(name):
    env_name = _BACKEND_ENV.get(name)
    if not env_name or os.environ.get(env_name):
        return
    _load_bws_secrets()
    if not os.environ.get(env_name):
        raise RuntimeError(f"{env_name} not found in environment or bws")


def _load_bws_secrets():
    global _BWS_LOADED
    if _BWS_LOADED:
        return
    env_path = os.path.expanduser("~/dev/.env.local")
    # set -a so BWS_ACCESS_TOKEN is EXPORTED to bws (a child process), not just a
    # shell var — plain `source` leaves it unexported and bws sees no token.
    command = f"set -a; source {shlex.quote(env_path)} >/dev/null 2>&1; set +a; bws secret list -o json"
    out = subprocess.run(["zsh", "-lc", command], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError("bws secret list failed")
    data = json.loads(out.stdout, strict=False)
    wanted = set(_BACKEND_ENV.values())
    for item in data if isinstance(data, list) else []:
        key = item.get("key") or item.get("name")
        value = item.get("value")
        if key in wanted and value and not os.environ.get(key):
            os.environ[key] = value
    _BWS_LOADED = True


def _error_sentinel(name, exc):
    return f"{ERROR_SENTINEL_PREFIX} {name}: {_scrub(str(exc))}"


def _compact(text):
    return " ".join(str(text).split())[:500]


def _scrub(text):
    scrubbed = _compact(text)
    for env_name in _BACKEND_ENV.values():
        value = os.environ.get(env_name)
        if value:
            scrubbed = scrubbed.replace(value, "[REDACTED]")
    return scrubbed
