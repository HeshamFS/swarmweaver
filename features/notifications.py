"""
Notification & Webhook System
===============================

Sends notifications to configured channels when key events occur:
- Browser push notifications (via frontend WebSocket)
- Slack webhooks
- Discord webhooks
- Generic HTTP webhooks

Configuration persists per-project in notification_config.json.
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class NotificationConfig:
    """Configuration for notification channels."""
    enabled: bool = True
    webhook_url: str = ""           # Generic webhook
    slack_webhook: str = ""         # Slack incoming webhook URL
    discord_webhook: str = ""       # Discord webhook URL
    notify_on: list[str] = field(default_factory=lambda: [
        "task_completed",
        "all_tasks_done",
        "error",
        "agent_stuck",
    ])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationConfig":
        return cls(
            enabled=data.get("enabled", True),
            webhook_url=data.get("webhook_url", ""),
            slack_webhook=data.get("slack_webhook", ""),
            discord_webhook=data.get("discord_webhook", ""),
            notify_on=data.get("notify_on", [
                "task_completed", "all_tasks_done", "error", "agent_stuck",
            ]),
        )


class NotificationManager:
    """
    Manages notification dispatch to configured channels.

    Loads/saves config per-project. Sends to Slack, Discord,
    and generic webhooks.
    """

    CONFIG_FILE = "notification_config.json"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config = NotificationConfig()
        self.load_config()

    @property
    def config_path(self) -> Path:
        return self.project_dir / self.CONFIG_FILE

    def load_config(self) -> NotificationConfig:
        """Load notification config from disk."""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.config = NotificationConfig.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass
        return self.config

    def save_config(self, config: Optional[NotificationConfig] = None) -> None:
        """Save notification config to disk."""
        if config:
            self.config = config
        self.config_path.write_text(
            json.dumps(self.config.to_dict(), indent=2),
            encoding="utf-8",
        )

    def should_notify(self, event_type: str) -> bool:
        """Check if notifications are enabled for this event type."""
        return self.config.enabled and event_type in self.config.notify_on

    def notify(self, event_type: str, title: str, body: str) -> list[dict]:
        """
        Send notification to all configured channels.

        Returns a list of results with channel name and success status.
        """
        if not self.should_notify(event_type):
            return []

        results = []

        if self.config.slack_webhook:
            results.append(self._send_slack(title, body))

        if self.config.discord_webhook:
            results.append(self._send_discord(title, body))

        if self.config.webhook_url:
            results.append(self._send_generic(event_type, title, body))

        return results

    def _send_slack(self, title: str, body: str) -> dict:
        """Send notification to Slack."""
        payload = json.dumps({
            "text": f"*{title}*\n{body}",
        }).encode("utf-8")

        return self._post(
            self.config.slack_webhook,
            payload,
            "slack",
            content_type="application/json",
        )

    def _send_discord(self, title: str, body: str) -> dict:
        """Send notification to Discord."""
        payload = json.dumps({
            "content": f"**{title}**\n{body}",
        }).encode("utf-8")

        return self._post(
            self.config.discord_webhook,
            payload,
            "discord",
            content_type="application/json",
        )

    def _send_generic(self, event_type: str, title: str, body: str) -> dict:
        """Send notification to generic webhook."""
        payload = json.dumps({
            "event": event_type,
            "title": title,
            "body": body,
            "source": "swarmweaver",
        }).encode("utf-8")

        return self._post(
            self.config.webhook_url,
            payload,
            "webhook",
            content_type="application/json",
        )

    def _post(
        self,
        url: str,
        payload: bytes,
        channel: str,
        content_type: str = "application/json",
    ) -> dict:
        """POST payload to URL. Returns result dict."""
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": content_type},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {
                    "channel": channel,
                    "success": True,
                    "status": resp.status,
                }
        except urllib.error.URLError as e:
            return {
                "channel": channel,
                "success": False,
                "error": str(e)[:200],
            }
        except Exception as e:
            return {
                "channel": channel,
                "success": False,
                "error": str(e)[:200],
            }

    def test_notification(self) -> list[dict]:
        """Send a test notification to all configured channels."""
        return self.notify(
            "test",
            "SwarmWeaver Test Notification",
            "If you see this, notifications are working correctly!",
        )
