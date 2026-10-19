"""Identity lint: GenSurf speaks its own vocabulary.

Fails when a file of the repository (its path or its text) names a
commercial CAD product or vendor, or uses a term GenSurf has replaced
with its own (see docs/glossary.md). Exceptions:

* README.md may name products inside ONE comparative sentence, the one
  that starts with ``README_MARKER``;
* gensurf/migrations.py and CHANGELOG.md may use replaced terms: they
  hold the map from old names to new ones and its history.

The lists are stored ROT13-encoded so that this file passes its own
check. Decode one with ``codecs.decode(text, "rot13")``.
"""

import codecs
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

README_MARKER = "history-based surfacing as found in tools such as"

#: files allowed to use replaced terms (never vendor names)
TERM_EXCEPTIONS = {"gensurf/migrations.py", "CHANGELOG.md"}

BINARY = (".fcstd", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf",
          ".ico", ".pyc")

# vendors and products, matched as whole words, any case
_VENDORS = [
    "pngvn", "qnffnhyg", "3qrkcrevrapr", "fbyvqjbexf", "fvrzraf",
    "havtencuvpf", "fbyvq rqtr", "cnenfbyvq", "perb", "ceb/ratvarre",
    "bafuncr", "euvab", "euvabprebf", "zparry", "bcraaheof",
    "tenffubccre", "nhgbqrfx", "shfvba 360", "vprz", "fcnprpynvz",
    "funce3q", "mj3q", "zbv3q", "pvzngeba", "vebapnq",
]
# vendor names and abbreviations that are ordinary words in lower case
_VENDORS_EXACT_CASE = ["AK", "CGP", "TFQ"]
# terms GenSurf replaced; spaces also match "_", "-" or nothing
_TERMS = [
    "trbzrgevpny frg", "zhygv frpgvba", "fjrcg fhesnpr", "jbex bowrpg",
    "funcr svyyrg", "pbaarpg pheir", "cnenyyry pheir", "pheir bssfrg 3q",
    "3q pheir bssfrg", "pybfr fhesnpr", "zhygvcyr rkgenpg",
    "zhygv rkgenpg", "arkg fbyhgvba", "pbeare ba fhccbeg", "3q pbeare",
    "chyyvat qverpgvba", "gnatrapl fhesnpr", "cbvag pbagvahvgl",
    "pbzcyrgr obhaqnel", "trarengvir funcr qrfvta", "eryvzvgre",
    "zber>>", "gjb yvzvgf", "yvzvg naq zvqqyr", "jvgu ersrerapr fhesnpr",
    "jvgu qensg qverpgvba", "jvgu gjb thvqr pheirf", "guerr thvqrf",
    "gjb thvqrf naq enqvhf", "pragre naq gjb natyrf",
    "svir thvqr pheirf", "gjb thvqr pheirf", "fzbbgu fjrrcvat",
    "gjvfgrq nern", "pnabavpny funcr qrgrpgvba",
]


def _decode(words):
    return [codecs.decode(w, "rot13") for w in words]


def _word(text):
    return r"(?<![A-Za-z0-9])" + re.escape(text) + r"(?![A-Za-z0-9])"


VENDOR_RE = re.compile(
    "|".join(_word(w) for w in _decode(_VENDORS)), re.IGNORECASE)
VENDOR_CASE_RE = re.compile(
    "|".join(_word(w) for w in _decode(_VENDORS_EXACT_CASE)))
TERM_RE = re.compile(
    "|".join(r"[\s_-]*".join(re.escape(part) for part in t.split(" "))
             for t in _decode(_TERMS)), re.IGNORECASE)


def _repo_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
        files = [f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for base, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", ".pytest_cache")]
            for name in names:
                files.append(os.path.relpath(os.path.join(base, name), ROOT))
    return sorted(f.replace(os.sep, "/") for f in files
                  if os.path.isfile(os.path.join(ROOT, f)))


def _text(path):
    if path.lower().endswith(BINARY):
        return None
    with open(os.path.join(ROOT, path), "rb") as f:
        data = f.read()
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _without_readme_list(text):
    """README text minus its single comparative sentence."""
    start = text.find(README_MARKER)
    if start < 0:
        return text
    end = text.find(".", start)
    end = len(text) if end < 0 else end
    return text[:start] + text[end:]


def _hits(regex, text):
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in regex.finditer(line):
            out.append(f"{n}: {m.group(0)!r}")
    return out


def test_no_vendor_names():
    problems = {}
    for path in _repo_files():
        found = _hits(VENDOR_RE, path) + _hits(VENDOR_CASE_RE, path)
        text = _text(path)
        if text is not None:
            if path == "README.md":
                text = _without_readme_list(text)
            found += _hits(VENDOR_RE, text) + _hits(VENDOR_CASE_RE, text)
        if found:
            problems[path] = found
    assert not problems, problems


def test_no_replaced_terms():
    problems = {}
    for path in _repo_files():
        if path in TERM_EXCEPTIONS:
            continue
        found = _hits(TERM_RE, path)
        text = _text(path)
        if text is not None:
            found += _hits(TERM_RE, text)
        if found:
            problems[path] = found
    assert not problems, problems


def test_readme_has_at_most_one_comparative_list():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        assert f.read().count(README_MARKER) <= 1


def test_lint_catches_what_it_should():
    """Self-check, so a broken pattern cannot pass silently."""
    vendor = _decode(_VENDORS)[0]
    assert VENDOR_RE.search(f"built like {vendor.upper()} does")
    assert VENDOR_CASE_RE.search(_decode(_VENDORS_EXACT_CASE)[0] + " style")
    assert not VENDOR_CASE_RE.search("nx, ny = -uy, ux")
    term = _decode(_TERMS)[0]
    assert TERM_RE.search(term.title().replace(" ", ""))
    assert TERM_RE.search(term.replace(" ", "_"))
    assert not _without_readme_list(
        f"Intro. GenSurf brings {README_MARKER} {vendor}. Next."
    ).count(vendor)
