import os
import django
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jenkins.settings")
django.setup()

import requests
import logging
from django.utils import timezone
import dramatiq
from .models import BuildRecord
from .storage import append_to_log, save_meta
from builds.broker import broker

JENKINS_URL = "http://localhost:8080"
JENKINS_USER = "admin"
JENKINS_TOKEN = "11675a28f9e88da72c7844548ac4aa14f0"

# Setup logger
logger = logging.getLogger("jenkins_worker")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

def http_post(url, data=None, retries=3, timeout=10):
    for attempt in range(retries):
        try:
            r = requests.post(url, data=data, auth=(JENKINS_USER, JENKINS_TOKEN),
                              timeout=timeout, verify=False)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            logger.warning(f"POST {url} attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"POST {url} attempt {attempt+1}/{retries} failed (unexpected exception): {e}")
            time.sleep(1)
    return None

def http_get(url, params=None, timeout=10, skip_warning=False):
    try:
        r = requests.get(url, params=params, auth=(JENKINS_USER, JENKINS_TOKEN),
                         timeout=timeout, verify=False)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        if not skip_warning:
            logger.warning(f"GET {url} failed: {e}")
        return None
    except Exception as e:
        logger.error(f"GET {url} failed (unexpected exception): {e}")
        return None

@dramatiq.actor
def start_and_poll_build(build_id):
    """Start Jenkins build and poll until completion (basic)."""
    build_record = None
    try:
        build_record = BuildRecord.objects.get(id=build_id)
        job_name = build_record.job_name
        logger.info(f"Starting build for job={job_name}")

        # Trigger build
        trigger_url = f"{JENKINS_URL}/job/{job_name}/build?delay=0sec"
        r = http_post(trigger_url)
        if not r:
            build_record.status = "FAILED"
            build_record.save()
            return
        
        # Wait for build number
        build_number = None
        for _ in range(10):
            api_url = f"{JENKINS_URL}/job/{job_name}/api/json"
            r = http_get(api_url)
            if r:
                info = r.json()
                if info.get("builds"):
                    build_number = info["builds"][0]["number"]
                    break
            time.sleep(2)

        if not build_number:
            logger.error("Build number not found")
            build_record.status = "FAILED"
            build_record.save()
            return
        
        build_record.build_number = build_number
        build_record.status = "RUNNING"
        build_record.start_time = timezone.now()
        build_record.save()
        logger.info(f"Build started with build_number={build_number}")

        # Progressive logs and build status loop
        log_offset = 0
        poll_interval_logs = 2
        poll_interval_status = 15
        last_status_check = time.time()
        while True:
            build_record.refresh_from_db()

            # Fetch progressive logs
            log_api = f"{JENKINS_URL}/job/{job_name}/{build_number}/logText/progressiveText"
            r_log = http_get(log_api, params={"start": log_offset}, timeout=10, skip_warning=True)
            more_data = False
            if r_log:
                if r_log.text:
                    append_to_log(job_name, build_number, r_log.text)
                    log_offset = int(r_log.headers.get("X-Text-Size", log_offset + len(r_log.text)))
                    # logger.info(f"✅ Progressive log fetch SUCCESS for {job_name} #{build_number}, offset={log_offset}")
                    pass
                else:
                    # logger.info(f"ℹ️ No new logs yet for {job_name} #{build_number}, offset={log_offset}")
                    pass
                more_data = r_log.headers.get("X-More-Data", "false").lower() == "true"
            # else:
            #     logger.warning(f"⏱️ Progressive log fetch TIMEOUT for {job_name} #{build_number} at offset {log_offset}")
            #     more_data = True

            # Fetch build status only every poll_interval_status
            building = True
            result = None
            if time.time() - last_status_check >= poll_interval_status:
                build_api = f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json"
                r_status = http_get(build_api, timeout=5, skip_warning=True)
                last_status_check = time.time()
                if r_status:
                    info = r_status.json()
                    building = info.get("building", True)
                    result = info.get("result")
                    # logger.info(f"📊 Build status check SUCCESS for {job_name} #{build_number}: building={building}, result={result}")
                    pass
                else:
                    # logger.warning(f"⏱️ Build status check TIMEOUT for {job_name} #{build_number}")
                    pass
            
            # Exit condition: finished and no more logs
            if not building and not more_data:
                build_record.status = result or "UNKNOWN"
                build_record.end_time = timezone.now()
                build_record.save()
                logger.info(f"Build finished with result={build_record.status}")
                break

            time.sleep(poll_interval_logs)

        logger.info(f"✅ Log collection complete for {job_name} #{build_number}")
        save_meta(job_name, build_number, {
            "status": build_record.status,
            "start_time": str(build_record.start_time),
            "end_time": str(build_record.end_time),
        })
        logger.info(f"📦 Meta saved and all tasks completed for {job_name} #{build_number}")

    except Exception as e:
        logger.exception(f"Error in start_and_poll_build: {e}")
        if build_record:
            build_record.status = "FAILED"
            build_record.save()
    finally:
        return

@dramatiq.actor
def stop_build(build_id):
    """Stop Jenkins build."""
    try:
        build_record = BuildRecord.objects.get(id=build_id)
        if not build_record.build_number:
            logger.warning(f"No build_number for {build_id}")
            return

        job_name = build_record.job_name
        build_number = build_record.build_number
        stop_url = f"{JENKINS_URL}/job/{job_name}/{build_number}/stop"

        logger.info(f"Requesting stop for Jenkins build: {job_name} #{build_number}")

        # Call Jenkins stop API
        r = http_post(stop_url)
        if r:
            build_record.status = "STOPPED"
            build_record.end_time = timezone.now()
            build_record.save()
            logger.info(f"Build stopped successfully on Jenkins: {job_name} #{build_number}")
        else:
            logger.error(f"Failed to stop build on Jenkins: {job_name} #{build_number}")

    except Exception as e:
        logger.exception(f"Error stopping build: {e}")
    finally:
        return
