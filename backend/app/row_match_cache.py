from dataclasses import dataclass, field


def pair_key(
    source_database: str,
    source_table: str,
    source_schema: str | None,
    target_database: str,
    target_table: str,
    target_schema: str | None,
) -> str:
    return "|".join(
        [
            source_database or "",
            source_schema or "",
            source_table or "",
            target_database or "",
            target_schema or "",
            target_table or "",
        ]
    )


@dataclass
class RowMatchCache:
    pair_key: str
    source_to_target: dict[int, int] = field(default_factory=dict)
    target_to_source: dict[int, int] = field(default_factory=dict)
    source_total: int = 0
    target_total: int = 0
    # When set, unmatched/totals are scoped to these absolute row indices (filtered compare).
    source_universe: list[int] | None = None
    target_universe: list[int] | None = None
    _unmatched_source: list[int] | None = None
    _unmatched_target: list[int] | None = None

    @property
    def matched(self) -> int:
        return len(self.source_to_target)

    def invalidate_unmatched(self) -> None:
        self._unmatched_source = None
        self._unmatched_target = None

    def unmatched(self, side: str) -> list[int]:
        if side == "source":
            if self._unmatched_source is None:
                matched = self.source_to_target
                universe = self.source_universe
                if universe is None:
                    self._unmatched_source = [i for i in range(self.source_total) if i not in matched]
                else:
                    self._unmatched_source = [i for i in universe if i not in matched]
            return self._unmatched_source
        if self._unmatched_target is None:
            matched = self.target_to_source
            universe = self.target_universe
            if universe is None:
                self._unmatched_target = [i for i in range(self.target_total) if i not in matched]
            else:
                self._unmatched_target = [i for i in universe if i not in matched]
        return self._unmatched_target

    def link(self, source: int, target: int) -> None:
        old_target = self.source_to_target.pop(source, None)
        if old_target is not None:
            self.target_to_source.pop(old_target, None)
        old_source = self.target_to_source.pop(target, None)
        if old_source is not None:
            self.source_to_target.pop(old_source, None)
        self.source_to_target[source] = target
        self.target_to_source[target] = source
        self.invalidate_unmatched()

    def unlink(self, source: int | None = None, target: int | None = None) -> None:
        if source is not None:
            old_target = self.source_to_target.pop(source, None)
            if old_target is not None:
                self.target_to_source.pop(old_target, None)
        if target is not None:
            old_source = self.target_to_source.pop(target, None)
            if old_source is not None:
                self.source_to_target.pop(old_source, None)
        self.invalidate_unmatched()

    def overlay(self, source_indices: list[int], target_indices: list[int]) -> dict:
        source_set = set(source_indices)
        target_set = set(target_indices)
        mappings = []
        mapped_source = []
        mapped_target = []
        pairs = []
        seen_pairs: set[tuple[int, int]] = set()

        for source_index in source_indices:
            target_index = self.source_to_target.get(source_index)
            if target_index is None:
                continue
            mapped_source.append(source_index)
            pair = (source_index, target_index)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                pairs.append({"source": source_index, "target": target_index})
            if target_index in target_set:
                mappings.append(
                    {
                        "source": f"row-{source_index}",
                        "target": f"row-{target_index}",
                    }
                )

        for target_index in target_indices:
            source_index = self.target_to_source.get(target_index)
            if source_index is None:
                continue
            mapped_target.append(target_index)
            pair = (source_index, target_index)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                pairs.append({"source": source_index, "target": target_index})
            if source_index in source_set and target_index in target_set:
                # already added in mappings when walking sources; avoid duplicates
                continue

        return {
            "has_match": True,
            "matched": self.matched,
            "mappings": mappings,
            "mapped_source": mapped_source,
            "mapped_target": mapped_target,
            "pairs": pairs,
        }


_CACHE: dict[int, RowMatchCache] = {}


def put(task_id: int, cache: RowMatchCache) -> None:
    _CACHE[int(task_id)] = cache


def get(task_id: int, expected_pair: str | None = None) -> RowMatchCache | None:
    cache = _CACHE.get(int(task_id))
    if not cache:
        return None
    if expected_pair and cache.pair_key != expected_pair:
        return None
    return cache


def clear(task_id: int) -> None:
    _CACHE.pop(int(task_id), None)
