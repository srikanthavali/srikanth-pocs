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
from .storage import append_to_log, save_meta, read_meta
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

def get_running_build_number(job_name):
    running_build_number = None

    # 1️⃣ Check the latest build only
    r_job = http_get(f"{JENKINS_URL}/job/{job_name}/api/json?tree=lastBuild[number,building]")
    if r_job:
        last_build = r_job.json().get("lastBuild")
        if last_build and last_build.get("building"):
            return last_build["number"]

    # 2️⃣ Also check the queue to see if a build is waiting
    r_queue = http_get(f"{JENKINS_URL}/queue/api/json?tree=items[task[name],id]")
    if r_queue:
        for item in r_queue.json().get("items", []):
            if item.get("task", {}).get("name") == job_name:
                # Jenkins queue item id can be used if you want
                return f"queued-{item['id']}"

    return running_build_number

@dramatiq.actor(time_limit=24*60*60*1000)
def start_and_poll_build(build_id):
    """Start Jenkins build and poll until completion (basic)."""
    build_record = None
    log_offset = 0
    try:
        build_record = BuildRecord.objects.get(id=build_id)
        job_name = build_record.job_name
        logger.info(f"Preparing build for job={job_name}")

        # --- 1️⃣ Check for already running build ---
        running_build_number = get_running_build_number(job_name)

        if running_build_number:
            logger.info(f"Build already running: {job_name} #{running_build_number}, attaching logs")
            build_record.build_number = running_build_number
            build_record.status = "RUNNING"
            build_record.start_time = build_record.start_time or timezone.now()
            build_record.save()

            # Load last log_offset from meta
            meta = read_meta(job_name, running_build_number) or {}
            log_offset = meta.get("last_log_offset", 0)

            # assign build_number for later usage
            build_number = running_build_number
        else:
            logger.info(f"Starting build for job={job_name}")
            # --- 2️⃣ Trigger new build as usual ---
            trigger_url = f"{JENKINS_URL}/job/{job_name}/build?delay=0sec"
            r = http_post(trigger_url)
            if not r:
                build_record.status = "FAILED"
                build_record.save()
                return

            # Wait for build number
            build_number = None
            for _ in range(10):
                r_info = http_get(f"{JENKINS_URL}/job/{job_name}/api/json")
                if r_info:
                    info = r_info.json()
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
            log_offset = 0
            logger.info(f"Build started with build_number={build_number}")

        # Progressive logs and build status loop
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

                    # Save intermediate log_offset for resumability
                    save_meta(job_name, build_record.build_number, {
                        "status": build_record.status,
                        "start_time": str(build_record.start_time),
                        "last_log_offset": log_offset,
                    })
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
                else:
                    # logger.warning(f"⏱️ Build status check TIMEOUT for {job_name} #{build_number}")
                    pass
            
            if not building:
                stable_offset = False
                while not stable_offset:
                    r_log = http_get(log_api, params={"start": log_offset}, timeout=10, skip_warning=True)
                    if r_log:
                        text = r_log.text or ""
                        append_to_log(job_name, build_record.build_number, text)
                        new_offset = int(r_log.headers.get("X-Text-Size", log_offset + len(text)))
                        save_meta(job_name, build_record.build_number, {
                            "status": build_record.status,
                            "start_time": str(build_record.start_time),
                            "last_log_offset": new_offset,
                        })

                        if new_offset == log_offset and r_log.headers.get("X-More-Data", "false").lower() == "false":
                            stable_offset = True  # no new logs, safe to exit
                        log_offset = new_offset
                    else:
                        time.sleep(1)

                    time.sleep(1)              

                # Mark build as finished
                build_record.status = result or "UNKNOWN"
                build_record.end_time = timezone.now()
                build_record.save()
                logger.info(f"Build finished with result={build_record.status}")
                break

            time.sleep(poll_interval_logs)

        save_meta(job_name, build_record.build_number, {
            "status": build_record.status,
            "start_time": str(build_record.start_time),
            "end_time": str(build_record.end_time),
            "last_log_offset": log_offset,
        })
        logger.info(f"✅ Log collection complete and meta saved for {job_name} #{build_record.build_number}")

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
