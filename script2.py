import subprocess
import os
import json
import time

GITHUB_USERNAME = "user"
REPO_NAME = "REPO"
GITHUB_TOKEN = "Token" 


def get_open_pull_requests():
    """Fetches open PRs from the GitHub repository"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/pulls?state=open"
    cmd = [
        "curl",
        "-L",  # Follow redirects
        "-H", f"Authorization: Bearer {GITHUB_TOKEN}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)  # Parse JSON from the output string
        except json.JSONDecodeError:
            print("Failed to parse the JSON response")
            return []
    else:
        print("Failed to fetch pull requests")
        return []


def get_pull_request_commits(pr_number):
    """Fetches the commits for a given PR"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/pulls/{pr_number}/commits"
    cmd = [
        "curl",
        "-L",  # Follow redirects
        "-H", f"Authorization: Bearer {GITHUB_TOKEN}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)  # List of commits
        except json.JSONDecodeError:
            print(f"Failed to parse commits for PR #{pr_number}")
            return []
    else:
        print(f"Failed to fetch commits for PR #{pr_number}")
        return []


def set_commit_status(commit_sha, state, description):
    """Set the build status on a commit using GitHub Status API"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/statuses/{commit_sha}"
    status_payload = {
        "state": state,  # "pending", "success", "failure"
        "description": description,
        "context": "ci/build",  # You can change this to your build system context
        "target_url": "http://your-build-system-url.com"  # URL to the build result
    }
    cmd = [
        "curl",
        "-L",  # Follow redirects
        "-X", "POST",  # POST request to set status
        "-H", f"Authorization: Bearer {GITHUB_TOKEN}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        "-d", json.dumps(status_payload),  # Payload to send in the request
        url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"Successfully set status: {state} for commit {commit_sha}")
    else:
        print(f"Failed to set status for commit {commit_sha}")


def build_code():
    """Simulate a build process (placeholder for actual build logic)"""
    print("No reviews found. Triggering a build for the PR...")


def check_pr_review_status_and_build():
    """Check PR status, track CL, and trigger build if necessary"""
    pull_requests = get_open_pull_requests()

    if not pull_requests:
        print("No open pull requests found.")
        return

    for pr in pull_requests:
        pr_number = pr['number']
        pr_title = pr['title']
        print(f"Checking review status for PR: #{pr_number} - {pr_title}")
        
        # Get the most recent commit SHA for the PR
        commits = get_pull_request_commits(pr_number)
        if not commits:
            print(f"No commits found for PR #{pr_number}.")
            continue
        
        # Get the SHA of the latest commit
        latest_commit_sha = commits[-1]['sha']
        
        # Check if build has been triggered for this commit
        # Retrieve the status of the latest commit
        status_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/commits/{latest_commit_sha}/status"
        cmd = [
            "curl",
            "-L",  # Follow redirects
            "-H", f"Authorization: Bearer {GITHUB_TOKEN}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28",
            status_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            status_data = json.loads(result.stdout)
            state = status_data.get("state", "")
            
            # If the commit is not yet built, trigger the build
            if state != "success" and state != "pending":
                print(f"Triggering build for PR #{pr_number} (New commit detected)...")
                build_code()  # Trigger build
                set_commit_status(latest_commit_sha, "pending", "Build in progress")
            else:
                print(f"Build already triggered or in progress for PR #{pr_number}. Skipping build.")
        else:
            print(f"Failed to retrieve commit status for PR #{pr_number}.")

def main():
    """Main function to execute the process"""
    check_pr_review_status_and_build()


if __name__ == "__main__":
    main()
