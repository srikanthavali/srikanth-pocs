import os
import django
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jenkins.settings")
django.setup()

import requests
from django.utils import timezone
from .models import BuildRecord
from .storage import append_to_log, save_meta
from builds.broker import broker
import dramatiq
import logging

# Setup logger
logger = logging.getLogger("jenkins_worker")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

JENKINS_USER = "admin"
JENKINS_TOKEN = "11675a28f9e88da72c7844548ac4aa14f0"
JENKINS_URL = "http://localhost:8080"

@dramatiq.actor
def stop_build(build_id):
    """Stop a running Jenkins build."""
    try:
        build_record = BuildRecord.objects.get(id=build_id)
        if not build_record.build_number:
            logger.warning(f"Build {build_id} has no build_number, cannot stop.")
            return

        job_name = build_record.job_name
        build_number = build_record.build_number
        stop_url = f"{JENKINS_URL}/job/{job_name}/{build_number}/stop"

        logger.info(f"Sending stop command to Jenkins for {job_name} #{build_number}")
        r = requests.post(stop_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=20, verify=False)

        if r.status_code in [200, 201]:
            logger.info(f"Jenkins accepted stop for {job_name} #{build_number}")
            build_record.status = 'STOPPED'
            build_record.end_time = timezone.now()
            build_record.save()
        else:
            logger.error(f"Failed to stop Jenkins build: status={r.status_code}, body={r.text}")

    except Exception as e:
        logger.exception(f"Error while stopping build_id={build_id}: {e}")

@dramatiq.actor
def start_and_poll_build(build_id):
    """Poll Jenkins build logs and update BuildRecord"""
    logger.info(f"Task started for BuildRecord id={build_id}")
    build_record = None

    try:
        try:
            build_record = BuildRecord.objects.get(id=build_id)
            logger.info(f"Fetched BuildRecord: {build_record}")
        except BuildRecord.DoesNotExist:
            logger.error(f"BuildRecord {build_id} does not exist. Exiting task.")
            return

        job_name = build_record.job_name
        logger.info(f"Job name: {job_name}")

        # Trigger build if needed
        if not build_record.build_number:
            trigger_url = f"{JENKINS_URL}/job/{job_name}/build?delay=0sec"
            logger.info(f"Triggering Jenkins build at: {trigger_url}")

            try:
                r = requests.post(trigger_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=15, verify=False)
                if r.status_code not in [200, 201]:
                    logger.error(f"Failed to trigger build, status_code={r.status_code}")
                    build_record.status = 'FAILED'
                    build_record.save()
                    return
                logger.info("Build triggered successfully")
            except Exception as e:
                logger.exception(f"Exception while triggering Jenkins build: {e}")
                build_record.status = 'FAILED'
                build_record.save()
                return

            # Poll queue for build number
            queue_url = r.headers.get('Location')
            if not queue_url:
                logger.error("No Location header returned from Jenkins, cannot fetch queue info")
                build_record.status = 'FAILED'
                build_record.save()
                return

            queue_api = queue_url + "api/json"
            build_number = None
            waited = 0
            max_wait = 30
            while build_number is None and waited < max_wait:
                try:
                    q = requests.get(queue_api, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10, verify=False).json()
                    executable = q.get('executable')
                    if executable and executable.get('number'):
                        build_number = executable['number']
                        build_record.build_number = build_number
                        build_record.status = 'RUNNING'
                        build_record.start_time = timezone.now()
                        build_record.save()
                        logger.info(f"Build started with build_number={build_number}")
                        break
                except Exception as e:
                    logger.exception(f"Error while polling queue: {e}")
                time.sleep(2)
                waited += 2

            if build_number is None:
                logger.error("Build number not obtained after waiting, marking FAILED")
                build_record.status = 'FAILED'
                build_record.save()
                return
        else:
            build_number = build_record.build_number
            build_record.status = 'RUNNING'
            build_record.start_time = build_record.start_time or timezone.now()
            build_record.save()
            logger.info(f"Build already triggered, continuing with build_number={build_number}")

        # Poll progressive logs
        poll_interval = 2
        db_refresh_interval = 5
        stable_timeout = 15
        log_offset = 0
        finished = False
        no_log_since = None
        last_db_check = 0
        poll_count = 0
        logger.info(f"Start polling logs for build_number={build_number}")

        while not finished:
            poll_count += 1
            log_api = f"{JENKINS_URL}/job/{job_name}/{build_number}/logText/progressiveText"

            try:
                # ---- Throttled DB refresh ----
                if time.time() - last_db_check > db_refresh_interval:
                    build_record.refresh_from_db()
                    last_db_check = time.time()

                if build_record.status == "STOPPED":
                    logger.info(f"Build #{build_number} marked STOPPED — sending stop and draining logs.")
                    stop_url = f"{JENKINS_URL}/job/{job_name}/{build_number}/stop"
                    try:
                        requests.post(stop_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=20, verify=False)
                        logger.info(f"Stop command sent to Jenkins for build #{build_number}")
                    except Exception as e:
                        logger.warning(f"Failed to stop Jenkins build: {e}")

                    # Poll progressive logs until Jenkins confirms build stopped
                    while True:
                        r = requests.get(log_api, params={"start": log_offset}, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=30, verify=False)
                        text_chunk = r.text or ""
                        if text_chunk:
                            append_to_log(job_name, build_number, text_chunk)
                            log_offset = int(r.headers.get("X-Text-Size", log_offset + len(text_chunk)))

                        # Check if Jenkins build finished
                        info = requests.get(f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json",
                                            auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10, verify=False).json()
                        if not info.get("building", True):
                            logger.info(f"Jenkins build #{build_number} fully stopped.")
                            break
                        time.sleep(2)
                    
                    # Fetch final build result to reflect ABORTED/FAILURE if any
                    try:
                        info = requests.get(f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json",
                                            auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10, verify=False).json()
                        build_record.status = info.get("result") or "STOPPED"
                    except Exception:
                        build_record.status = "STOPPED"
                    build_record.end_time = timezone.now()
                    build_record.save()
                    finished = True
                    continue

                # ---- Fetch progressive logs ----
                r = requests.get(
                    log_api,
                    params={"start": log_offset},
                    auth=(JENKINS_USER, JENKINS_TOKEN),
                    timeout=30,
                    verify=False,
                )
                r.raise_for_status()
                text_chunk = r.text or ""
                append_to_log(job_name, build_number, text_chunk)
                
                prev_offset = log_offset
                log_offset = int(r.headers.get("X-Text-Size", log_offset + len(text_chunk)))

                # ---- Small periodic info log ----
                if poll_count % 10 == 0:
                    logger.info(f"Polling #{poll_count}: offset={log_offset}, job={job_name}")

                # ---- Detect end conditions ----
                if r.headers.get("X-More-Data") == "true":
                    no_log_since = None
                    time.sleep(poll_interval)
                    continue
                
                if r.headers.get("X-More-Data") == "false" or "X-More-Data" not in r.headers:
                    build_info_api = f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json"
                    info = requests.get(build_info_api, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10, verify=False).json()

                    if info.get("building") is False:
                        finished = True
                        logger.info(f"Build logs completed for #{build_number}")
                    else:
                        # build still running but Jenkins hasn't updated logs yet
                        time.sleep(poll_interval)
                    continue

                # ---- Stable timeout detection ----
                if prev_offset == log_offset:
                    if no_log_since is None:
                        no_log_since = time.time()
                    elif time.time() - no_log_since > stable_timeout:
                        logger.warning(f"No new logs for {stable_timeout}s — assuming done.")
                        finished = True
                else:
                    no_log_since = None
                
                time.sleep(poll_interval)

            except Exception as e:
                logger.exception(f"Error while polling logs: {e}")
                time.sleep(poll_interval)

        # Fetch final result
        build_info_api = f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json"
        try:
            info = requests.get(build_info_api, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10, verify=False).json()
            result = info.get('result')
            build_record.status = result if result else 'FAILED'
            build_record.end_time = timezone.now()
            build_record.save()
            logger.info(f"Build finished with status={build_record.status}")
        except Exception as e:
            logger.exception(f"Error fetching final build info: {e}")
            build_record.status = 'FAILED'
            build_record.end_time = timezone.now()
            build_record.save()

        # Save meta.json
        try:
            save_meta(job_name, build_number, {
                "status": build_record.status,
                "start_time": str(build_record.start_time),
                "end_time": str(build_record.end_time),
            })
            logger.info(f"Meta saved for build_number={build_number}")
        except Exception as e:
            logger.exception(f"Error saving meta.json: {e}")

    except Exception as e:
      logger.exception(f"Unhandled exception in worker for build_id={build_id}: {e}")
      if build_record:
          build_record.status = 'FAILED'
          build_record.save()
