from .literature import source_ok

INDEXES = {"SCIE", "SSCI", "AHCI", "ESCI", "KCI 등재", "KCI 등재후보"}


def venue_fields(venue):
    if venue.get("category") == "conference":
        return ("guidelines", "schedule", "cost")
    return ("index", "cost", "guidelines", "schedule", "metrics")


def verified_field(journal, key):
    field = journal.get(key)
    if field is None:
        field = {}
    if not isinstance(field, dict):
        raise ValueError(f"journal.{key}: 객체 또는 null 필요")
    source = field.get("source")
    if source is None:
        source = {}
    if not isinstance(source, dict):
        raise ValueError(f"journal.{key}.source: 객체 또는 null 필요")
    if field.get("status") != "verified" or not source_ok(source) or source.get("official") is not True or not str(source.get("url", "")).startswith("https://"):
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if journal.get("category") == "conference":
        identity_matches = (
            bool(journal.get("name") and journal.get("edition"))
            and source.get("venue_name") == journal["name"]
            and source.get("edition") == journal["edition"]
            and source.get("track") == journal.get("track")
        )
    else:
        identity_matches = (
            bool(journal.get("issn"))
            and source.get("issn") == journal["issn"]
            and source.get("journal_name") == journal.get("name")
        )
    if not identity_matches:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if key == "index" and field.get("value") not in INDEXES:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if key == "metrics" and (not field.get("year") or not field.get("category")):
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if field.get("value") is None:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    return {"value": field["value"], "checked_at": source["checked_at"], "source": source["url"]}


def recheck_journals(state, as_of=None, max_age_days=90):
    from datetime import date
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0:
        raise ValueError("max_age_days: 0 이상의 정수 필요")
    target = date.fromisoformat(as_of) if as_of else date.today()
    results = []
    for journal in state["journals"]:
        fields = {}
        for key in venue_fields(journal):
            verified = verified_field(journal, key)
            checked = date.fromisoformat(verified["checked_at"][:10]) if verified["source"] else None
            age = (target - checked).days if checked else None
            status = "unverified" if checked is None else "future_date" if age < 0 else "stale" if age > max_age_days else "current"
            fields[key] = {**verified, "status": status, "age_days": age, "needs_recheck": status != "current"}
        results.append({"id": journal["id"], "name": journal.get("name"), "as_of": target.isoformat(), "max_age_days": max_age_days, "fields": fields})
    return results
