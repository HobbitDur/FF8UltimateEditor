"""Execution IDs and the Seq/Cam combinations verified for direct commands."""

DIRECT_COMMAND_ANIMATIONS = {command: (11, tuple(range(6)))
                             for command in (24, 25, 26, 27, 30, 32, 33, 34)}
DIRECT_COMMAND_ANIMATIONS.update({23: (23, ()), 31: (24, (6, 7))})
DIRECT_TYPE_IDS = (24, 23, 31)
FIRST_DLL_TYPE = 39
LAST_DLL_TYPE = 0xAF  # 0xB0 and above are engine-internal command IDs.


def command_type_name(code):
    profile = DIRECT_COMMAND_ANIMATIONS.get(code or 24)
    if profile:
        seq, cameras = profile
        cam = "0–5" if len(cameras) == 6 else "6–7" if cameras else "none"
        suffix = " (default alias)" if code == 0 else " (existing alias)" if code not in DIRECT_TYPE_IDS else ""
        return f"{code}: Seq {seq} / Cam {cam}{suffix}"
    return f"{code}: DLL-defined" if code >= FIRST_DLL_TYPE else f"{code}: native path (requires DLL support)"


def command_type_options(used_ids=()):
    # Preserve existing aliases byte-for-byte, without offering every equivalent ID for new work.
    codes = list(DIRECT_TYPE_IDS) + sorted(set(used_ids) - set(DIRECT_TYPE_IDS))
    return [{"value": code, "name": command_type_name(code)} for code in codes]
