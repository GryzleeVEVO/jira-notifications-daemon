# A polling notifications daemon for JIRA

## Overview

This program polls the JIRA API for new and updated tickets as defined by a JQL query. This implementation does not use WebHooks: although it may be less efficient, no admin access is required, only an API key.

## Requirements

This project requires Python 3.13 or higher. Lower versions of Python or its dependencies may work, but it's not tested.

This project uses `uv` for dependency management. This is not strictly necessary, otherwise install the following dependencies:

- [`jira`](https://github.com/pycontribs/jira)
- [`desktop-notifier`](https://github.com/samschott/desktop-notifier)

Note this has only been tested on Linux.

## Quickstart

```sh
git clone https://github.com/GryzleeVEVO/jira-notifications-daemon
uv sync
uv run --env-file .env jira-notifd.py
```

## Configuration

Use the `.env.example` file in order to properly configure the daemon.
