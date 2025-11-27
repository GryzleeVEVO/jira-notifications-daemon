import asyncio
import os
import random
import webbrowser
import logging
from desktop_notifier import DesktopNotifier
from jira import JIRA, Issue

JIRA_BASE_URL = os.getenv(
    "JIRA_BASE_URL", ""
)
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JQL_QUERY = os.getenv("JQL_QUERY", "")

# Controls how often a new notification is popped from the queue
NOTIFICATION_RATE_MIN = 2
NOTIFICATION_RATE_MAX = 2

# How often the JIRA API is polled for new updates
POLLING_RATE = 10

logger = logging.getLogger(__name__)


async def notify_loop(notifier: DesktopNotifier, queue: asyncio.Queue[Issue]):
    """
    Loop that awaits new notifications in a queue and displays them.
    """
    while True:
        issue = await queue.get()

        logging.info("Retrieved issue %s from queue", issue)

        _ = await notifier.send(
            title=issue.key,
            message=issue.fields.summary,
            on_clicked=lambda: webbrowser.open(
                f"{JIRA_BASE_URL}/browse/{issue.key}")
        )

        # Add a random timeout to debounce notifications
        await asyncio.sleep(random.randint(NOTIFICATION_RATE_MIN, NOTIFICATION_RATE_MAX))


async def jira_loop(jira: JIRA, queue: asyncio.Queue[Issue]):
    """
    Loop that fetches periodically new issues and sends notification requests
    if needed
    """
    issues_seen: dict[str, str] = {}
    first_iter = True

    while True:
        try:
            issues = jira.search_issues(JQL_QUERY, maxResults=10)

            for issue in issues:
                logger.debug("Found issue %s", issue.key)
                if issue.key not in issues_seen or issue.fields.updated != issues_seen[issue.key]:
                    issues_seen[issue.key] = issue.fields.updated

                    if not first_iter:
                        logger.info("Sending issue %s to queue", issue.key)
                        await queue.put(issue)
        except Exception as e:
            logger.error(e)
        finally:
            first_iter = False
            await asyncio.sleep(POLLING_RATE)


async def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s[%(process)d]: %(funcName)s: %(message)s"
    )

    if not len(JIRA_BASE_URL) > 0:
        logging.critical("No base URL defined")
        exit(1)

    if not len(JIRA_API_TOKEN) > 0:
        logging.critical("No API token defined")
        exit(1)

    if not len(JIRA_EMAIL) > 0:
        logging.critical("No email defined")
        exit(1)

    if not len(JQL_QUERY) > 0:
        logging.critical("No JQL query defined")
        exit(1)

    notifier = DesktopNotifier()
    jira = JIRA(
        server=JIRA_BASE_URL,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN),
    )
    queue: asyncio.Queue[Issue] = asyncio.Queue()

    tasks = [
        asyncio.create_task(notify_loop(notifier, queue)),
        asyncio.create_task(jira_loop(jira, queue))
    ]

    try:
        _ = await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        for task in tasks:
            _ = task.cancel()
        _ = await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting")
