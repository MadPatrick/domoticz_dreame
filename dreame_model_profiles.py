MODEL_PROFILES = {
    # =========================
    # L10 SERIES
    # =========================
    "dreame.vacuum.r2257": {
        "profile_key": "dreame.vacuum.r2257",
        "name": "Dreame L10 Ultra",
    },
    "dreame.vacuum.r2257o": {
        "profile_key": "dreame.vacuum.r2257o",
        "name": "Dreame L10s Ultra",
    },
    "dreame.vacuum.r2216": {
        "profile_key": "dreame.vacuum.r2216",
        "name": "Dreame Z10 Pro",
    },

    # =========================
    # L20 SERIES
    # =========================
    "dreame.vacuum.r2228": {
        "profile_key": "dreame.vacuum.r2228",
        "name": "Dreame L20 Ultra",
    },
    "dreame.vacuum.r2228a": {
        "profile_key": "dreame.vacuum.r2228a",
        "name": "Dreame L20 Ultra (variant)",
    },

    # =========================
    # L40 SERIES
    # =========================
    "dreame.vacuum.r2492j": {
        "profile_key": "dreame.vacuum.r2492j",
        "name": "Dreame L40 Ultra",
    },
    "dreame.vacuum.r2492": {
        "profile_key": "dreame.vacuum.r2492",
        "name": "Dreame L40 Ultra (base)",
    },

    # =========================
    # X30 SERIES
    # =========================
    "dreame.vacuum.r2387": {
        "profile_key": "dreame.vacuum.r2387",
        "name": "Dreame X30 Ultra",
    },
    "dreame.vacuum.r2387a": {
        "profile_key": "dreame.vacuum.r2387a",
        "name": "Dreame X30 Ultra (variant)",
    },

    # =========================
    # X40 SERIES
    # =========================
    "dreame.vacuum.r2416c": {
        "profile_key": "dreame.vacuum.r2416c",
        "name": "Dreame X40 Ultra",
    },
    "dreame.vacuum.r2416": {
        "profile_key": "dreame.vacuum.r2416",
        "name": "Dreame X40 Ultra (base)",
    },

    # =========================
    # X50 SERIES
    # =========================
    "dreame.vacuum.r2506": {
        "profile_key": "dreame.vacuum.r2506",
        "name": "Dreame X50 Ultra",
    },
    "dreame.vacuum.r2506a": {
        "profile_key": "dreame.vacuum.r2506a",
        "name": "Dreame X50 Ultra (variant)",
    },

    # =========================
    # GENERIC FALLBACKS
    # =========================
    "dreame.vacuum": {
        "profile_key": "dreame.vacuum",
        "name": "Generic Dreame Vacuum",
    },
    "default": {
        "profile_key": "default",
        "name": "Generic Dreame",
    },
}

def get_model_profile(model):
    model = model or "default"
    if model in MODEL_PROFILES:
        return dict(MODEL_PROFILES[model])

    parts = str(model).split(".")
    if len(parts) >= 2:
        family = ".".join(parts[:2])
        if family in MODEL_PROFILES:
            profile = dict(MODEL_PROFILES[family])
            profile["profile_key"] = family + " fallback for " + str(model)
            return profile

    profile = dict(MODEL_PROFILES["default"])
    profile["profile_key"] = "default fallback for " + str(model)
    return profile
