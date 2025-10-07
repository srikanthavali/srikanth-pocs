from django.http import JsonResponse
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
        return JsonResponse({"error": "Missing parameters"}, status=400)

    try:
        start_int = int(start)
    except ValueError:
        return JsonResponse({"error": "Invalid start value"}, status=400)

    url = f"{jenkins_url}/job/{job_name}/{build_number}/logText/progressiveText?start={start_int}"

    try:
        r = requests.get(url, auth=HTTPBasicAuth(username, api_token), timeout=10)
        r.raise_for_status()

        logs = r.text
        more_data = r.headers.get("x-more-data", "false") == "true"
        next_start = int(r.headers.get("x-text-size", start_int))

        return JsonResponse({
            "logs": logs,
            "more_data": more_data,
            "next_start": next_start
        })
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)
