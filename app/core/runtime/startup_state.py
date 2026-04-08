from __future__ import annotations

import logging
from typing import Any

from app.core.runtime.startup_checks import run_startup_checks

LOGGER = logging.getLogger("project_approval.startup")


def refresh_startup_checks(app_instance: Any, *, rules_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = run_startup_checks(rules_bundle=rules_bundle)
    app_instance.state.startup_checks = payload
    for item in payload["checks"]:
        log_fn = LOGGER.info if item["status"] == "ok" else LOGGER.warning
        log_fn("startup-check %s [%s] %s", item["name"], item["status"], item["message"])
    return payload
