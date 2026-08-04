import re
from datetime import datetime

from app.core.models import TriageResult
from app.reports.models import DuplicateCluster

_PREFIX_RE = re.compile(r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "it",
        "not",
        "be",
        "as",
        "was",
        "that",
        "this",
        "are",
        "were",
        "been",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "when",
        "if",
        "then",
        "than",
        "so",
        "no",
        "all",
        "any",
        "each",
        "feat",
        "fix",
        "bug",
        "add",
        "update",
        "issue",
        "error",
        "support",
        "new",
        "old",
        "use",
        "using",
        "set",
        "get",
    }
)

_WINDOW_DAYS = 7
_MIN_SHARED_TOKENS = 1


def _extract_prefix(title: str) -> str | None:
    m = _PREFIX_RE.match(title)
    return m.group(1) if m else None


def _tokenize(title: str) -> set[str]:
    clean = _PREFIX_RE.sub("", title)
    tokens = re.findall(r"[a-zA-Z]{3,}", clean.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def _within_window(a: TriageResult, b: TriageResult) -> bool:
    try:
        ta = datetime.fromisoformat(a.assessed_at)
        tb = datetime.fromisoformat(b.assessed_at)
        return abs((ta - tb).total_seconds()) <= _WINDOW_DAYS * 86400
    except (ValueError, TypeError):
        return False


class DuplicateDetector:
    def detect(self, results: list[TriageResult]) -> list[DuplicateCluster]:
        groups: dict[str, list[TriageResult]] = {}
        for r in results:
            prefix = _extract_prefix(r.issue_title)
            key = prefix if prefix else "__no_prefix__"
            groups.setdefault(key, []).append(r)

        clusters = []
        for area, group in groups.items():
            if len(group) < 2:
                continue

            token_sets = [(r, _tokenize(r.issue_title)) for r in group]

            adj: dict[int, set[int]] = {i: set() for i in range(len(group))}
            shared_tokens_map: dict[tuple[int, int], set[str]] = {}

            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if not _within_window(group[i], group[j]):
                        continue
                    shared = token_sets[i][1] & token_sets[j][1]
                    if len(shared) >= _MIN_SHARED_TOKENS:
                        adj[i].add(j)
                        adj[j].add(i)
                        shared_tokens_map[(i, j)] = shared

            visited = set()
            for start in range(len(group)):
                if start in visited or not adj[start]:
                    continue
                component = set()
                stack = [start]
                while stack:
                    node = stack.pop()
                    if node in component:
                        continue
                    component.add(node)
                    stack.extend(adj[node] - component)
                visited |= component

                all_shared = set()
                for i in component:
                    for j in component:
                        if i < j and (i, j) in shared_tokens_map:
                            all_shared |= shared_tokens_map[(i, j)]

                cluster_area = area if area != "__no_prefix__" else "no-prefix"
                clusters.append(
                    DuplicateCluster(
                        area=cluster_area,
                        issues=[group[i] for i in sorted(component)],
                        similarity_reason=f"shared: {', '.join(sorted(all_shared))}",
                    )
                )

        return clusters
