import asyncio
import logging
import os
import webbrowser
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from desktop_notifier import DesktopNotifier, Icon
from jira import JIRA, Issue

logger = logging.getLogger(__name__)


@dataclass
class Config:
    log_level: int
    jira_url: str
    jira_username: str
    jira_api_token: str
    jira_query: str
    polling_rate: int
    notifications_rate: int
    icon_path: Path | None


def load_config() -> Config:
    def resolve_path() -> Path:
        resolved = Path(
            os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ) / "jira-notifications" / "config.ini"
        return resolved if resolved.exists() else Path("config.ini")

    def required(section: str, key: str) -> str:
        value = parser.get(section, key, fallback="").strip()

        if not value:
            raise SystemExit(f"Missing required value: [{section}] {key}")

        return value

    parser = ConfigParser()
    path = resolve_path()

    if not parser.read(path):
        raise SystemExit(f"Config file not found: {path}")

    icon = parser.get("Notifications", "IconPath", fallback=None)

    return Config(
        log_level=logging.getLevelNamesMapping()[parser.get(
            "App", "LoggingLevel", fallback="INFO")],
        jira_url=required("Jira", "BaseUrl"),
        jira_username=required("Jira", "Username"),
        jira_api_token=required("Jira", "Token"),
        jira_query=required("Jira", "Query"),
        polling_rate=parser.getint("Jira", "PollingRate", fallback=10),
        notifications_rate=parser.getint("Notifications", "Rate", fallback=2),
        icon_path=Path(icon).expanduser().resolve() if icon else None
    )


async def notify_loop(config: Config, notifier: DesktopNotifier, queue: asyncio.Queue[Issue]):
    """
    Loop that awaits new notifications in a queue and displays them.
    """
    icon = Icon(config.icon_path) if config.icon_path else None

    _ = await notifier.send(
        title="JIRA notifications started",
        message="",
        icon=icon
    )

    while True:
        issue = await queue.get()
        logger.info("Retrieved issue %s from queue", issue)

        url = f"{config.jira_url}/browse/{issue.key}"
        _ = await notifier.send(
            title=issue.key,
            message=issue.fields.summary,
            on_clicked=lambda url=url: webbrowser.open(url),
            icon=icon
        )

        await asyncio.sleep(config.notifications_rate)


async def jira_loop(config: Config, jira: JIRA, queue: asyncio.Queue[Issue]):
    """
    Loop that fetches periodically new issues and sends notification requests
    if needed
    """
    issues_seen: dict[str, str] = {}
    first_iter = True

    while True:
        try:
            issues = await asyncio.to_thread(jira.search_issues, config.jira_query, maxResults=10)
            logger.debug("Found issues: %s", [issue.key for issue in issues])

            for issue in issues:
                updated = cast(str, issue.fields.updated)
                if issues_seen.get(issue.key) != updated:
                    issues_seen[issue.key] = updated

                    if not first_iter:
                        logger.info("Sending issue %s to queue", issue.key)
                        await queue.put(issue)
        except Exception:
            logger.exception("Failed to poll Jira")
        finally:
            first_iter = False
            await asyncio.sleep(config.polling_rate)


async def main():
    config = load_config()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(name)s[%(process)d]: %(funcName)s: %(message)s"
    )

    notifier = DesktopNotifier()
    jira = await asyncio.to_thread(JIRA, server=config.jira_url, basic_auth=(config.jira_username, config.jira_api_token))
    queue: asyncio.Queue[Issue] = asyncio.Queue()

    async with asyncio.TaskGroup() as tg:
        _ = tg.create_task(notify_loop(config, notifier, queue))
        _ = tg.create_task(jira_loop(config, jira, queue))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting")
