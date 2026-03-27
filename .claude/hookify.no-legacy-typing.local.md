---
name: no-legacy-typing
enabled: true
event: file
pattern: (Optional\[|List\[|Dict\[|Tuple\[|Union\[)
action: warn
---

**Use Python 3.10+ type syntax.**

- `X | None` not `Optional[X]`
- `list[X]` not `List[X]`
- `dict[K, V]` not `Dict[K, V]`
- `tuple[X, ...]` not `Tuple[X, ...]`
- `X | Y` not `Union[X, Y]`
