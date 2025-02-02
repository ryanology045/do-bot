# project_root/services/github_service.py

import os
import requests
import logging
import base64

logger = logging.getLogger(__name__)

class GitHubService:
    """
    Minimal interface for GitHub actions. Could commit JSON for session rollback if needed.
    """

    def __init__(self):
        self.github_token = os.environ.get("GH_TOKEN")
        if not self.github_token:
            raise ValueError("GH_TOKEN not set.")
        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json"
        }
        self.default_owner = os.environ.get("GH_OWNER", "")
        self.default_repo = os.environ.get("GH_REPO_NAME", "")

    def get_file_contents(self, owner=None, repo=None, path="README.md", ref="main"):
        if not owner:
            owner = self.default_owner
        if not repo:
            repo = self.default_repo
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 200:
            data = resp.json()
            return base64.b64decode(data.get("content", "")).decode("utf-8")
        else:
            logger.error(f"Failed to get file contents: {resp.text}")
            return None

    def create_pull_request(self, owner=None, repo=None, head_branch="feature", base_branch="main",
                            title="New PR", body=""):
        if not owner:
            owner = self.default_owner
        if not repo:
            repo = self.default_repo

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        payload = {"title": title, "body": body, "head": head_branch, "base": base_branch}
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code in [200, 201]:
            return resp.json().get("html_url")
        else:
            logger.error(f"Failed to create PR: {resp.text}")
            return None
