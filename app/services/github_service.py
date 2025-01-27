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
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/git/refs"
    GITHUB_TOKEN = os.environ.get("GH_TOKEN")
    
    if not GH_TOKEN:
        logger.error("GH_TOKEN is not set.")
        raise Exception("GH_TOKEN is not set.")
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Fetch the latest commit SHA from main branch
    try:
        main_ref_url = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/git/ref/heads/main"
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
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/contents/{file_path}"
    GITHUB_TOKEN = os.environ.get("GH_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GH_TOKEN is not set.")
        raise Exception("GH_TOKEN is not set.")
    
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
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/merges"
    GITHUB_TOKEN = os.environ.get("GH_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GH_TOKEN is not set.")
        raise Exception("GH_TOKEN is not set.")
    
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
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/git/refs/heads/{branch_name}"
    GITHUB_TOKEN = os.environ.get("GH_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GH_TOKEN is not set.")
        raise Exception("GH_TOKEN is not set.")
    
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
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GH_OWNER')}/{os.environ.get('GH_REPO')}/tags"
    GITHUB_TOKEN = os.environ.get("GH_TOKEN")
    
    if not GITHUB_TOKEN:
        logger.error("GH_TOKEN is not set.")
        raise Exception("GH_TOKEN is not set.")
    
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

def rollback_to_tag(tag: str):
    """
    Performs a rollback to the specified GitHub tag (e.g., 'production-deployment-20250127-0000').

    1) Fetch release data for `tag` from GitHub.
    2) Extract the Docker image URI from the release body (assuming 'Image URI: <image>'.
    3) Update the ECS task definition to use that image, forcing a new deployment.

    Args:
        tag (str): The tag identifying the deployment version to roll back to.

    Raises:
        Exception: If the rollback process fails or the tag doesn't exist.
    """
    logger.info(f"Attempting to roll back to tag '{tag}'...")

    # 1) Fetch release info from GitHub
    github_token = os.environ.get("GH_TOKEN")
    github_owner = os.environ.get("GH_OWNER")  # e.g. "YourName"
    github_repo  = os.environ.get("GH_REPO")   # e.g. "YourRepo"

    if not all([github_token, github_owner, github_repo]):
        msg = "GH_TOKEN, GH_OWNER, or GH_REPO not set in env."
        logger.error(msg)
        raise Exception(msg)

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    releases_url = f"https://api.github.com/repos/{github_owner}/{github_repo}/releases/tags/{tag}"
    logger.info(f"Fetching release info from {releases_url}")
    resp = requests.get(releases_url, headers=headers)
    if resp.status_code != 200:
        msg = f"Failed to fetch release for tag '{tag}': {resp.status_code} {resp.text}"
        logger.error(msg)
        raise Exception(msg)

    release_data = resp.json()
    # 2) Extract Docker image URI from release body
    image_uri = _extract_image_uri_from_release(release_data.get("body", ""), tag)
    logger.info(f"Found image URI for rollback: {image_uri}")

    # 3) Update ECS to use that image
    _update_ecs_service(image_uri)
    logger.info(f"Rollback to tag '{tag}' completed successfully using image '{image_uri}'.")

def _extract_image_uri_from_release(body: str, tag: str) -> str:
    """
    Extract the Docker image URI from the release body, assuming it has a line like 'Image URI: <image>'.
    """
    # Example line: "Image URI: 123456789012.dkr.ecr.us-east-1.amazonaws.com/your-app:someTag"
    logger.info(f"Extracting image URI from release body for tag {tag}.")
    pattern = r"Image URI:\s*(\S+)"
    match = re.search(pattern, body)
    if not match:
        msg = f"No 'Image URI:' line found in release body for tag '{tag}'."
        logger.error(msg)
        raise Exception(msg)
    return match.group(1)

def _update_ecs_service(image_uri: str):
    """
    Updates an ECS service to use the specified Docker image URI.
    - Expects AWS creds + ECS info in environment:
      ECS_CLUSTER, ECS_SERVICE, ECS_TASK_DEFINITION, AWS_DEFAULT_REGION, etc.
    """
    ecs_cluster = os.environ.get("ECS_CLUSTER")        # e.g. "my-ecs-cluster"
    ecs_service = os.environ.get("ECS_SERVICE")        # e.g. "my-ecs-service"
    ecs_taskdef = os.environ.get("ECS_TASK_DEFINITION")# e.g. "my-ecs-task-def-family"
    region      = os.environ.get("AWS_DEFAULT_REGION","us-east-2")

    if not all([ecs_cluster, ecs_service, ecs_taskdef]):
        msg = "ECS_CLUSTER, ECS_SERVICE, or ECS_TASK_DEFINITION not set in env. Cannot update ECS."
        logger.error(msg)
        raise Exception(msg)

    ecs_client = boto3.client("ecs", region_name=region)

    # 1) Describe the current task definition
    logger.info(f"Describing current task definition: {ecs_taskdef}")
    resp = ecs_client.describe_task_definition(taskDefinition=ecs_taskdef)
    if "taskDefinition" not in resp:
        raise Exception(f"Task definition '{ecs_taskdef}' not found or invalid response.")

    task_def = resp["taskDefinition"]
    container_defs = task_def["containerDefinitions"]

    # 2) Update the container image
    #    - If your container is named 'do-bot', update that container
    container_name = "do-bot"  # Adjust to your container name
    updated = False
    for cdef in container_defs:
        if cdef["name"] == container_name:
            logger.info(f"Updating container '{container_name}' image to '{image_uri}'")
            cdef["image"] = image_uri
            updated = True
            break

    if not updated:
        raise Exception(f"No container named '{container_name}' found in task definition.")

    # 3) Register a new task definition revision with the updated container
    new_task_def = ecs_client.register_task_definition(
        family=task_def["family"],
        taskRoleArn=task_def["taskRoleArn"],
        executionRoleArn=task_def["executionRoleArn"],
        networkMode=task_def["networkMode"],
        containerDefinitions=container_defs,
        requiresCompatibilities=task_def["requiresCompatibilities"],
        cpu=task_def["cpu"],
        memory=task_def["memory"]
    )

    new_td_arn = new_task_def["taskDefinition"]["taskDefinitionArn"]
    logger.info(f"Registered new task definition revision: {new_td_arn}")

    # 4) Update the ECS service to use that new revision
    logger.info(f"Updating service '{ecs_service}' in cluster '{ecs_cluster}' to use task def {new_td_arn}")
    ecs_client.update_service(
        cluster=ecs_cluster,
        service=ecs_service,
        taskDefinition=new_td_arn,
        forceNewDeployment=True
    )
    logger.info(f"ECS service '{ecs_service}' updated to new task definition. Rollback triggered.")
