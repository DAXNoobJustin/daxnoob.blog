"""
Monitoring and incident utilities for HelixData.

Provides a configurable incident hook used by the data-quality framework to
raise an alert when a check fails.
"""

import requests

from helixutils._debug import get_logger

from ._var import global_variable

logger = get_logger(__name__)


def create_incident(
    title: str, description: str, severity: int, fields: str, owning_team: str = "HelixData/Operations"
) -> str | None:
    """
    Create an automated incident via a configurable webhook.

    Posts the incident to the webhook URL configured in the ``global`` variable
    library (``incident_webhook_url``). Point it at whatever incident or alerting
    system you use -- a ticketing API, PagerDuty, a Teams Incoming Webhook, etc.

    Args:
        title: Incident title
        description: Incident description
        severity: Incident severity level
        fields: Incident field/symptom
        owning_team: Team that owns the incident

    Returns:
        Incident ID if the webhook returns one, otherwise None (and in non-prod).

    """
    if global_variable.environment != "prod":
        return "Automated incidents not enabled in lower environment"

    webhook_url = global_variable.incident_webhook_url
    if not webhook_url:
        logger.warning("incident_webhook_url is not configured; skipping incident creation")
        return None

    try:
        payload = {
            "title": title,
            "description": description,
            "symptom": fields,
            "severity": severity,
            "owningTeam": owning_team,
        }
        response = requests.post(webhook_url, json=payload)

        if response.status_code == 200:
            logger.info("Incident created")
            return (response.json().get("incidentId") or "").strip() or None
        logger.error(f"Incident webhook failed with status code: {response.status_code}")
        logger.error(response.text)
        return None

    except Exception as e:
        logger.error(f"Failed to create incident: {e!s}")
        return None
