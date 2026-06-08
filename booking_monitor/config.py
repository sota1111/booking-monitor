import json
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Conditions:
    adults: int = 2
    children_under_3: int = 0
    days_of_week: List[str] = field(default_factory=list)
    time: str = ""


@dataclass
class Target:
    name: str
    url: str
    interval_seconds: int
    available_keywords: List[str]
    unavailable_keywords: List[str]
    notify: bool
    site_type: str = "generic"
    conditions: Optional[Conditions] = None


@dataclass
class Notification:
    type: str
    webhook_url_env: str = ""


@dataclass
class Config:
    targets: List[Target]
    notification: Notification


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    targets = []
    for t in data.get("targets", []):
        conditions_data = t.get("conditions")
        conditions = None
        if conditions_data:
            conditions = Conditions(
                adults=conditions_data.get("adults", 2),
                children_under_3=conditions_data.get("children_under_3", 0),
                days_of_week=conditions_data.get("days_of_week", []),
                time=conditions_data.get("time", ""),
            )
        targets.append(
            Target(
                name=t["name"],
                url=t["url"],
                interval_seconds=t.get("interval_seconds", 300),
                available_keywords=t.get("available_keywords", []),
                unavailable_keywords=t.get("unavailable_keywords", []),
                notify=t.get("notify", True),
                site_type=t.get("site_type", "generic"),
                conditions=conditions,
            )
        )

    notif_data = data.get("notification", {})
    notification = Notification(
        type=notif_data.get("type", "discord"),
        webhook_url_env=notif_data.get("webhook_url_env", "DISCORD_WEBHOOK_URL"),
    )

    if not targets:
        raise ValueError("No targets defined in config")

    return Config(targets=targets, notification=notification)
