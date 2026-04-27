import asyncio
import logging
import webbrowser
import os
from configparser import ConfigParser
from pathlib import Path

from desktop_notifier import DesktopNotifier, Icon
from jira import JIRA, Issue

# Config
config_path = os.path.join(
    os.environ.get("XDG_CONFIG_HOME")
    or os.path.join(os.environ.get("HOME", ""), ".config"),
    "jira-notifications",
    "config.ini"
) if (os.environ.get("XDG_CONFIG_HOME") or os.environ.get("HOME")) \
  else "./config.ini"

config = ConfigParser()
_ = config.read("config.ini")

LOGGING_LEVEL = logging.getLevelNamesMapping(
)[config.get('App', 'LoggingLevel', fallback="DEBUG")]
JIRA_URL = config.get('Jira', 'BaseUrl')
JIRA_USERNAME = config.get('Jira', 'Username')
JIRA_API_TOKEN = config.get('Jira', 'Token')
JIRA_QUERY = config.get('Jira', 'Query')
JIRA_POLLING_RATE = config.getint('Jira', 'PollingRate', fallback=10)
NOTIFICATIONS_RATE = config.getint('Notifications', 'Rate', fallback=2)
NOTIFICATIONS_ICON_PATH = config.get(
    'Notifications', 'IconPath', fallback=None)

assert len(JIRA_URL) >= 0, "JIRA URL not defined"
assert len(JIRA_USERNAME) >= 0, "JIRA username not defined"
assert len(JIRA_API_TOKEN) >= 0, "No JIRA API token provided"
assert len(JIRA_QUERY) >= 0, "Query not defined"

# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s %(name)s[%(process)d]: %(funcName)s: %(message)s"
)

# Notifier
notifier = DesktopNotifier()

# JIRA
jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USERNAME, JIRA_API_TOKEN),)
queue: asyncio.Queue[Issue] = asyncio.Queue()


async def notify_loop(notifier: DesktopNotifier, queue: asyncio.Queue[Issue]):
    """
    Loop that awaits new notifications in a queue and displays them.
    """
    icon = Icon(Path(NOTIFICATIONS_ICON_PATH)) if NOTIFICATIONS_ICON_PATH else None

    while True:
        issue = await queue.get()

        logger.info("Retrieved issue %s from queue", issue)

        _ = await notifier.send(
            title=issue.key,
            message=issue.fields.summary,
            on_clicked=lambda: webbrowser.open(
                f"{JIRA_URL}/browse/{issue.key}"),
            icon=icon
        )

        # Add a random timeout to debounce notifications
        await asyncio.sleep(NOTIFICATIONS_RATE)


async def jira_loop(jira: JIRA, queue: asyncio.Queue[Issue]):
    """
    Loop that fetches periodically new issues and sends notification requests
    if needed
    """
    issues_seen: dict[str, str] = {}
    first_iter = True

    while True:
        try:
            issues = jira.search_issues(JIRA_QUERY, maxResults=10)
            logger.debug("Found issues: %s", [issue.key for issue in issues])

            for issue in issues:
                if issue.key not in issues_seen or issue.fields.updated != issues_seen[issue.key]:
                    issues_seen[issue.key] = issue.fields.updated

                    if not first_iter:
                        logger.info("Sending issue %s to queue", issue.key)
                        await queue.put(issue)
        except Exception as e:
            logger.error(e)
        finally:
            first_iter = False
            await asyncio.sleep(JIRA_POLLING_RATE)


async def main():
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
