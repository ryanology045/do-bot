# services/github_service.py
"""
Service for interacting with GitHub to commit, tag, merge, or rollback changes.
All GitHub credentials come from environment variables or GitHub Actions secrets.
"""

import os
from github import Github
import datetime

# In your GitHub repository, you might have:
# GITHUB_TOKEN is from GitHub Secrets (set in GitHub Actions or ECS env)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", None)
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "owner/my_slackbot_project")

def get_github_repo():
    if not GITHUB_TOKEN:
        raise ValueError("No GITHUB_TOKEN set. Cannot interact with GitHub.")
    g = Github(GITHUB_TOKEN)
    return g.get_repo(GITHUB_REPO_NAME)

def create_upgrade_branch(branch_prefix="upgrade-"):
    """
    Create a new Git branch from 'main' (or 'master') for the upgrade.
    """
    repo = get_github_repo()
    main_ref = repo.get_git_ref("heads/main")
    new_branch_name = branch_prefix + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    repo.create_git_ref(ref="refs/heads/" + new_branch_name, sha=main_ref.object.sha)
    return new_branch_name

def commit_file_to_branch(branch_name, file_path, new_content, commit_message="Upgrade commit"):
    """
    Commit a file to a branch in GitHub.
    """
    repo = get_github_repo()
    # Try to get the file if it exists
    try:
        contents = repo.get_contents(file_path, ref=branch_name)
        repo.update_file(contents.path, commit_message, new_content, contents.sha, branch=branch_name)
    except:
        # File doesn't exist, create it
        repo.create_file(file_path, commit_message, new_content, branch=branch_name)

def merge_branch(branch_name, base_branch="main"):
    """
    Merge the branch into main.
    """
    repo = get_github_repo()
    repo.merge(base_branch, branch_name, f"Merging {branch_name} into {base_branch}")

def merge_upgrade_branch(branch_name):
    merge_branch(branch_name, "main")

def rollback_to_tag(tag):
    """
    Sample rollback method: create a new branch from the specified tag, then merge to main, or reset main to that tag.
    For demonstration, we do a simple reset by creating a ref from the tag to main. 
    In real usage, you'd ensure safe forced push or protected branch rules are considered.
    """
    repo = get_github_repo()
    # 1. find the tag
    tag_ref = None
    try:
        tag_ref = repo.get_git_ref(f"tags/{tag}")
    except:
        raise ValueError(f"Tag {tag} not found in repository.")
    
    # 2. get main ref
    main_ref = repo.get_git_ref("heads/main")
    
    # 3. update main ref to point to the tag's commit (force=True might be needed)
    main_ref.edit(tag_ref.object.sha, force=True)
    
    # (re)deploy on ECS if your pipeline triggers on main updates
    return
