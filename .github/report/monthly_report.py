#!/usr/bin/env python3
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple


API_VERSION = "2022-11-28"
MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 2
STALE_BRANCH_DAYS = 90

ROOT_STREAM_LABELS = {
    "ca-payment": "XS2A/Payments",
    "ca-mortgage": "Mortgage",
    "ca-wealth": "Wealth",
    "ca-card": "Card",
    "ca-pension": "Pension",
    "ca-security": "API Security and Consent Management",
}

STREAM_ORDER = [
    "ca-payment",
    "ca-mortgage",
    "ca-wealth",
    "ca-card",
    "ca-pension",
    "ca-security",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[monthly-org-activity] {ts} - {msg}", flush=True)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


GITHUB_TOKEN = require_env("GITHUB_TOKEN")
GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_GRAPHQL_URL = os.environ.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql").rstrip("/")
GITHUB_SERVER_URL = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")

ORG_NAME = require_env("ORG_NAME")
REPORT_REPO = require_env("REPORT_REPO")
REPORT_OWNER, REPORT_REPO_NAME = REPORT_REPO.split("/", 1)

SINCE = require_env("SINCE")
UNTIL_EXCLUSIVE = require_env("UNTIL_EXCLUSIVE")
UNTIL_INCLUSIVE = require_env("UNTIL_INCLUSIVE")
REPORT_MONTH = require_env("REPORT_MONTH")
REPORT_MONTH_NAME = require_env("REPORT_MONTH_NAME")
REPORT_YEAR = require_env("REPORT_YEAR")

REPORT_DIR = "reports"
REPORT_FILENAME = f"github_report_{REPORT_YEAR}_{REPORT_MONTH.split('-')[1]}.md"
REPORT_PATH = os.path.join(REPORT_DIR, REPORT_FILENAME)


@dataclass
class Repo:
    name: str
    full_name: str
    default_branch: str
    html_url: str
    archived: bool
    disabled: bool
    is_private: bool
    has_wiki: bool


@dataclass
class IssueItem:
    number: int
    title: str
    url: str
    tag: str  # new | modified | ""


@dataclass
class PullRequestItem:
    number: int
    title: str
    url: str
    tag: str  # merged | closed | draft | open


@dataclass
class BranchItem:
    name: str
    url: str
    last_commit_sha: str
    last_commit_date: Optional[str]
    stale: bool
    protected: bool


@dataclass
class RepoActivity:
    repo: Repo
    pr_merged: int = 0
    pr_closed: int = 0
    pr_draft: int = 0
    pr_open_current: int = 0
    issues_new: int = 0
    issues_active_excl_new: int = 0
    issues_open: int = 0
    commits: int = 0
    contributors: int = 0
    wiki_new_pages: int = 0
    wiki_modified_pages: int = 0
    issue_items: List[IssueItem] = field(default_factory=list)
    pr_items: List[PullRequestItem] = field(default_factory=list)
    branch_items: List[BranchItem] = field(default_factory=list)
    wiki_items: List[Tuple[str, str]] = field(default_factory=list)  # (tag, path)


def github_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "monthly-org-activity-action/1.0",
    }
    if extra:
        headers.update(extra)
    return headers


def parse_json_response(resp) -> Tuple[dict, dict]:
    body = resp.read().decode("utf-8")
    data = json.loads(body) if body else {}
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return data, headers


def request_json(
    method: str,
    url: str,
    *,
    body: Optional[dict] = None,
    headers: Optional[Dict[str, str]] = None,
    expected: Iterable[int] = (200,),
) -> Tuple[dict, dict]:
    payload = None
    merged_headers = github_headers(headers)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=payload, headers=merged_headers, method=method)
            with urllib.request.urlopen(req, timeout=90) as resp:
                if resp.status not in expected:
                    raise RuntimeError(f"Unexpected status {resp.status} for {method} {url}")
                data, resp_headers = parse_json_response(resp)
                remaining = resp_headers.get("x-ratelimit-remaining")
                used = resp_headers.get("x-ratelimit-used")
                resource = resp_headers.get("x-ratelimit-resource")
                if remaining is not None:
                    log(f"{method} {url} -> {resp.status} (resource={resource}, remaining={remaining}, used={used})")
                else:
                    log(f"{method} {url} -> {resp.status}")
                return data, resp_headers

        except urllib.error.HTTPError as e:
            status = e.code
            headers_l = {k.lower(): v for k, v in e.headers.items()}
            body_text = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {status} for {method} {url}: {body_text}")

            retry_after = headers_l.get("retry-after")
            remaining = headers_l.get("x-ratelimit-remaining")
            reset = headers_l.get("x-ratelimit-reset")

            if status in (403, 429, 500, 502, 503, 504):
                sleep_for = BACKOFF_BASE_SECONDS ** attempt
                if retry_after:
                    try:
                        sleep_for = max(sleep_for, int(retry_after))
                    except ValueError:
                        pass
                elif remaining == "0" and reset:
                    try:
                        reset_epoch = int(reset)
                        sleep_for = max(sleep_for, reset_epoch - int(time.time()) + 1)
                    except ValueError:
                        pass

                if attempt < MAX_RETRIES:
                    log(f"{method} {url} failed with HTTP {status}; retrying in {sleep_for}s")
                    time.sleep(sleep_for)
                    continue

            raise last_error

        except urllib.error.URLError as e:
            last_error = RuntimeError(f"Network error for {method} {url}: {e}")
            sleep_for = BACKOFF_BASE_SECONDS ** attempt
            if attempt < MAX_RETRIES:
                log(f"{method} {url} network error; retrying in {sleep_for}s")
                time.sleep(sleep_for)
                continue
            raise last_error

    raise last_error if last_error else RuntimeError(f"Request failed: {method} {url}")


def rest_url(path: str, params: Optional[dict] = None) -> str:
    base = f"{GITHUB_API_URL}{path}"
    if not params:
        return base
    return f"{base}?{urllib.parse.urlencode(params)}"


def graphql(query: str, variables: dict) -> dict:
    data, _ = request_json(
        "POST",
        GITHUB_GRAPHQL_URL,
        body={"query": query, "variables": variables},
        headers={"Accept": "application/json"},
        expected=(200,),
    )
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {json.dumps(data['errors'])}")
    return data["data"]


def parse_link_header(link_header: Optional[str]) -> Dict[str, str]:
    result = {}
    if not link_header:
        return result
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part.strip())
        if m:
            result[m.group(2)] = m.group(1)
    return result


def paginate_rest_list(url: str) -> List[dict]:
    items: List[dict] = []
    next_url = url
    while next_url:
        data, headers = request_json("GET", next_url, expected=(200,))
        if not isinstance(data, list):
            raise RuntimeError(f"Expected list payload from {next_url}, got: {type(data)}")
        items.extend(data)
        links = parse_link_header(headers.get("link"))
        next_url = links.get("next")
    return items


def list_org_repos() -> List[Repo]:
    repos_raw = paginate_rest_list(
        rest_url(f"/orgs/{ORG_NAME}/repos", {"type": "public", "per_page": 100, "sort": "full_name", "page": 1})
    )

    repos: List[Repo] = []
    for r in repos_raw:
        if r.get("archived") or r.get("disabled"):
            continue
        repos.append(
            Repo(
                name=r["name"],
                full_name=r["full_name"],
                default_branch=r["default_branch"],
                html_url=r["html_url"],
                archived=bool(r["archived"]),
                disabled=bool(r["disabled"]),
                is_private=bool(r["private"]),
                has_wiki=bool(r.get("has_wiki", False)),
            )
        )

    repos.sort(key=lambda x: x.name.lower())
    log(f"Discovered {len(repos)} active public repositories in org {ORG_NAME}")
    return repos


def graphql_search_count(search_query: str) -> int:
    query = """
    query($q: String!) {
      rateLimit {
        cost
        remaining
        resetAt
      }
      search(query: $q, type: ISSUE, first: 1) {
        issueCount
      }
    }
    """
    data = graphql(query, {"q": search_query})
    rl = data["rateLimit"]
    log(f"GraphQL search count={data['search']['issueCount']} cost={rl['cost']} remaining={rl['remaining']} q={search_query}")
    return int(data["search"]["issueCount"])


def graphql_search_issue_nodes(search_query: str) -> List[IssueItem]:
    query = """
    query($q: String!, $cursor: String) {
      rateLimit {
        cost
        remaining
        resetAt
      }
      search(query: $q, type: ISSUE, first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          ... on Issue {
            number
            title
            url
          }
        }
      }
    }
    """
    items: List[IssueItem] = []
    cursor = None
    while True:
        data = graphql(query, {"q": search_query, "cursor": cursor})
        rl = data["rateLimit"]
        log(f"GraphQL search page cost={rl['cost']} remaining={rl['remaining']} q={search_query}")
        search = data["search"]
        for node in search["nodes"]:
            if not node:
                continue
            items.append(
                IssueItem(
                    number=int(node["number"]),
                    title=node["title"],
                    url=node["url"],
                    tag="",
                )
            )
        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]
    return items


def graphql_search_pr_nodes(search_query: str) -> List[PullRequestItem]:
    query = """
    query($q: String!, $cursor: String) {
      rateLimit {
        cost
        remaining
        resetAt
      }
      search(query: $q, type: ISSUE, first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          ... on PullRequest {
            number
            title
            url
            isDraft
            state
            merged
          }
        }
      }
    }
    """
    items: List[PullRequestItem] = []
    cursor = None
    while True:
        data = graphql(query, {"q": search_query, "cursor": cursor})
        rl = data["rateLimit"]
        log(f"GraphQL PR search page cost={rl['cost']} remaining={rl['remaining']} q={search_query}")
        search = data["search"]
        for node in search["nodes"]:
            if not node:
                continue

            if node.get("merged"):
                tag = "merged"
            elif node.get("isDraft"):
                tag = "draft"
            elif node.get("state") == "CLOSED":
                tag = "closed"
            else:
                tag = "open"

            items.append(
                PullRequestItem(
                    number=int(node["number"]),
                    title=node["title"],
                    url=node["url"],
                    tag=tag,
                )
            )
        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]
    return items


def graphql_releases_for_repo(owner: str, repo: str, cursor: Optional[str]) -> dict:
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        releases(first: 50, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes {
            name
            tagName
            url
            createdAt
            isDraft
            isPrerelease
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
      rateLimit {
        cost
        remaining
        resetAt
      }
    }
    """
    return graphql(query, {"owner": owner, "repo": repo, "cursor": cursor})


def count_root_level_yaml_files(repo: Repo) -> int:
    data, _ = request_json(
        "GET",
        rest_url(f"/repos/{ORG_NAME}/{repo.name}/contents"),
        expected=(200,),
    )
    if not isinstance(data, list):
        return 0

    count = 0
    for item in data:
        if item.get("type") != "file":
            continue
        name = item.get("name", "")
        if name.endswith(".yaml") or name.endswith(".yml"):
            count += 1
    return count


def search_count_repo_scoped(kind_query: str, repo_full_name: str) -> int:
    return graphql_search_count(f"repo:{repo_full_name} {kind_query}")


def collect_pr_metrics(repos: List[Repo]) -> Dict[str, int]:
    merged = 0
    closed = 0
    draft = 0
    open_now = 0
    window = f"{SINCE}..{UNTIL_INCLUSIVE}"

    for repo in repos:
        merged += search_count_repo_scoped(f"is:pr is:merged merged:{window}", repo.full_name)
        closed += search_count_repo_scoped(f"is:pr is:closed -is:merged closed:{window}", repo.full_name)
        draft += search_count_repo_scoped("is:pr is:open created:<{UNTIL_INCLUSIVE} draft:true", repo.full_name)
        open_now += search_count_repo_scoped("is:pr is:open created:<{UNTIL_INCLUSIVE} draft:false", repo.full_name)

    return {
        "merged": merged,
        "closed": closed,
        "draft": draft,
        "open_current": open_now,
    }


def collect_issue_metrics(repos: List[Repo]) -> Dict[str, int]:
    new_issues = 0
    active_issues = 0
    open_issues = 0
    window = f"{SINCE}..{UNTIL_INCLUSIVE}"

    for repo in repos:
        new_count = search_count_repo_scoped(f"is:issue created:{window}", repo.full_name)
        active_excl_new_count = search_count_repo_scoped(
            f"is:issue updated:{window} -created:{window}",
            repo.full_name,
        )
        open_count = search_count_repo_scoped("is:issue is:open created:<{UNTIL_INCLUSIVE}", repo.full_name)

        new_issues += new_count
        active_issues += active_excl_new_count
        open_issues += open_count

    return {
        "new": new_issues,
        "active_excl_new": active_issues,
        "open": open_issues,
    }


def collect_commit_metrics(repos: List[Repo]) -> Dict[str, int]:
    total_commits = 0
    unique_contributors: Set[str] = set()

    for repo in repos:
        repo_commits, repo_contributors = collect_repo_commit_metrics(repo)
        total_commits += repo_commits
        unique_contributors.update(repo_contributors)

    return {
        "commits": total_commits,
        "contributors": len(unique_contributors),
    }


def collect_repo_commit_metrics(repo: Repo) -> Tuple[int, Set[str]]:
    branch_names = []
    branches_raw = paginate_rest_list(
        rest_url(f"/repos/{ORG_NAME}/{repo.name}/branches", {"per_page": 100, "page": 1})
    )
    for branch in branches_raw:
        branch_names.append(branch["name"])

    seen_commit_shas: Set[str] = set()
    unique_contributors: Set[str] = set()

    for branch_name in branch_names:
        url = rest_url(
            f"/repos/{ORG_NAME}/{repo.name}/commits",
            {
                "sha": branch_name,
                "since": SINCE,
                "until": UNTIL_INCLUSIVE,
                "per_page": 100,
                "page": 1,
            },
        )

        while url:
            data, headers = request_json("GET", url, expected=(200,))
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected commits response for {repo.full_name}: {data}")

            for commit in data:
                sha = commit.get("sha")
                if not sha or sha in seen_commit_shas:
                    continue

                seen_commit_shas.add(sha)

                author = commit.get("author")
                if author and author.get("login"):
                    unique_contributors.add(f"login:{author['login']}")
                else:
                    raw_author = (commit.get("commit") or {}).get("author") or {}
                    email = raw_author.get("email")
                    if email:
                        unique_contributors.add(f"email:{email.strip().lower()}")

            links = parse_link_header(headers.get("link"))
            url = links.get("next")

    return len(seen_commit_shas), unique_contributors


def run_git(cmd: List[str], cwd: Optional[str] = None) -> str:
    log("git " + " ".join(shlex.quote(x) for x in cmd[1:]))
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return proc.stdout


def wiki_clone_url(repo_name: str) -> str:
    parsed = urllib.parse.urlparse(GITHUB_SERVER_URL)
    host = parsed.netloc
    prefix = parsed.path.rstrip("/")
    repo_path = f"{ORG_NAME}/{repo_name}.wiki.git"
    return f"{parsed.scheme}://x-access-token:{urllib.parse.quote(GITHUB_TOKEN, safe='')}@{host}{prefix}/{repo_path}"


def is_wiki_page_file(path: str) -> bool:
    page_exts = {
        ".md", ".markdown", ".mdown", ".rst", ".textile",
        ".adoc", ".asciidoc", ".org", ".creole", ".mediawiki", ".wiki"
    }
    return os.path.splitext(path.lower())[1] in page_exts


def get_last_commit_before(repo_dir: str, before_iso: str) -> Optional[str]:
    out = run_git(["git", "rev-list", "-1", f"--before={before_iso}", "HEAD"], cwd=repo_dir).strip()
    return out or None


def list_files_at_commit(repo_dir: str, rev: str) -> Set[str]:
    out = run_git(["git", "ls-tree", "-r", "--name-only", rev], cwd=repo_dir)
    return {line.strip() for line in out.splitlines() if line.strip()}


def analyze_wiki_repo(repo: Repo) -> Tuple[int, int, List[Tuple[str, str]]]:
    if not repo.has_wiki:
        return 0, 0, []

    with tempfile.TemporaryDirectory(prefix=f"wiki-{repo.name}-") as tmpdir:
        target = os.path.join(tmpdir, "wiki")
        cloned = False
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                run_git(["git", "clone", "--quiet", wiki_clone_url(repo.name), target], cwd=tmpdir)
                cloned = True
                break
            except subprocess.CalledProcessError as e:
                last_error = e.stderr or str(e)
                sleep_for = BACKOFF_BASE_SECONDS ** attempt
                if attempt < MAX_RETRIES:
                    log(f"Wiki clone failed for {repo.name}; retrying in {sleep_for}s")
                    time.sleep(sleep_for)

        if not cloned:
            text = (last_error or "").lower()
            if "not found" in text or "repository not found" in text:
                return 0, 0, []
            raise RuntimeError(f"Unable to clone wiki repo for {repo.full_name}: {last_error}")

        try:
            run_git(["git", "rev-parse", "HEAD"], cwd=target)
        except subprocess.CalledProcessError:
            return 0, 0, []

        before_rev = get_last_commit_before(target, SINCE)
        existing_before: Set[str] = set()
        if before_rev:
            existing_before = {p for p in list_files_at_commit(target, before_rev) if is_wiki_page_file(p)}

        log_output = run_git(
            [
                "git", "log",
                "--since", SINCE,
                "--until", UNTIL_INCLUSIVE,
                "--name-status",
                "--format=__COMMIT__%H",
                "--no-renames",
            ],
            cwd=target,
        )

        if not log_output.strip():
            return 0, 0, []

        new_pages: Set[str] = set()
        modified_pages: Set[str] = set()

        for line in log_output.splitlines():
            if not line or line.startswith("__COMMIT__"):
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, path = parts[0].strip(), parts[1].strip()
            if not is_wiki_page_file(path):
                continue

            if status == "A":
                if path not in existing_before:
                    new_pages.add(path)
                else:
                    modified_pages.add(path)
            elif status in {"M", "T"}:
                if path in existing_before:
                    modified_pages.add(path)

        items: List[Tuple[str, str]] = []
        for path in sorted(new_pages):
            items.append((f"{'new':<10} ", path))
        for path in sorted(modified_pages):
            items.append((f"{'modified':<10} ", path))

        return len(new_pages), len(modified_pages), items


def collect_wiki_metrics(repos: List[Repo]) -> Dict[str, int]:
    total_new = 0
    total_modified = 0

    for repo in repos:
        new_pages, modified_pages, _ = analyze_wiki_repo(repo)
        total_new += new_pages
        total_modified += modified_pages

    return {
        "new_pages": total_new,
        "modified_pages": total_modified,
    }


def collect_monthly_releases(repos: List[Repo]) -> List[dict]:
    releases = []
    since_dt = datetime.strptime(SINCE, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    until_dt = datetime.strptime(UNTIL_EXCLUSIVE, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    for repo in repos:
        cursor = None
        while True:
            data = graphql_releases_for_repo(ORG_NAME, repo.name, cursor)
            repo_data = data.get("repository")
            if not repo_data:
                break

            nodes = repo_data["releases"]["nodes"]
            page_info = repo_data["releases"]["pageInfo"]

            stop_repo = False
            for rel in nodes:
                if rel["isDraft"]:
                    continue

                created_at = datetime.strptime(rel["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if created_at < since_dt:
                    stop_repo = True
                    break

                if since_dt <= created_at < until_dt:
                    display_name = rel["name"] or rel["tagName"]
                    releases.append(
                        {
                            "repo": repo.name,
                            "name": display_name,
                            "url": rel["url"],
                            "createdAt": rel["createdAt"],
                            "isPrerelease": rel["isPrerelease"],
                        }
                    )

            if stop_repo or not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]

    releases.sort(key=lambda x: (x["createdAt"], x["repo"], x["name"]), reverse=True)
    return releases


def collect_stream_yaml_counts(repos: List[Repo]) -> Dict[str, int]:
    repo_lookup = {r.name: r for r in repos}
    counts: Dict[str, int] = {}

    for repo_name in STREAM_ORDER:
        repo = repo_lookup.get(repo_name)
        if not repo:
            counts[repo_name] = 0
            continue
        counts[repo_name] = count_root_level_yaml_files(repo)

    return counts


def iso_to_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def collect_repo_pull_requests(repo: Repo) -> Tuple[List[PullRequestItem], int, int, int, int]:
    window = f"{SINCE}..{UNTIL_INCLUSIVE}"

    merged_prs = graphql_search_pr_nodes(
        f"repo:{repo.full_name} is:pr is:merged merged:{window} sort:updated-asc"
    )
    closed_prs = graphql_search_pr_nodes(
        f"repo:{repo.full_name} is:pr is:closed -is:merged closed:{window} sort:updated-asc"
    )
    draft_prs = graphql_search_pr_nodes(
        f"repo:{repo.full_name} is:pr is:open draft:true created:<{UNTIL_INCLUSIVE} sort:created-asc"
    )
    open_prs = graphql_search_pr_nodes(
        f"repo:{repo.full_name} is:pr is:open draft:false created:<{UNTIL_INCLUSIVE} sort:created-asc"
    )

    for pr in merged_prs:
        pr.tag = "merged"
    for pr in closed_prs:
        pr.tag = "closed"
    for pr in draft_prs:
        pr.tag = "draft"
    for pr in open_prs:
        pr.tag = "open"

    all_items = merged_prs + closed_prs + draft_prs + open_prs
    all_items.sort(key=lambda x: x.number)

    return (
        all_items,
        len(merged_prs),
        len(closed_prs),
        len(draft_prs),
        len(open_prs),
    )


def collect_open_issues(repo: Repo) -> Tuple[List[IssueItem], int, int, int]:
    window = f"{SINCE}..{UNTIL_INCLUSIVE}"

    open_issues = graphql_search_issue_nodes(
        f"repo:{repo.full_name} is:issue is:open created:<{UNTIL_INCLUSIVE} sort:created-asc"
    )
    new_issue_numbers = {
        item.number for item in graphql_search_issue_nodes(
            f"repo:{repo.full_name} is:issue is:open created:{window} sort:created-asc"
        )
    }
    modified_issue_numbers = {
        item.number for item in graphql_search_issue_nodes(
            f"repo:{repo.full_name} is:issue is:open updated:{window} -created:{window} sort:updated-asc"
        )
    }

    for issue in open_issues:
        if issue.number in new_issue_numbers:
            issue.tag = "new"
        elif issue.number in modified_issue_numbers:
            issue.tag = "modified"
        else:
            issue.tag = ""

    open_issues.sort(key=lambda x: x.number)

    return (
        open_issues,
        len(new_issue_numbers),
        len(modified_issue_numbers),
        len(open_issues),
    )


def collect_branch_items(repo: Repo) -> List[BranchItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_BRANCH_DAYS)
    branches_raw = paginate_rest_list(
        rest_url(f"/repos/{ORG_NAME}/{repo.name}/branches", {"per_page": 100, "page": 1})
    )

    branch_items: List[BranchItem] = []
    for branch in branches_raw:
        name = branch["name"]
        sha = branch["commit"]["sha"]
        protected = bool(branch.get("protected", False))

        commit_data, _ = request_json(
            "GET",
            rest_url(f"/repos/{ORG_NAME}/{repo.name}/commits/{sha}"),
            expected=(200,),
        )

        raw_commit = commit_data.get("commit") or {}
        committer = raw_commit.get("committer") or {}
        author = raw_commit.get("author") or {}
        commit_date = committer.get("date") or author.get("date")

        stale = False
        if commit_date:
            stale = iso_to_dt(commit_date) < cutoff

        branch_items.append(
            BranchItem(
                name=name,
                url=f"{repo.html_url}/tree/{urllib.parse.quote(name, safe='')}",
                last_commit_sha=sha,
                last_commit_date=commit_date,
                stale=stale,
                protected=protected,
            )
        )

    def branch_sort_key(branch: BranchItem):
        if branch.name.lower() in {"main", "master"}:
            bucket = 0
        elif branch.protected:
            bucket = 1
        elif not branch.stale:
            bucket = 2
        else:
            bucket = 3
        return (bucket, branch.name.lower())

    branch_items.sort(key=branch_sort_key)
    return branch_items


def collect_repo_activity(repo: Repo) -> RepoActivity:
    activity = RepoActivity(repo=repo)

    pr_items, merged_count, closed_count, draft_count, open_count = collect_repo_pull_requests(repo)
    activity.pr_items = pr_items
    activity.pr_merged = merged_count
    activity.pr_closed = closed_count
    activity.pr_draft = draft_count
    activity.pr_open_current = open_count

    open_issues, new_open_count, modified_open_count, total_open_count = collect_open_issues(repo)
    activity.issue_items = open_issues
    activity.issues_new = new_open_count
    activity.issues_active_excl_new = modified_open_count
    activity.issues_open = total_open_count

    repo_commit_count, repo_contributors = collect_repo_commit_metrics(repo)
    activity.commits = repo_commit_count
    activity.contributors = len(repo_contributors)

    activity.branch_items = collect_branch_items(repo)
    activity.wiki_new_pages, activity.wiki_modified_pages, activity.wiki_items = analyze_wiki_repo(repo)

    return activity


def wiki_page_url(repo: Repo, path: str) -> str:
    page_name = os.path.splitext(os.path.basename(path))[0].strip()
    slug = re.sub(r"\s+", "-", page_name)
    return f"{repo.html_url}/wiki/{urllib.parse.quote(slug, safe='-_.()')}"


def render_pr_lines(pr_items: List[PullRequestItem]) -> str:
    if not pr_items:
        return "  - none"

    lines = []
    for pr in pr_items:
        tag = f"{pr.tag:<10} " if pr.tag else ""
        lines.append(f"  - {tag:13}#{pr.number} [{pr.title}]({pr.url})")
    return "\n".join(lines)


def render_issue_lines(issue_items: List[IssueItem]) -> str:
    if not issue_items:
        return "  - none"

    lines = []
    for issue in issue_items:
        tag = f"{issue.tag:<10} " if issue.tag else ""
        lines.append(f"  - {tag:13}#{issue.number} [{issue.title}]({issue.url})")
    return "\n".join(lines)


def render_branch_lines(branch_items: List[BranchItem]) -> str:
    if not branch_items:
        return "  - none"

    lines = []
    for branch in branch_items:
        match (branch.protected, branch.stale):
            case (True, _):
                tag = f"{'protected':<10} "
            case (False, True):
                tag = f"{'stale':<10} "
            case _:
                tag = ""

        date_suffix = ""
        if branch.last_commit_date:
            human_date = datetime.strptime(branch.last_commit_date, "%Y-%m-%dT%H:%M:%SZ").strftime("%d %B %Y, %H:%M")
            date_suffix = f" -- last commit {human_date}"

        lines.append(f"  - {tag:13}[{branch.name}]({branch.url}){date_suffix}")
    return "\n".join(lines)


def render_wiki_lines(repo: Repo, wiki_items: List[Tuple[str, str]]) -> str:
    if not wiki_items:
        return "  - none"

    lines = []
    for tag, path in wiki_items:
        page_title = os.path.splitext(os.path.basename(path))[0]
        page_url = wiki_page_url(repo, path)
        lines.append(f"  - {tag:13}[{page_title}]({page_url})")
    return "\n".join(lines)


def render_repo_sections(repo_activities: List[RepoActivity]) -> str:
    def repo_sort_key(repo: Repo):
        return (repo.name == ".github", repo.name.lower())
    repo_activities = sorted(repo_activities, key=lambda a: repo_sort_key(a.repo))

    sections: List[str] = ["# SFTI Stream Repositories"]
    for a in repo_activities:
        if (a.repo.name == ".github"):
            sections.append("# SFTI Infrastructure Repository")  
        sections.append(
            f"""### {a.repo.name}
- Pull requests: {a.pr_merged} merged PRs / {a.pr_closed} closed PRs / {a.pr_draft} draft PRs / {a.pr_open_current} open PRs
{render_pr_lines(a.pr_items)}
- Issues: {a.issues_new} new issues / {a.issues_active_excl_new} active issues / {a.issues_open} total open issues
{render_issue_lines(a.issue_items)}
- Contribution: {a.commits} new commits by {a.contributors} distinctive contributors
- Development ({len(a.branch_items)} branches):
{render_branch_lines(a.branch_items)}
- Wiki: {a.wiki_new_pages} new wiki pages / {a.wiki_modified_pages} modified wiki pages
{render_wiki_lines(a.repo, a.wiki_items)}"""
        )
    

    if not sections:
        return "## No repositories found"

    return "\n\n".join(sections)


def render_report(
    repos: List[Repo],
    yaml_counts: Dict[str, int],
    pr_metrics: Dict[str, int],
    issue_metrics: Dict[str, int],
    commit_metrics: Dict[str, int],
    wiki_metrics: Dict[str, int],
    releases: List[dict],
    repo_activities: List[RepoActivity],
) -> str:
    total_yaml = sum(yaml_counts.values())
    stream_repo_count = sum(1 for repo_name in STREAM_ORDER if repo_name in yaml_counts)

    release_lines = []
    if releases:
        for rel in releases:
            prerelease_suffix = " (prerelease)" if rel["isPrerelease"] else ""
            release_lines.append(f"- {rel['repo']:<12} -- [{rel['name']}]({rel['url']}){prerelease_suffix}")
    else:
        release_lines.append("- No releases published in the reporting month")

    sfti_banner = r"""
```
::::... %%%@@@@@@@%%. ..::::::::::::::..   ..::::::............:...............::.....::::::::::::::..   ..::::::...............:::
:::..%%%%%.       %%%%% ..:::::::::..  %%%%% ...:::.%%%%%%%%%%.:.%%%%%%%%%%%%%.:..%%%.:::::::::::..  %%%%% ...::. %%%%%%%%%%%%% .::
:...%%%  ..::::::... %%%% .:::::::..%%%%%%%%%%%..::.%%%%%%%%%@.:.@%%%%%%%%%%%@.:..%%%.::::::::::..%%%%%%%%%%%..:. %%%%%%%%%%%%@ .::
:..%%*..:::...     ... %%% .::::::.%%#%     %%%%.::.%#%      ..:..    %#%    ..:..%#% ::::::::::.%%#%     %%%%.:. %#%      .%#% .::
. %%.       :@@@###%.:. %%%.::::::.%%#%  .... ...::.%#% .......:::::: %#% ::::::..%#% :::::::::. %%#%    ....:::. %#% ......%#% .::
.%%% %%%%%@%#    #+ .::.*%% ::::::. %%%%%%   ..::::.%#%.#####%.:::::: %#% ::::::..%#% :       :. %%#%   ...:::::. %#%.#####%%#% :::
.%%%%%%%#    @@@  # :::. %% :::::::.. .%%%%%%% ..::.%#%%%%%%%@.:::::: %#% ::::::..%#% : %###% :. %%#%   ...:::::. %#%%%%%%%%%#% .::
.%%%%#   @@@@   #...:::.+%% :::::::.....   %%%%..::.%#%      ..:::::: %#% ::::::..%#% :.......:. %%#%  ...::::::. %#%      .%#% .::
..%   #@@@@   %%..::::. %%%.:::::.. % ..::. .%%%.::.%#% ::::::::::::: %#% ::::::..%#% :::::::::. %%#%  ........:. %#% ::::::%#% .::
:.. @@@@@   %%% .:::.. %%% .:::::.%%%%.     %%%%.::.%#% ::::::::::::: %#% ::::::..%#% ::::::::::.%%#%  .. %%%%.:. %#% ::::::%#% .::
::: @@@@  %%%% .:... %%%% .::::::.. %%%%%%%%%%% .::.%%%.:::::::::::::.%%%.::::::..%%%.:::::::::::.%%%%%%%%%%%..:. %%%.::::::%%% .::
:::  @   %%#%     *%%%% ..:::::::::..  %%%%%  ..:::.%:%.:::::::::::::.%:%.::::::..%:%.:::::::::::..  %%%%% ...::. %:%.::::::%:% .::
::::   .@%%%%%@@@@%%. ..::::::::::::::..   ..::::::.....:::::::::::::.....:::::::.....:::::::::::::::..   ..::::.......::::.....:::
```
"""

    repo_sections = render_repo_sections(repo_activities)

    return f"""filename: {REPORT_FILENAME}  
report time: {SINCE} - {UNTIL_INCLUSIVE}  

{sfti_banner}


# Summary {REPORT_MONTH_NAME} {REPORT_YEAR} {ORG_NAME} GitHub organisation

SFTI maintains {total_yaml} financial-related API specifications in {stream_repo_count} repos streams.
- XS2A/Payments: {yaml_counts.get('ca-payment', 0)}
- Mortgage: {yaml_counts.get('ca-mortgage', 0)}
- Wealth: {yaml_counts.get('ca-wealth', 0)}
- Card: {yaml_counts.get('ca-card', 0)}
- Pension: {yaml_counts.get('ca-pension', 0)}
- API Security and Consent Management: {yaml_counts.get('ca-security', 0)}

### Releases
{chr(10).join(release_lines)}

### Common SFTI Repo indicators
- Pull requests: {pr_metrics['merged']} merged PRs / {pr_metrics['closed']} closed PRs / {pr_metrics['draft']} draft PRs / {pr_metrics['open_current']} open PRs
- Issues: {issue_metrics['new']} new issues / {issue_metrics['active_excl_new']} active issues / {issue_metrics['open']} total open issues
- Contribution: {commit_metrics['commits']} new commits by {commit_metrics['contributors']} distinctive contributors
- Wiki: {wiki_metrics['new_pages']} new wiki pages / {wiki_metrics['modified_pages']} modified wiki pages

{repo_sections}
""".rstrip() + "\n"


def ensure_report_dir() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)


def main() -> None:
    log(f"Starting org report for {ORG_NAME}, month={REPORT_MONTH}")
    log(f"Window since={SINCE} until_exclusive={UNTIL_EXCLUSIVE} until_inclusive={UNTIL_INCLUSIVE}")

    repos = list_org_repos()
    yaml_counts = collect_stream_yaml_counts(repos)
    releases = collect_monthly_releases(repos)

    pr_metrics = collect_pr_metrics(repos)
    issue_metrics = collect_issue_metrics(repos)
    commit_metrics = collect_commit_metrics(repos)
    wiki_metrics = collect_wiki_metrics(repos)

    repo_activities: List[RepoActivity] = []
    for repo in repos:
        log(f"Collecting per-repo section data for {repo.full_name}")
        repo_activities.append(collect_repo_activity(repo))

    report = render_report(
        repos=repos,
        yaml_counts=yaml_counts,
        pr_metrics=pr_metrics,
        issue_metrics=issue_metrics,
        commit_metrics=commit_metrics,
        wiki_metrics=wiki_metrics,
        releases=releases,
        repo_activities=repo_activities,
    )

    ensure_report_dir()
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"ERROR: {exc}")
        raise