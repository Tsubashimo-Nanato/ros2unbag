from __future__ import annotations

from dataclasses import dataclass, field

from .models import TopicInfo


@dataclass(slots=True)
class TopicTreeNode:
    name: str
    path: str
    children: dict[str, "TopicTreeNode"] = field(default_factory=dict)
    topic: TopicInfo | None = None

    @property
    def topic_count(self) -> int:
        count = 1 if self.topic is not None else 0
        return count + sum(child.topic_count for child in self.children.values())


def split_topic_name(topic_name: str) -> list[str]:
    return [part for part in topic_name.strip().split("/") if part]


def topic_leaf_name(topic_name: str) -> str:
    parts = split_topic_name(topic_name)
    return parts[-1] if parts else "/"


def topic_parent_path(topic_name: str) -> str:
    parts = split_topic_name(topic_name)
    if len(parts) <= 1:
        return "/"
    return "/" + "/".join(parts[:-1])


def build_topic_tree(topics: list[TopicInfo]) -> TopicTreeNode:
    root = TopicTreeNode(name="/", path="/")
    for topic in sorted(topics, key=lambda item: item.name):
        node = root
        parts = split_topic_name(topic.name)
        for index, part in enumerate(parts):
            path = "/" + "/".join(parts[: index + 1])
            node = node.children.setdefault(part, TopicTreeNode(name=part, path=path))
        node.topic = topic
    return root


def format_topic_brief(topic: TopicInfo) -> str:
    duration = "" if topic.duration_sec is None else f", duration={topic.duration_sec:.3f}s"
    return (
        f"type={topic.msgtype}, count={topic.message_count}, "
        f"category={topic.category}{duration}"
    )


def format_topic_compact(topic: TopicInfo) -> str:
    return f"{topic.category}, {topic.message_count} msgs"
