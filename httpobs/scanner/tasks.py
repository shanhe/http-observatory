from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded
from os import environ

from httpobs.database import insert_test_result, update_scan_state
from httpobs.scanner import celeryconfig, STATE_ABORTED, STATE_FAILED, STATE_STARTED
from httpobs.scanner.retriever import retrieve_all

import sys

import httpobs.scanner.analyzer


# Create the scanner task queue
scanner = Celery()
scanner.config_from_object(celeryconfig)


@scanner.task()
def scan(hostname: str, site_id: int, scan_id: int):
    try:
        # Once celery kicks off the task, let's update the scan state from PENDING to STARTED
        update_scan_state(scan_id, STATE_STARTED)

        # Attempt to retrieve all the resources
        reqs = retrieve_all(hostname)

        # If we can't connect at all, let's abort the test
        if reqs['responses']['auto'] is None:
            update_scan_state(scan_id, STATE_FAILED, error='site down')

            return

        # Execute each test, replacing the underscores in the function name with dashes in the test name
        for test in httpobs.scanner.analyzer.tests:
            # TODO: Get overridden expectations
            insert_test_result(site_id, scan_id, test.__name__.replace('_', '-'), test(reqs))

    # catch the celery timeout, which will almost certainly occur in retrieve_all()
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        update_scan_state(scan_id, STATE_ABORTED, error='site unresponsive')
    except:
        # TODO: have more specific error messages
        e = sys.exc_info()[1]  # get the error message

        # Print the exception to stdout if we're in dev
        if 'HTTPOBS_DEV' in environ:
            import traceback
            print('Error detected in: ' + hostname)
            traceback.print_exc()

        # If we are unsuccessful, close out the scan in the database
        update_scan_state(scan_id, STATE_FAILED, error=repr(e))
