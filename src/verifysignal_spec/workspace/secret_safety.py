"""Secret-looking value detection shared by readers and validators."""

from __future__ import annotations

import base64
import binascii
import math
import re
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlsplit

SECRET_FIELD_RE = re.compile(
    r"(password|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|authorization)",
    re.I,
)
AUTH_CREDENTIAL_RE = re.compile(
    r"\b(?P<scheme>Bearer|Basic)\s+(?P<credential>[A-Za-z0-9._~+/=-]+)",
    re.I,
)
HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9_./+=-]{32,}$")
HEX_IDENTIFIER_RE = re.compile(r"^[a-f0-9]{7,64}$", re.I)
PUBLIC_DIGEST_RE = re.compile(r"^(sha256:)?[a-f0-9]{64}$", re.I)
SECRET_CONTAINER_FIELDS = {
    "password",
    "secret",
    "token",
    "credential",
    "apikey",
    "accesskey",
    "privatekey",
    "clientsecret",
    "authorization",
}
DUMMY_VALUES = {
    "example",
    "dummy",
    "placeholder",
    "changeme",
    "test",
    "sample",
    "qa@example.com",
}
SECRET_QUERY_PARAM_RE = re.compile(
    r"^(token|(?:[a-z0-9]+[_-])+token|secret|credential(?:s)?|signature|sig|api[_-]?key|access[_-]?(?:key|token)|client[_-]?secret|authorization|auth|password|pwd)$",
    re.I,
)
ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
LOCAL_CONFIG_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
ENV_ASSIGNMENT_RE = re.compile(r"\b[A-Z_][A-Z0-9_]*\s*=\s*['\"]?[^'\"\s]+")
CREDENTIAL_REFERENCE_RE = re.compile(
    r"^[^:/\\\s@]+:[^/\\\s@]+@[^/\\\s@]+"
)
URI_USERINFO_RE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|//)[^/\s<>\"'`:@]+:[^/\s<>\"'`@]+@",
    re.I,
)
WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:(?!//)")
EMBEDDED_QUERY_PAIR_RE = re.compile(
    r"[?&#](?P<key>[^?&#=\s]+)=(?P<value>[^&#\s<>\"'`]+)",
    re.I,
)
URI_REFERENCE_CANDIDATE_RE = re.compile(
    r"""
    (?:
        [a-z][a-z0-9+.-]*://[^\s<>\"'`]+ |
        //[^\s<>\"'`]+ |
        /[^\s<>\"'`]*[?#][^\s<>\"'`]* |
        (?<![\w@])[^:/\s@]+:[^/\s@]+@[^/\s@]+(?:[/?#][^\s<>\"'`]*)?
    )
    """,
    re.I | re.X,
)
PUBLIC_SELECTOR_COLLECTION_FIELDS = {"controls", "targets"}
PUBLIC_SELECTOR_SHAPE_FIELDS = {
    "all",
    "any",
    "css",
    "domainsemantics",
    "exact",
    "label",
    "name",
    "nth",
    "role",
    "semanticlocator",
    "testid",
    "text",
}
PUBLIC_TOKEN_POLICY_FIELDS = {
    "defaultreceiptttldays",
    "defaulttokenttldays",
    "exchangecount",
    "hourlyexchangecount",
    "maxexchanges",
    "maxexchangesperhour",
    "maxusecases",
    "policyid",
    "policyversion",
    "refresh",
    "ttldays",
    "validationmode",
}
PUBLIC_TOKEN_POLICY_INTEGER_FIELDS = {
    "defaultreceiptttldays",
    "defaulttokenttldays",
    "exchangecount",
    "hourlyexchangecount",
    "maxexchanges",
    "maxexchangesperhour",
    "maxusecases",
    "policyversion",
    "ttldays",
}
PUBLIC_TOKEN_POLICY_ENUM_FIELDS = {
    "policyid": {"public-free"},
    "refresh": {"silent-credential"},
    "validationmode": {"happy-path-only"},
}
PUBLIC_SELECTOR_PRIMARY_FIELDS = {
    "all",
    "any",
    "css",
    "label",
    "role",
    "semanticlocator",
    "testid",
    "text",
}
PUBLIC_SELECTOR_STRING_FIELDS = {
    "css",
    "domainsemantics",
    "label",
    "name",
    "role",
    "semanticlocator",
    "testid",
    "text",
}
PUBLIC_AUTH_PROSE_WORDS = {
    "authentication",
    "authorization",
    "credentials",
}
PROVIDER_SECRET_QUERY_KEYS = {
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-credential",
    "x-goog-signature",
}
PUBLIC_SCHEMA_VERSION_RE = re.compile(
    r"^[a-z][a-z0-9.-]*(?:-[a-z0-9.-]+)*/v[0-9]+$"
)
PUBLIC_BRANCH_RE = re.compile(
    r"^(?![./])(?!.*(?:^|/)\.\.?(?:/|$))(?=.*[./-])[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
PUBLIC_CODE_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z][a-z0-9-]*)+$"
)
PUBLIC_REASON_CODE_RE = re.compile(
    r"^[a-z]{2,24}(?:-[a-z]{2,24}){2,}$"
)
PUBLIC_CODE_FIELD_NAMES = {"blockercode", "code", "errorcode", "findingids"}
PUBLIC_SLUG_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+){2,}(?:-\d{8}T\d{6}Z)?$"
)
PUBLIC_STRUCTURED_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9][a-z0-9-]*)+(?:-\d{8}T\d{6}Z)?$"
)
PUBLIC_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*_[0-9]{10,17}$")
PUBLIC_PREFIXED_UUID_RE = re.compile(
    r"^(?:[a-z][a-z0-9]{0,15}_)?"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
# Dotted document pointers as emitted by Core validation findings (zod
# `issue.path.join(".")`): short identifier-or-index segments only. Segment
# caps keep base64url payloads (JWT segments, signatures) out of this shape.
PUBLIC_DOCUMENT_POINTER_RE = re.compile(
    r"^[a-z][A-Za-z0-9]{0,23}(?:\.(?:[A-Za-z][A-Za-z0-9]{0,23}|[0-9]{1,4})){1,11}$"
)
PUBLIC_PATH_FIELD_NAMES = {
    "evidencedir",
    "file",
    "path",
    "recordpath",
    "reportpath",
    "route",
    "surface",
}
PUBLIC_RECOMMENDED_ACTION_VALUES = {
    "blocked",
    "clarify",
    "confirm",
    "continue",
    "environment-recovery",
    "implement-repair",
    "none",
    "obsolete",
    "plan",
    "replan",
    "rerun",
    "resume-current-stage",
    "review-created-resource-before-rerun",
    "review-side-effect-violation-before-rerun",
    "safe-repair",
    "validate",
    "wait-for-active-run",
}
MAX_URI_DECODE_DEPTH = 3
MAX_SECRET_SCAN_DEPTH = 512
MAX_SECRET_SCAN_NODES = 100_000


def looks_secret(value: Any, field_name: str = "") -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if text.lower() in DUMMY_VALUES:
        return False
    normalized_field = field_name.lower()
    # A field-name exemption only describes the expected public value. It must
    # never make an otherwise credential-bearing URL safe to persist.
    if _url_contains_secret_locator(text):
        return True
    if _contains_authorization_credential(text):
        return True
    if (
        re.sub(r"[_-]", "", normalized_field) in SECRET_CONTAINER_FIELDS
        or SECRET_FIELD_RE.search(field_name)
    ) and text.lower() not in DUMMY_VALUES:
        return True
    if _is_public_digest_field_value(normalized_field, text):
        return False
    # Exemptions describe expected public metadata, not arbitrary contents.
    # Check opaque secret-like values before applying those exemptions.
    if _looks_like_opaque_secret(text, normalized_field):
        return True
    if field_name in {
        "schemaVersion",
        "version",
        "id",
        "path",
        "file",
        "route",
        "surface",
        "branch",
        "candidateAlias",
        "sourceInventoryItems",
        "recordPath",
        "reportPath",
        "evidenceDir",
        "planFingerprint",
        "sha256",
        "generatedGitHash",
        "tokenPolicy",
    }:
        return False
    return False


def runtime_input_name_looks_secret(name: str) -> bool:
    return bool(SECRET_FIELD_RE.search(name or ""))


def validate_no_secret_values(data: Any, path: str = "") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    stack: list[tuple[str, Any, str, str, int]] = [
        ("visit", data, path, "", 0)
    ]
    active_containers: set[int] = set()
    visited_nodes = 0
    while stack:
        action, value, current_path, secret_field_name, depth = stack.pop()
        if action == "leave":
            active_containers.discard(int(value))
            continue
        visited_nodes += 1
        if visited_nodes > MAX_SECRET_SCAN_NODES:
            findings.append(_unsafe_structure_finding(current_path, "size"))
            break
        if isinstance(value, (dict, list)):
            if depth > MAX_SECRET_SCAN_DEPTH:
                findings.append(_unsafe_structure_finding(current_path, "depth"))
                continue
            if len(value) > MAX_SECRET_SCAN_NODES - visited_nodes:
                findings.append(_unsafe_structure_finding(current_path, "size"))
                continue
            container_id = id(value)
            if container_id in active_containers:
                findings.append(_unsafe_structure_finding(current_path, "cycle"))
                continue
            active_containers.add(container_id)
            stack.append(("leave", container_id, current_path, "", depth))
            if isinstance(value, dict):
                children: list[tuple[str, Any, str, str, int]] = []
                for key, child in value.items():
                    child_path = f"{current_path}.{key}" if current_path else str(key)
                    if _is_secret_container_field(str(key), child_path, child):
                        child_secret_field = str(key)
                    else:
                        child_secret_field = secret_field_name
                        generated_field = _generated_runtime_value_field(value, str(key))
                        if not child_secret_field and generated_field:
                            child_secret_field = generated_field
                    children.append(
                        ("visit", child, child_path, child_secret_field, depth + 1)
                    )
                stack.extend(reversed(children))
            else:
                for index in range(len(value) - 1, -1, -1):
                    stack.append(
                        (
                            "visit",
                            value[index],
                            f"{current_path}[{index}]",
                            secret_field_name,
                            depth + 1,
                        )
                    )
            continue
        if _is_public_credential_ref_key_name(current_path, value):
            continue
        if _is_public_session_ref_key_name(current_path, value):
            continue
        if _is_public_artifact_fingerprint(current_path, value):
            continue
        if looks_secret(value, secret_field_name or _leaf_field_name(current_path)):
            findings.append(_secret_value_finding(current_path))
    return findings


def _secret_value_finding(path: str) -> dict[str, str]:
    return {
        "severity": "blocking",
        "code": "secret-looking-value",
        "path": path,
        "message": "Secret-looking value must not be persisted.",
    }


def _unsafe_structure_finding(path: str, reason: str) -> dict[str, str]:
    return {
        "severity": "blocking",
        "code": "secret-scan-unsafe-structure",
        "path": path,
        "message": f"Secret scan refused unsafe {reason} structure.",
    }


def _is_secret_container_field(field_name: str, path: str, value: Any) -> bool:
    normalized = re.sub(r"[_-]", "", field_name).lower()
    parent_path = path.rsplit(".", 1)[0] if "." in path else ""
    parent_field = _leaf_field_name(parent_path)
    if normalized == "tokenpolicy" and _is_public_token_policy_shape(value):
        return False
    if (
        parent_field in PUBLIC_SELECTOR_COLLECTION_FIELDS
        and _is_public_selector_shape(value)
    ):
        return False
    return normalized in SECRET_CONTAINER_FIELDS or bool(
        SECRET_FIELD_RE.search(field_name)
    )


def _generated_runtime_value_field(container: dict[Any, Any], key: str) -> str:
    if key != "value" or container.get("source") != "generated":
        return ""
    name = container.get("name")
    if not isinstance(name, str) or not LOCAL_CONFIG_KEY_RE.fullmatch(name):
        return ""
    if runtime_input_name_looks_secret(name):
        return ""
    return name


def _is_public_digest_field_value(field_name: str, text: str) -> bool:
    if field_name in {"hash", "planfingerprint", "sha256"}:
        return bool(PUBLIC_DIGEST_RE.match(text) or HEX_IDENTIFIER_RE.match(text))
    return any(
        term in field_name
        for term in (
            "githash",
            "gitsha",
            "commithash",
            "commitsha",
            "revision",
        )
    ) and bool(HEX_IDENTIFIER_RE.match(text))


def _url_contains_secret_locator(text: str, *, depth: int = 0) -> bool:
    if URI_USERINFO_RE.search(text):
        return True
    if _embedded_query_contains_secret(text, depth=depth):
        return True
    if WINDOWS_DRIVE_PATH_RE.match(text):
        parts = re.split(r"[\s;,|]+", text, maxsplit=1)
        return bool(
            len(parts) == 2
            and _url_contains_secret_locator(parts[1], depth=depth)
        )

    candidates = [text.strip("()[]{}<>.,;!")]
    candidates.extend(
        match.group(0).strip("()[]{}<>.,;!")
        for match in URI_REFERENCE_CANDIDATE_RE.finditer(text)
    )
    if any(
        _uri_reference_contains_secret(candidate, depth=depth)
        for candidate in dict.fromkeys(candidates)
        if candidate
    ):
        return True
    if depth >= MAX_URI_DECODE_DEPTH:
        return False
    decoded = unquote_plus(text)
    return decoded != text and _url_contains_secret_locator(decoded, depth=depth + 1)


def _uri_reference_contains_secret(text: str, *, depth: int = 0) -> bool:
    text = text.strip("()[]{}<>.,;!")
    if WINDOWS_DRIVE_PATH_RE.match(text):
        return False
    if URI_USERINFO_RE.search(text):
        return True
    if not text.lower().startswith("mailto:") and CREDENTIAL_REFERENCE_RE.match(text):
        return True
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    if parsed.username or parsed.password:
        return True
    return _query_component_contains_secret(parsed.query, depth=depth) or (
        _query_component_contains_secret(parsed.fragment, depth=depth)
    )


def _embedded_query_contains_secret(text: str, *, depth: int) -> bool:
    for match in EMBEDDED_QUERY_PAIR_RE.finditer(text):
        key = unquote_plus(match.group("key"))
        value = unquote_plus(match.group("value")).strip("()[]{}<>.,;!")
        if _secret_query_pair(key, value):
            return True
        if (
            depth < MAX_URI_DECODE_DEPTH
            and value
            and _url_contains_secret_locator(value, depth=depth + 1)
        ):
            return True
    return False


def _query_component_contains_secret(component: str, *, depth: int) -> bool:
    if not component:
        return False
    for key, value in parse_qsl(component, keep_blank_values=True):
        if _secret_query_pair(key, value):
            return True
        if (
            depth < MAX_URI_DECODE_DEPTH
            and value
            and _url_contains_secret_locator(value, depth=depth + 1)
        ):
            return True
    return False


def _secret_query_pair(key: str, value: str) -> bool:
    return bool(
        _secret_query_key(key)
        and value
        and value.lower() not in DUMMY_VALUES
    )


def _secret_query_key(key: str) -> bool:
    normalized = unquote_plus(key).strip().lower()
    segments = [
        segment
        for segment in re.split(r"[\[\].]+", normalized)
        if segment
    ]
    return any(
        segment in PROVIDER_SECRET_QUERY_KEYS
        or bool(SECRET_QUERY_PARAM_RE.fullmatch(segment))
        for segment in segments
    )


def _contains_authorization_credential(text: str) -> bool:
    for match in AUTH_CREDENTIAL_RE.finditer(text):
        scheme = match.group("scheme").lower()
        credential = match.group("credential")
        if scheme == "basic":
            if _is_basic_credential(credential):
                return True
            continue
        if credential.lower() in PUBLIC_AUTH_PROSE_WORDS:
            continue
        return True
    return False


def _is_basic_credential(value: str) -> bool:
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return False
    return b":" in decoded


def _looks_like_opaque_secret(text: str, field_name: str) -> bool:
    if not HIGH_ENTROPY_RE.fullmatch(text) or _entropy(text) <= 3.5:
        return False
    if _is_contextual_public_identifier(field_name, text):
        return False
    if "/" in text:
        return _is_encoded_secret_payload(text)
    return True


def _is_encoded_secret_payload(value: str) -> bool:
    # b64decode keeps "/" in the alphabet even with altchars, so lowercase
    # kebab relative paths (no dots) decode "successfully". A real >=24-byte
    # base64 payload contains an uppercase character with overwhelming
    # probability; an all-lowercase slash path never does.
    if not any(character.isupper() for character in value):
        return False
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) >= 24


def _is_contextual_public_identifier(field_name: str, text: str) -> bool:
    normalized_field = re.sub(r"[_-]", "", field_name).lower()
    if normalized_field in {"schemaversion", "version"}:
        return bool(PUBLIC_SCHEMA_VERSION_RE.fullmatch(text))
    if normalized_field == "branch":
        return bool(PUBLIC_BRANCH_RE.fullmatch(text))
    if normalized_field in PUBLIC_CODE_FIELD_NAMES:
        return bool(PUBLIC_CODE_RE.fullmatch(text))
    if normalized_field == "reasons":
        return bool(PUBLIC_REASON_CODE_RE.fullmatch(text))
    if normalized_field == "recommendedaction":
        return text in PUBLIC_RECOMMENDED_ACTION_VALUES
    if normalized_field == "preparationhint" and ENV_ASSIGNMENT_RE.search(text):
        # Credential readiness validation owns KEY=value diagnostics so callers
        # retain the stable payload.invalid contract instead of an entropy error.
        return True
    if normalized_field.endswith("id") or normalized_field in {
        "alias",
        "appliesto",
        "candidatealias",
        "projecttitle",
        "resourcename",
        "selectedcandidate",
        "sourceinventoryitems",
        "supersededby",
        "usecasealias",
    }:
        return bool(
            PUBLIC_SLUG_RE.fullmatch(text)
            or PUBLIC_STRUCTURED_ID_RE.fullmatch(text)
            or (
                normalized_field.endswith("id")
                and (
                    PUBLIC_RUN_ID_RE.fullmatch(text)
                    or PUBLIC_PREFIXED_UUID_RE.fullmatch(text)
                )
            )
        )
    if normalized_field in PUBLIC_PATH_FIELD_NAMES:
        return _looks_like_public_path(text)
    return False


def _looks_like_public_path(text: str) -> bool:
    if "=" in text or "\x00" in text or any(character.isspace() for character in text):
        return False
    if PUBLIC_DOCUMENT_POINTER_RE.fullmatch(text):
        return True
    if text.startswith(("./", "../", ".\\", "..\\", ".verifysignal/")):
        return True
    if WINDOWS_DRIVE_PATH_RE.match(text):
        return True
    if not text.startswith("/"):
        return False
    segments = [segment for segment in text.split("/") if segment]
    return len(segments) >= 2 and any(
        "." in segment or segment == ".verifysignal" for segment in segments
    )


def _is_public_token_policy_shape(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    normalized_items = {
        re.sub(r"[_-]", "", str(key)).lower(): item
        for key, item in value.items()
    }
    if len(normalized_items) != len(value) or not set(normalized_items).issubset(
        PUBLIC_TOKEN_POLICY_FIELDS
    ):
        return False
    for field, item in normalized_items.items():
        if field in PUBLIC_TOKEN_POLICY_INTEGER_FIELDS:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                return False
        elif (
            not isinstance(item, str)
            or item not in PUBLIC_TOKEN_POLICY_ENUM_FIELDS.get(field, set())
        ):
            return False
    return True


def _is_public_selector_shape(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    pending = [value]
    seen: set[int] = set()
    while pending:
        selector = pending.pop()
        selector_id = id(selector)
        if selector_id in seen:
            return False
        seen.add(selector_id)
        normalized_items = {
            re.sub(r"[_-]", "", str(key)).lower(): item
            for key, item in selector.items()
        }
        if (
            not normalized_items
            or len(normalized_items) != len(selector)
            or not set(normalized_items).issubset(PUBLIC_SELECTOR_SHAPE_FIELDS)
        ):
            return False
        if (
            len(set(normalized_items).intersection(PUBLIC_SELECTOR_PRIMARY_FIELDS))
            != 1
        ):
            return False
        for field, item in normalized_items.items():
            if field in {"all", "any"}:
                if (
                    not isinstance(item, list)
                    or not item
                    or not all(isinstance(candidate, dict) for candidate in item)
                ):
                    return False
                pending.extend(item)
            elif field in PUBLIC_SELECTOR_STRING_FIELDS:
                if not isinstance(item, str) or not item.strip():
                    return False
            elif field == "exact":
                if not isinstance(item, bool):
                    return False
            elif field == "nth":
                if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                    return False
            else:
                return False
    return True


def _leaf_field_name(path: str) -> str:
    without_indexes = re.sub(r"\[\d+\]", "", path)
    return without_indexes.rsplit(".", 1)[-1]


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {character: text.count(character) for character in set(text)}
    return -sum(
        (count / len(text)) * math.log2(count / len(text))
        for count in counts.values()
    )


def _is_public_credential_ref_key_name(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if ".credentialRefs." not in marker_path or ".keys." not in marker_path:
        return False
    return isinstance(value, str) and bool(ENV_VAR_NAME_RE.match(value.strip()))


def _is_public_session_ref_key_name(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if not marker_path.endswith(".sessionRef.key"):
        return False
    return isinstance(value, str) and bool(LOCAL_CONFIG_KEY_RE.match(value.strip()))


def _is_public_artifact_fingerprint(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if ".artifactFingerprints." not in marker_path:
        return False
    return isinstance(value, str) and bool(PUBLIC_DIGEST_RE.match(value.strip()))
