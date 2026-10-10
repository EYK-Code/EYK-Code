#!/usr/bin/env python3
"""Profil README.md dosyasını GitHub projelerine göre günceller.

Yalnızca README içindeki işaretçiler arasındaki bölümleri değiştirir:
  <!-- PROJECTS:START --> ... <!-- PROJECTS:END -->
  <!-- LANGUAGES:START --> ... <!-- LANGUAGES:END -->
  <!-- STATS:START --> ... <!-- STATS:END -->
İşaretçilerin dışındaki hiçbir şeye dokunmaz. README'nin geri kalanında
(Technologies vb.) olmayan dil/topic'leri PR açıklamasında öneri olarak listeler.
"""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CONFIG = ROOT / "config.json"
PR_BODY = ROOT / "pr_body.md"

DEFAULTS = {
    "max_projects": 6,
    "exclude": [],          # README'de görünmesini istemediğin repo adları
    "pinned": [],           # her zaman en üstte görünecek repo adları
    "include_forks": False,
}


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_repos(user):
    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/users/{user}/repos?per_page=100&page={page}&sort=pushed&type=owner")
        repos += batch
        if len(batch) < 100:
            return repos
        page += 1


def replace_block(text, name, content):
    pattern = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        print(f"uyarı: README'de {name} işaretçileri yok, atlandı", file=sys.stderr)
        return text
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def badge(label, color="0A7C86", message=None, style="for-the-badge"):
    esc = lambda s: urllib.parse.quote(s.replace("-", "--").replace("_", "__"), safe="")
    path = f"{esc(label)}-{esc(message)}-{color}" if message is not None else f"{esc(label)}-{color}"
    return f"![{label}](https://img.shields.io/badge/{path}?style={style})"


def ts(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def project_card(r):
    name = html.escape(r["name"])
    desc = html.escape(r["description"] or "No description yet.")
    lang = r["language"]
    stars = r["stargazers_count"]
    bits = []
    if lang:
        bits.append(f"<code>{html.escape(lang)}</code>")
    if stars:
        bits.append(f"⭐ {stars}")
    meta = " &nbsp;·&nbsp; ".join(bits)
    return (
        f'<td width="50%" valign="top">\n\n'
        f'### 📁 [{name}]({r["html_url"]})\n\n'
        f'{desc}\n\n'
        f'{meta}\n\n'
        f'</td>'
    )


def render_projects(shown):
    if not shown:
        return "_No public projects yet._"
    cells = [project_card(r) for r in shown]
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        if len(pair) == 1:
            pair.append('<td width="50%"></td>')
        rows.append("<tr>\n" + "\n".join(pair) + "\n</tr>")
    return '<div align="center">\n\n<table>\n' + "\n".join(rows) + "\n</table>\n\n</div>"


def main():
    user = os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not user:
        sys.exit("GH_USER ortam değişkeni gerekli (GitHub kullanıcı adın).")
    cfg = load_config()

    repos = [
        r for r in fetch_repos(user)
        if r["name"].lower() != user.lower()          # profil reposunun kendisi
        and not r["archived"]
        and not r["private"]
        and r["name"] not in cfg["exclude"]
        and (cfg["include_forks"] or not r["fork"])
    ]

    pinned = {n: i for i, n in enumerate(cfg["pinned"])}
    repos.sort(key=lambda r: (pinned.get(r["name"], 10**6), -ts(r["pushed_at"])))
    shown = repos[: cfg["max_projects"]]

    langs = Counter(r["language"] for r in repos if r["language"])
    stars = sum(r["stargazers_count"] for r in repos)

    stats_md = '<div align="center">\n\n' + " ".join([
        badge("Public Repos", "0A7C86", str(len(repos))),
        badge("Stars", "512BD4", str(stars)),
        badge("Languages", "FF6B35", str(len(langs))),
    ]) + "\n\n</div>"

    langs_md = '<div align="center">\n\n' + (" ".join(
        badge(lang, "512BD4", str(n), style="flat-square") for lang, n in langs.most_common(10)
    ) or "_No data._") + "\n\n</div>"

    if not README.exists():
        sys.exit("README.md bulunamadı.")
    text = README.read_text(encoding="utf-8")
    new = replace_block(text, "PROJECTS", render_projects(shown))
    new = replace_block(new, "LANGUAGES", langs_md)
    new = replace_block(new, "STATS", stats_md)

    changed = new != text
    if changed:
        README.write_text(new, encoding="utf-8")

    # --- PR açıklaması: ne değişti + senden gelmesi gereken kararlar ---
    lower = text.lower()
    seen_langs = {r["language"] for r in repos if r["language"]}
    seen_topics = {t for r in repos for t in r.get("topics", [])}
    suggest = sorted(
        x for x in seen_langs | seen_topics if x.lower() not in lower
    )
    missing = [r["name"] for r in shown if not r["description"]]

    body = ["README, GitHub projelerine göre otomatik güncellendi.", "",
            f"- Listelenen proje: {len(shown)} / toplam {len(repos)}"]
    if suggest:
        body += ["", "**README'de geçmeyen ama projelerinde kullandığın teknolojiler** "
                     "(Technologies bölümüne eklemek ister misin?):"]
        body += [f"- {s}" for s in suggest]
    if missing:
        body += ["", "**Açıklaması olmayan repolar** (GitHub'da açıklama eklersen kartlar daha iyi görünür):"]
        body += [f"- {n}" for n in missing]
    body += ["", "Onaylamak için merge et, istemiyorsan kapat."]
    PR_BODY.write_text("\n".join(body), encoding="utf-8")

    print("README güncellendi." if changed else "Değişiklik yok.")


if __name__ == "__main__":
    main()
