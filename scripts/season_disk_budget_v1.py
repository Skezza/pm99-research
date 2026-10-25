"""Explicit capacity limits for serial season builds and runtime copies."""
import shutil

DEFAULT_RESERVE = 8 * 1024**3
MINIMUM_RESERVE = 6 * 1024**3


def validate_reserve(value):
    if type(value) is not int or value < MINIMUM_RESERVE:
        raise ValueError("minimum free space must be an integer of at least 6 GiB")
    return value


def require_space(path, planned_bytes, *, minimum_free_bytes=DEFAULT_RESERVE,
                  context="season operation"):
    validate_reserve(minimum_free_bytes)
    if type(planned_bytes) is not int or planned_bytes < 0:
        raise ValueError("planned disk usage must be a nonnegative integer")
    free = shutil.disk_usage(path).free
    if free - planned_bytes < minimum_free_bytes:
        raise ValueError(
            f"{context} would breach the configured "
            f"{minimum_free_bytes / 1024**3:g} GiB reserve "
            f"(free={free}, planned={planned_bytes})")
    return {"free_bytes": free, "planned_bytes": planned_bytes,
            "minimum_free_bytes": minimum_free_bytes}
