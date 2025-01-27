# services/github_service.py
"""
Service for interacting with GitHub APIs.
Includes functions for rollback operations using GitHub tags.
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

def rollback_to_tag(tag: str):
    """
    Performs a rollback to the specified GitHub tag.
    This function updates the ECS service to use the Docker image associated with the tag.

    Args:
        tag (str): The GitHub tag to rollback to.

    Raises:
        Exception: If the rollback process fails.
    """
    GITHUB_API_URL = f"https://api.github.com/repos/{os.environ.get('GITHUB_OWNER')}/{os.environ.get('GITHUB_REPO')}/releases/tags/{tag}"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.")
        raise Exception("GITHUB_TOKEN is not set.")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Fetch the release information
    response = requests.get(GITHUB_API_URL, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch release for tag '{tag}': {response.status_code} {response.text}")
        raise Exception(f"Failed to fetch release for tag '{tag}'.")

    release_data = response.json()
    if not release_data:
        logger.error(f"No release data found for tag '{tag}'.")
        raise Exception(f"No release data found for tag '{tag}'.")

    # Extract Docker image URI from release notes
    image_uri = extract_image_uri(release_data.get("body", ""))
    if not image_uri:
        logger.error("Docker image URI not found in release notes.")
        raise Exception("Docker image URI not found in release notes.")

    # Update ECS service with the new image URI
    try:
        update_ecs_service(image_uri)
        logger.info(f"Successfully rolled back to tag '{tag}' with image '{image_uri}'.")
    except Exception as e:
        logger.error(f"Failed to rollback to tag '{tag}': {e}")
        raise

def extract_image_uri(release_body: str) -> str:
    """
    Extracts the Docker image URI from the release body.

    Args:
        release_body (str): The body content of the GitHub release.

    Returns:
        str: The Docker image URI if found, else an empty string.
    """
    match = re.search(r"Image URI:\s*(\S+)", release_body)
    if match:
        return match.group(1)
    return ""

def update_ecs_service(image_uri: str):
    """
    Updates the ECS service to use the specified Docker image URI.

    Args:
        image_uri (str): The Docker image URI to deploy.

    Raises:
        Exception: If the ECS service update fails.
    """
    import boto3

    ECS_CLUSTER = os.environ.get("ECS_CLUSTER")
    ECS_SERVICE = os.environ.get("ECS_SERVICE")
    TASK_DEFINITION = os.environ.get("ECS_TASK_DEFINITION")

    if not ECS_CLUSTER or not ECS_SERVICE or not TASK_DEFINITION:
        logger.error("ECS_CLUSTER, ECS_SERVICE, and ECS_TASK_DEFINITION must be set as environment variables.")
        raise Exception("Missing ECS deployment environment variables.")

    ecs_client = boto3.client('ecs', region_name=os.environ.get("AWS_DEFAULT_REGION"))

    try:
        # Describe the current task definition
        response = ecs_client.describe_task_definition(taskDefinition=TASK_DEFINITION)
        task_def = response['taskDefinition']

        # Update the image in the container definitions
        updated_container_definitions = []
        for container in task_def['containerDefinitions']:
            if container['name'] == 'do-bot':  # Replace with your container name
                container['image'] = image_uri
                logger.info(f"Updated container '{container['name']}' image to '{image_uri}'.")
            updated_container_definitions.append(container)

        # Register the new task definition
        new_task_def = ecs_client.register_task_definition(
            family=task_def['family'],
            taskRoleArn=task_def['taskRoleArn'],
            executionRoleArn=task_def['executionRoleArn'],
            networkMode=task_def['networkMode'],
            containerDefinitions=updated_container_definitions,
            requiresCompatibilities=task_def['requiresCompatibilities'],
            cpu=task_def['cpu'],
            memory=task_def['memory']
        )

        # Update the ECS service to use the new task definition
        ecs_client.update_service(
            cluster=ECS_CLUSTER,
            service=ECS_SERVICE,
            taskDefinition=new_task_def['taskDefinition']['taskDefinitionArn'],
            forceNewDeployment=True
        )

        logger.info(f"ECS service '{ECS_SERVICE}' updated to use image '{image_uri}'.")
    except Exception as e:
        logger.error(f"Failed to update ECS service: {e}")
        raise
