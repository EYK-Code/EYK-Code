import json
import os
import urllib.request

GITHUB_USERNAME = os.environ.get("GITHUB_ACTOR", "EYK-Code")
CONFIG_FILE = "config.json"
README_FILE = "README.md"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"max_projects": 6, "include_forks": False, "pinned_repos": [], "exclude_repos": []}

def fetch_repos(username):
    url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Python-Script"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching repos: {e}")
        return []

def generate_markdown(repos, config):
    exclude = set(config.get("exclude_repos", []))
    exclude.add(GITHUB_USERNAME.lower()) # EYK-Code profil reponun kendisini listede gösterme
    
    include_forks = config.get("include_forks", False)
    max_projects = config.get("max_projects", 6)
    pinned = config.get("pinned_repos", [])

    filtered_repos = []
    languages = set()

    for repo in repos:
        name = repo["name"]
        if repo["archived"] or name.lower() in [e.lower() for e in exclude]:
            continue
        if repo["fork"] and not include_forks:
            continue
        
        filtered_repos.append(repo)
        if repo.get("language"):
            languages.add(repo["language"])

    pinned_list = [r for r in filtered_repos if r["name"] in pinned]
    other_list = [r for r in filtered_repos if r["name"] not in pinned]
    final_repos = (pinned_list + other_list)[:max_projects]

    # Proje Listesi
    projects_md = "### 🚀 Son Aktif Projelerim\n\n"
    for r in final_repos:
        desc = r['description'] or 'Açıklama henüz eklenmemiş.'
        lang = f" `{r['language']}`" if r.get("language") else ""
        stars = f" ⭐ {r['stargazers_count']}" if r['stargazers_count'] > 0 else ""
        projects_md += f"- **[{r['name']}]({r['html_url']})**{lang}{stars} - {desc}\n"

    # Diller
    langs_md = "### 🛠️ Kullandığım Diller & Teknolojiler\n\n"
    langs_md += " ".join([f"`{lang}`" for lang in sorted(languages)]) + "\n"

    return projects_md, langs_md

def update_readme():
    config = load_config()
    repos = fetch_repos(GITHUB_USERNAME)
    if not repos:
        print("Repo bulunamadı veya API hatası.")
        return

    projects_md, langs_md = generate_markdown(repos, config)

    with open(README_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_section(src, start_marker, end_marker, new_content):
        if start_marker in src and end_marker in src:
            before = src.split(start_marker)[0]
            after = src.split(end_marker)[1]
            return f"{before}{start_marker}\n{new_content}{end_marker}{after}"
        return src

    content = replace_section(content, "<!-- START_PROJECTS -->", "<!-- END_PROJECTS -->", projects_md)
    content = replace_section(content, "<!-- START_LANGS -->", "<!-- END_LANGS -->", langs_md)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    update_readme()
