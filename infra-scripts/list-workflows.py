import os
import requests
"""
List all workflow files of the swissfintecinnovations github organization.
https://github.com/swissfintechinnovations
"""
# Configuration
GITHUB_TOKEN = "${{ github.SFTI_BOT_UNPRIV_TOKEN }}"  # your personal access token (PAT) -> settings -> developer settings
REPO_OWNER = "swissfintechinnovations"
REPO_NAMES = [".github", 'ca-payment', 'ca-mortgage', 'ca-card', 'ca-wealth', 'ca-pension', 'ca-shared', 'ca-security']

def list_repo_workflows(owner, repos, token):
    for repo in repos:
        list_workflows(owner, repo, token)

def list_workflows(owner, repo, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        resp = response.json()
        total_count = resp.get("total_count", [])
        workflows = resp.get("workflows", [])
        print(f"{owner}/{repo} ({total_count}):")
        if not workflows:
            print("No workflows found.")
            return

        for workflow in workflows:
            filename = os.path.basename(workflow["path"])
            print(f"    - {filename}: {workflow['name']}")
    else:
        print(f"Failed to fetch workflows: {response.status_code}")
        print(response.json().get("message", "Unknown error"))


def list_repositories(org, token):
    url = f"https://api.github.com/orgs/{org}/repos"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        repos = response.json()
        if not repos:
            print(f"No repositories found in organization: {org}")
            return

        print(f"Repositories in organization {org}:")
        for repo in repos:
            print(f"- {repo['name']}")

        print([repo['name'] for repo in repos])

    else:
        print(f"Failed to fetch repositories: {response.status_code}")
        print(response.json().get("message", "Unknown error"))


if __name__ == "__main__":
    # list_repositories(REPO_OWNER, GITHUB_TOKEN)
    list_repo_workflows(REPO_OWNER, REPO_NAMES, GITHUB_TOKEN)
