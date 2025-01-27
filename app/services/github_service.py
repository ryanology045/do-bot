# services/github_service.py
"""
Service for interacting with GitHub APIs.
Includes functions for rollback and self-upgrade operations using GitHub tags.
"""

import os
import re
import requests
import logging
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a console handler with a higher log level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create a formatter and set it for the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add the handler to the logger if it doesn't already have handlers
if not logger.hasHandlers():
    logger.addHandler(console_handler)

def create_upgrade_branch() -> str:
    """
    Creates a new upgrade branch in GitHub based on the latest main branch.
    
    Returns:
        str: The name of the created branch.
    
    Raises:
        Exception: If the branch creation fails.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/git/refs"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Fetch the latest commit SHA from main branch
    try:
        main_ref_url = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/git/ref/heads/main"
        response = requests.get(main_ref_url, headers=headers)
        response.raise_for_status()
        main_commit_sha = response.json()['object']['sha']
        logger.info(f"Latest commit SHA on main: {main_commit_sha}")
    except Exception as e:
        logger.error(f"Failed to fetch latest commit SHA from main branch: {e}")
        raise
    
    # Define the new branch name
    import datetime
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch_name = f"self-upgrade-{timestamp}"
    
    # Create the new branch
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": main_commit_sha
    }
    
    try:
        response = requests.post(GITHUB_API_URL, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Created new branch '{branch_name}'.")
        return branch_name
    except Exception as e:
        logger.error(f"Failed to create new branch '{branch_name}': {e}")
        raise

def commit_file_to_branch(branch_name: str, file_path: str, content: str, commit_message: str):
    """
    Commits a file to the specified branch in GitHub.
    
    Args:
        branch_name (str): The GitHub branch name.
        file_path (str): The path of the file to commit (e.g., "plugins/new_feature.py").
        content (str): The content to write to the file.
        commit_message (str): The commit message.
    
    Raises:
        Exception: If the commit fails.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/contents/{file_path}"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get the SHA of the file if it exists (to update)
    try:
        response = requests.get(GITHUB_API_URL, headers=headers, params={"ref": branch_name})
        if response.status_code == 200:
            file_sha = response.json()['sha']
            logger.info(f"File '{file_path}' exists in branch '{branch_name}' with SHA {file_sha}.")
        elif response.status_code == 404:
            file_sha = None
            logger.info(f"File '{file_path}' does not exist in branch '{branch_name}'. It will be created.")
        else:
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch file '{file_path}' from branch '{branch_name}': {e}")
        raise
    
    # Prepare the commit data
    import base64
    encoded_content = base64.b64encode(content.encode()).decode()
    
    data = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch_name
    }
    if file_sha:
        data["sha"] = file_sha
    
    # Commit the file
    try:
        response = requests.put(GITHUB_API_URL, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Committed file '{file_path}' to branch '{branch_name}'.")
    except Exception as e:
        logger.error(f"Failed to commit file '{file_path}' to branch '{branch_name}': {e}")
        raise

def merge_upgrade_branch(branch_name: str):
    """
    Merges the specified upgrade branch into the main branch.
    
    Args:
        branch_name (str): The GitHub branch name to merge.
    
    Raises:
        Exception: If the merge fails.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/merges"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "base": "main",
        "head": branch_name,
        "commit_message": f"Merging upgrade branch '{branch_name}' into main"
    }
    
    try:
        response = requests.post(GITHUB_API_URL, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Successfully merged branch '{branch_name}' into main.")
    except Exception as e:
        logger.error(f"Failed to merge branch '{branch_name}' into main: {e}")
        raise

def delete_upgrade_branch(branch_name: str):
    """
    Deletes the specified upgrade branch in GitHub.
    
    Args:
        branch_name (str): The GitHub branch name to delete.
    
    Raises:
        Exception: If the deletion fails.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/git/refs/heads/{branch_name}"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.delete(GITHUB_API_URL, headers=headers)
        if response.status_code in [204, 404]:
            logger.info(f"Deleted branch '{branch_name}' from GitHub.")
        else:
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to delete branch '{branch_name}' from GitHub: {e}")
        raise

def get_last_deployment_tag() -> str:
    """
    Retrieves the last deployment tag from GitHub.
    
    Returns:
        str: The last deployment tag.
    
    Raises:
        Exception: If unable to fetch tags or no tags are found.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/tags"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(GITHUB_API_URL, headers=headers)
        response.raise_for_status()
        tags = response.json()
        if not tags:
            raise Exception("No tags found in the repository.")
        last_tag = tags[0]['name']  # Assuming the first tag is the latest
        logger.info(f"Last deployment tag retrieved: '{last_tag}'.")
        return last_tag
    except Exception as e:
        logger.error(f"Failed to retrieve last deployment tag: {e}")
        raise
