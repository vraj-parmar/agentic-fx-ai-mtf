# File: clear_pushgateway.py
# (Place this in the root of your project or a utils/ directory)

import requests
import logging
import re
from collections import defaultdict

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
PUSHGATEWAY_URL = 'http://localhost:9091'  # Ensure this matches your port-forward


def attempt_admin_wipe(pushgateway_address):
    """
    Attempts to wipe all metrics using the Pushgateway admin API.
    This requires Pushgateway v1.4.0+ and the admin API to be enabled.
    """
    wipe_url = f"{pushgateway_address}/api/v1/admin/wipe"
    logging.info(f"Attempting to wipe all metrics via admin API: PUT {wipe_url}")
    try:
        response = requests.put(wipe_url, timeout=10)
        if response.status_code == 200:
            logging.info("Successfully wiped all metrics from Pushgateway via admin API.")
            return True
        elif response.status_code == 404:
            logging.warning(
                "Admin wipe API endpoint not found. Pushgateway might be an older version or admin API not enabled.")
            return False
        elif response.status_code == 405:  # Method Not Allowed
            logging.warning(
                f"Admin wipe API returned Method Not Allowed. Ensure --web.enable-admin-api is set for Pushgateway if using this method. Status: {response.status_code}")
            return False
        else:
            logging.error(f"Admin wipe failed. Status: {response.status_code}, Response: {response.text}")
            return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Could not connect to Pushgateway at {pushgateway_address} for admin wipe. Error: {e}")
        return False
    except requests.exceptions.Timeout:
        logging.error("Request to Pushgateway timed out during admin wipe attempt.")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during admin wipe: {e}")
        return False


def discover_and_delete_groups(pushgateway_address):
    """
    Fetches all metrics, discovers job/instance groups, and deletes them.
    This is a fallback if admin wipe is not available.
    """
    metrics_url = f"{pushgateway_address}/metrics"
    logging.info(f"Attempting to discover and delete groups by fetching {metrics_url}")
    try:
        response = requests.get(metrics_url, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch metrics from {metrics_url}. Error: {e}")
        return

    metrics_text = response.text
    # Regex to find job and instance labels. Adjust if other grouping labels are used.
    # Example: metric_name{job="myjob",instance="myinstance",other="val"} 123
    # This regex captures job and instance specifically.
    # For more general grouping keys, parsing becomes more complex.
    # The key 'instance' is common for grouping_key={'instance': '...'}

    # Stores job -> set of instances
    job_instances = defaultdict(set)
    all_jobs = set()

    # A more robust way to parse Prometheus exposition format is needed for arbitrary labels.
    # For now, let's focus on 'job' and 'instance' which are common.
    # This regex is a simplification. A proper parser would be better for complex label sets.
    # Example line: some_metric{label1="val1",job="j1",instance="i1"} 1
    # We need to extract the full label set that forms the group.
    # The Pushgateway API for deletion is /metrics/job/<job_name>[/label_name/<label_value>...]

    # Let's find all unique job/instance pairs
    # Regex to find 'job="<job_name>"' and 'instance="<instance_name>"'
    # This is a common pattern from prometheus_client's grouping_key={'instance': ...}
    # pattern = re.compile(r'.*\{.*job="([^"]+)".*instance="([^"]+)".*}.*') # Original simpler pattern

    # More general pattern to extract all labels within the curly braces
    metric_line_pattern = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{(.*?)\})?\s+.*$")
    label_pattern = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"')

    groups_to_delete = set()  # Store tuples of (job_name, frozenset_of_grouping_labels_dict_items)

    for line in metrics_text.splitlines():
        if line.startswith('#') or not line.strip():
            continue

        match = metric_line_pattern.match(line)
        if match:
            labels_str = match.group(1)
            if labels_str:
                current_labels = dict(label_pattern.findall(labels_str))
                job_name = current_labels.pop('job', None)
                # The 'instance' label is often the primary grouping key beyond 'job'
                # For simplicity, we'll focus on job/instance deletion path.
                # A truly generic solution would need to handle arbitrary grouping keys.
                instance_name = current_labels.get('instance', None)

                if job_name:
                    all_jobs.add(job_name)
                    if instance_name:
                        # This is the most common grouping from prometheus_client
                        job_instances[job_name].add(instance_name)

    deleted_something = False
    # Delete specific job/instance groups
    for job_name, instances in job_instances.items():
        for instance_name in instances:
            delete_url = f"{pushgateway_address}/metrics/job/{job_name}/instance/{instance_name}"
            logging.info(f"Deleting group: DELETE {delete_url}")
            try:
                del_response = requests.delete(delete_url, timeout=10)
                if del_response.status_code == 202:
                    logging.info(f"Successfully deleted group job='{job_name}', instance='{instance_name}'.")
                    deleted_something = True
                elif del_response.status_code == 404:
                    logging.info(f"Group job='{job_name}', instance='{instance_name}' not found (already deleted).")
                else:
                    logging.error(
                        f"Failed to delete group job='{job_name}', instance='{instance_name}'. Status: {del_response.status_code}")
            except Exception as e:
                logging.error(f"Error deleting group job='{job_name}', instance='{instance_name}': {e}")

    # As a broader cleanup, delete any remaining metrics by job (catches metrics without instance or other specific grouping)
    for job_name in all_jobs:
        # Check if we already tried to delete all instances for this job.
        # If job_instances[job_name] was empty, this job might have metrics without an instance.
        if not job_instances.get(job_name):  # Only delete whole job if no instances were found/deleted for it
            delete_url = f"{pushgateway_address}/metrics/job/{job_name}"
            logging.info(f"Attempting to delete all metrics for job (broader cleanup): DELETE {delete_url}")
            try:
                del_response = requests.delete(delete_url, timeout=10)
                if del_response.status_code == 202:
                    logging.info(f"Successfully deleted all metrics for job '{job_name}'.")
                    deleted_something = True
                elif del_response.status_code == 404:
                    logging.info(f"Job '{job_name}' not found for broader cleanup (already deleted or no metrics).")
                else:
                    logging.error(
                        f"Failed to delete job '{job_name}' during broader cleanup. Status: {del_response.status_code}")
            except Exception as e:
                logging.error(f"Error deleting job '{job_name}' during broader cleanup: {e}")

    if not deleted_something and not job_instances and not all_jobs:
        logging.info("No metrics or groups found on Pushgateway to delete.")


if __name__ == '__main__':
    logging.info("--- Starting Pushgateway Cleanup ---")
    # Make sure your Pushgateway is running and port-forwarded to localhost:9091
    # e.g., kubectl port-forward <your-pushgateway-pod-name> 9091:9091

    admin_wipe_successful = attempt_admin_wipe(PUSHGATEWAY_URL)

    if not admin_wipe_successful:
        logging.info("Admin wipe not successful or not available. Falling back to discovering and deleting groups.")
        discover_and_delete_groups(PUSHGATEWAY_URL)

    logging.info("--- Pushgateway Cleanup Finished ---")