from __future__ import annotations

from typing import Any
import re

from verifysignal_spec.workspace.models import RefreshImpactResult

from .models import CoverageInventory, CoverageInventoryItem, CandidateValidationUseCase, InventoryPass

VALID_SCOPES = {"all", "changed", "continue"}
SURFACE_PRIORITY = {
    "route": 0,
    "page": 0,
    "flow": 1,
    "form": 1,
    "action": 1,
    "permission": 2,
    "state": 2,
    "integration": 2,
}


def normalize_scope(scope: str | None) -> str:
    value = scope or "all"
    if value in VALID_SCOPES or value.startswith("route:") or value.startswith("area:"):
        return value
    raise ValueError("Scope must be all, changed, continue, route:<path>, or area:<name>.")


def normalize_inventory(data: dict[str, Any] | None, *, scope: str | None = None) -> CoverageInventory:
    payload = dict(data or {})
    normalize_scope(scope)
    payload = _normalize_inventory_payload(payload)
    if "items" not in payload:
        payload["items"] = []
    if "candidateUseCases" not in payload:
        payload["candidateUseCases"] = []
    inventory = CoverageInventory.from_dict(payload)
    inventory.items = sorted(
        inventory.items,
        key=lambda item: (SURFACE_PRIORITY.get(item.surfaceType, 3), _priority_rank(item.priority), item.path, item.id),
    )
    _validate_inventory(inventory)
    inventory.status = _computed_status(inventory)
    return inventory


def _normalize_inventory_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("items") and isinstance(payload.get("coveredAreas"), list):
        items: list[dict[str, Any]] = []
        for area in payload.get("coveredAreas", []):
            if not isinstance(area, dict):
                continue
            area_name = str(area.get("area") or area.get("name") or "area")
            for surface in area.get("surfaces", []):
                if not isinstance(surface, dict):
                    continue
                path = str(surface.get("route") or surface.get("path") or surface.get("container") or surface.get("name") or "")
                if not path:
                    continue
                item_id = surface.get("id") or f"{_slug(area_name)}-{_slug(path)}"
                items.append(
                    {
                        "id": item_id,
                        "surfaceType": surface.get("type") or ("route" if surface.get("route") else "flow"),
                        "path": path,
                        "title": surface.get("title") or surface.get("description") or path,
                        "sourceRefs": surface.get("sourceRefs", []),
                        "userFacing": surface.get("userFacing", True),
                        "inventoryStatus": surface.get("inventoryStatus", "covered"),
                        "exclusionReason": surface.get("exclusionReason"),
                        "candidateUseCaseRefs": surface.get("candidateUseCaseRefs", []),
                        "priority": surface.get("priority", "medium"),
                    }
                )
        payload["items"] = items
    if "uncoveredAreas" not in payload and isinstance(payload.get("uncovered"), list):
        payload["uncoveredAreas"] = payload["uncovered"]
    items = payload.get("items", [])
    item_ids = [str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")]
    normalized_traceability = False
    normalized_candidates: list[dict[str, Any]] = []
    for candidate in payload.get("candidateUseCases", []):
        if not isinstance(candidate, dict):
            continue
        normalized = dict(candidate)
        if not normalized.get("sourceInventoryItems"):
            sources = _candidate_sources(normalized, items, item_ids)
            normalized["sourceInventoryItems"] = sources
            normalized_traceability = bool(sources) or normalized_traceability
        if not normalized.get("rationale"):
            normalized["rationale"] = normalized.get("description") or normalized.get("behavior") or "Candidate inferred from product understanding."
        if not normalized.get("behavior"):
            normalized["behavior"] = normalized.get("description") or normalized.get("title") or normalized.get("alias", "")
        normalized_candidates.append(normalized)
    payload["candidateUseCases"] = normalized_candidates
    if payload.get("candidateUseCases"):
        if all(candidate.get("sourceInventoryItems") for candidate in normalized_candidates):
            payload["sourceTraceabilityStatus"] = "normalized" if normalized_traceability else payload.get("sourceTraceabilityStatus", "complete")
        else:
            payload["sourceTraceabilityStatus"] = "missing"
    else:
        payload.setdefault("sourceTraceabilityStatus", "complete")
    return payload


def merge_inventory(existing: dict[str, Any] | None, incoming: dict[str, Any] | None, *, scope: str | None = None) -> CoverageInventory:
    normalize_scope(scope)
    if not existing:
        return normalize_inventory(incoming, scope=scope)
    current = CoverageInventory.from_dict(existing)
    update = normalize_inventory(incoming, scope=scope)

    items_by_id = {item.id: item for item in current.items}
    for item in update.items:
        items_by_id[item.id] = item

    candidates_by_alias = {candidate.alias: candidate for candidate in current.candidateUseCases}
    for candidate in update.candidateUseCases:
        candidates_by_alias[candidate.alias] = candidate

    passes = [*current.passes, *update.passes]
    uncovered = sorted({*current.uncoveredAreas, *update.uncoveredAreas})
    stale = sorted({*current.staleAreas, *update.staleAreas})

    merged = CoverageInventory(
        status=update.status,
        generatedAt=update.generatedAt or current.generatedAt,
        generatedGitHash=update.generatedGitHash or current.generatedGitHash,
        gitAvailable=update.gitAvailable or current.gitAvailable,
        sourceFilesVisited=update.sourceFilesVisited or current.sourceFilesVisited,
        sourceTraceabilityStatus=update.sourceTraceabilityStatus or current.sourceTraceabilityStatus,
        partialInventoryReasons=sorted({*current.partialInventoryReasons, *update.partialInventoryReasons}),
        passes=passes,
        items=list(items_by_id.values()),
        candidateUseCases=list(candidates_by_alias.values()),
        uncoveredAreas=uncovered,
        staleAreas=stale,
    )
    merged.items = sorted(
        merged.items,
        key=lambda item: (SURFACE_PRIORITY.get(item.surfaceType, 3), _priority_rank(item.priority), item.path, item.id),
    )
    _validate_inventory(merged)
    merged.status = _computed_status(merged)
    return merged


def candidate_dicts(inventory: CoverageInventory) -> list[dict[str, Any]]:
    return [candidate.to_dict() for candidate in inventory.candidateUseCases]


def inventory_needs_more_coverage(inventory_data: dict[str, Any] | None) -> bool:
    if not inventory_data:
        return True
    status = inventory_data.get("status", "partial")
    return status in {"partial", "stale"}


def classify_refresh_impacts(
    existing_inventory_data: dict[str, Any] | None,
    incoming_inventory_data: dict[str, Any] | None,
    records: list[Any],
    *,
    generated_at: str | None = None,
) -> list[RefreshImpactResult]:
    """Conservative per-use-case impact from public inventory paths only.

    This intentionally avoids claiming tested-code precision. When the refreshed
    inventory does not mention a use case target surface, the use case is
    unaffected by that scoped refresh. When the target is mentioned and changed,
    it is affected. If there is no usable path signal, impact stays unknown.
    """

    incoming = normalize_inventory(incoming_inventory_data or {}, scope="all")
    existing = normalize_inventory(existing_inventory_data or {}, scope="all") if existing_inventory_data else None
    if not incoming.items:
        return [
            RefreshImpactResult(
                alias=str(record.alias),
                status="unknown",
                reason="Understanding refresh did not include inventory paths that can be compared to this use case.",
                affectedAreas=["inventory"],
                recommendedAction="validate",
                generatedAt=generated_at,
            )
            for record in records
        ]

    impacts: list[RefreshImpactResult] = []
    for record in records:
        target = str(getattr(record, "targetSurface", "") or "")
        new_matches = _matching_inventory_items(incoming.items, target)
        if not new_matches:
            impacts.append(
                RefreshImpactResult(
                    alias=str(record.alias),
                    status="unaffected",
                    reason="Refreshed inventory did not touch this use case target surface.",
                    recommendedAction="none",
                    generatedAt=generated_at,
                )
            )
            continue
        old_matches = _matching_inventory_items(existing.items if existing else [], target)
        old_by_id = {item.id: item.to_dict() for item in old_matches}
        changed = [item for item in new_matches if old_by_id.get(item.id) != item.to_dict()]
        status = "affected" if changed else "unaffected"
        impacts.append(
            RefreshImpactResult(
                alias=str(record.alias),
                status=status,
                reason=(
                    "Refreshed inventory changed this use case target surface."
                    if status == "affected"
                    else "Refreshed inventory includes this target surface but did not change its recorded inventory item."
                ),
                affectedAreas=sorted({item.path for item in changed}) if changed else [],
                recommendedAction="validate" if status == "affected" else "none",
                generatedAt=generated_at,
            )
        )
    return impacts


def _validate_inventory(inventory: CoverageInventory) -> None:
    item_ids = {item.id for item in inventory.items if item.id}
    for item in inventory.items:
        if not item.id:
            raise ValueError("Coverage inventory items require id.")
        if item.inventoryStatus == "excluded" and not item.exclusionReason:
            raise ValueError(f"Excluded inventory item {item.id} requires exclusionReason.")
    for candidate in inventory.candidateUseCases:
        if not candidate.alias:
            raise ValueError("Candidate validation use cases require alias.")
        if not candidate.rationale:
            raise ValueError(f"Candidate validation use case {candidate.alias} requires rationale.")
        if not candidate.sourceInventoryItems:
            raise ValueError(
                f"Candidate validation use case {candidate.alias} requires sourceInventoryItems. "
                "Add sourceInventoryItems referencing coverageInventory.items[].id, or include a candidate surface/path/sourceRefs that can be normalized."
            )
        missing = [item for item in candidate.sourceInventoryItems if item not in item_ids]
        if missing:
            raise ValueError(
                f"Candidate validation use case {candidate.alias} references unknown inventory items: {', '.join(missing)}. "
                "Use values from coverageInventory.items[].id."
            )


def _computed_status(inventory: CoverageInventory) -> str:
    if inventory.partialInventoryReasons:
        return "partial"
    if inventory.staleAreas or any(item.inventoryStatus == "stale" for item in inventory.items):
        return "stale"
    if inventory.uncoveredAreas:
        return "partial"
    if any(item.userFacing and item.inventoryStatus == "uncovered" for item in inventory.items):
        return "partial"
    if all(
        (not item.userFacing) or item.inventoryStatus == "covered" or (item.inventoryStatus == "excluded" and item.exclusionReason)
        for item in inventory.items
    ):
        return "complete" if inventory.items else "partial"
    return "partial"


def _priority_rank(priority: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(priority, 2)


def _candidate_sources(candidate: dict[str, Any], items: list[Any], item_ids: list[str]) -> list[str]:
    explicit_refs = _string_list(candidate.get("sourceRefs") or candidate.get("sourceContext") or candidate.get("sourceFiles"))
    explicit_refs.extend(_string_list(candidate.get("sourceInventoryItems")))
    for ref in explicit_refs:
        if ref in item_ids:
            return [ref]
    surface = str(candidate.get("surface") or candidate.get("targetSurface") or candidate.get("route") or candidate.get("path") or "")
    alias = str(candidate.get("alias") or candidate.get("candidateAlias") or "")
    text = " ".join([surface, alias, str(candidate.get("behavior") or ""), str(candidate.get("description") or "")]).lower()
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        item_id = str(item.get("id") or "")
        source_refs = _string_list(item.get("sourceRefs"))
        if item_id and item_id in explicit_refs:
            return [item_id]
        if source_refs and any(ref and any(ref == candidate_ref or ref in candidate_ref or candidate_ref in ref for candidate_ref in explicit_refs) for ref in source_refs):
            return [item_id]
        if path and surface and (_surface_matches(path, surface) or path in surface or surface in path):
            return [str(item.get("id"))]
        if item_id and item_id.lower() in text:
            return [item_id]
    return item_ids[:1] if len(item_ids) == 1 else []


def _surface_matches(item_path: str, candidate_surface: str) -> bool:
    if item_path == candidate_surface:
        return True
    if "[" not in item_path and "]" not in item_path:
        return False
    pattern = re.escape(item_path)
    pattern = re.sub(r"\\\[[^\\]+\\\]", r".+", pattern)
    return re.match(f"^{pattern}$", candidate_surface) is not None


def _matching_inventory_items(items: list[CoverageInventoryItem], target_surface: str) -> list[CoverageInventoryItem]:
    if not target_surface:
        return []
    matches: list[CoverageInventoryItem] = []
    for item in items:
        if item.path and (_surface_matches(item.path, target_surface) or item.path in target_surface or target_surface in item.path):
            matches.append(item)
    return matches


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"
