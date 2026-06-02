def is_guest_owner(owner_user_id: str) -> bool:
    return (owner_user_id or "").startswith("anon:")


def assert_not_guest_persist(owner_user_id: str, *, resource: str = "data") -> None:
    if is_guest_owner(owner_user_id):
        raise ValueError(
            f"Guest {resource} must be stored locally in the browser (IndexedDB), not on the server."
        )
