from django.http import HttpResponse
import json
import requests
from requests.auth import HTTPBasicAuth

def jenkins_proxy(request):
    jenkins_url = request.GET.get("jenkinsUrl")
    job_name = request.GET.get("jobName")
    build_number = request.GET.get("buildNumber")
    start = request.GET.get("start", "0")
    username = request.GET.get("username")
    api_token = request.GET.get("apiToken")

    if not all([jenkins_url, job_name, build_number, username, api_token]):
        return HttpResponse("Missing parameters", status=400, content_type="text/plain")

    try:
        start_int = int(start)
    except ValueError:
        return HttpResponse("Invalid start value", status=400, content_type="text/plain")

    url = f"{jenkins_url}/job/{job_name}/{build_number}/logText/progressiveText?start={start_int}"

    try:
        r = requests.get(url, auth=HTTPBasicAuth(username, api_token), timeout=10)
        r.raise_for_status()

        logs = r.text
        more_data = r.headers.get("x-more-data", "false") == "true"
        next_start = int(r.headers.get("x-text-size", start_int))

        # Create metadata JSON
        metadata = json.dumps({
            "more_data": more_data,
            "next_start": next_start
        })

        # Use a clear delimiter to separate logs and metadata
        delimiter = "\n__JENKINS_METADATA__\n"
        return HttpResponse(logs + delimiter + metadata, content_type="text/plain")

    except requests.RequestException as e:
        return HttpResponse(f"Error: {str(e)}", status=500, content_type="text/plain")