#!/usr/bin/env python3
"""Turn off Apple Intelligence on a Mac with one configuration profile.

Builds the same .mobileconfig that RemoveMacAI installs (Apple Intelligence
restrictions, forced preferences, model download blocks, privacy tweaks).
Double-click the file on the Mac to install it; remove the profile in
System Settings > General > Device Management to undo everything.
Catalog keys come from omlahore/RemoveMacAI (MIT), first mapped by 4evy/pared (MIT).
"""
import argparse
import hashlib
import plistlib
import sys
import time
import uuid

IDENTIFIER = "io.github.dodai0419.mac-ai-off"
BLOCKED_URL = "https://127.0.0.1:9/mac-ai-off-blocked/"  # closed local port: downloads fail
ACCESS = "com.apple.applicationaccess"

FOUNDATION = "com.apple.modelcatalog"
VISUAL = "com.apple.MobileAsset.UAF.FM.Visual"
CODE = "com.apple.MobileAsset.UAF.FM.CodeLM"
CLEANUP = "com.apple.MobileAsset.UAF.Photos.MagicCleanup"
SPATIAL = "com.apple.MobileAsset.UAF.Photos.SpatialPhotosRelive"

MODEL_SETS = [
    {"name": FOUNDATION, "asset": "com.apple.MobileAsset.UAF.FM.GenerativeModels", "title": "Apple Intelligence foundation models"},
    {"name": VISUAL, "asset": VISUAL, "title": "Image and Genmoji models"},
    {"name": SPATIAL, "asset": SPATIAL, "title": "Spatial Photos models"},
    {"name": CLEANUP, "asset": CLEANUP, "title": "Photos Clean Up models"},
    {"name": CODE, "asset": CODE, "title": "Xcode code completion models"},
]


def F(id, title, restrictions=(), prefs=(), sets=(), since=(15, 1)):
    return {"id": id, "title": title, "restrictions": list(restrictions), "prefs": list(prefs), "sets": list(sets), "since": since}


FEATURES = [
    F("siri", "Siri and Siri AI", ["allowAssistant"],
      [("com.apple.assistant.support", "Assistant Enabled", False), ("com.apple.Siri", "StatusMenuVisible", False),
       ("com.apple.Siri", "VoiceTriggerUserEnabled", False)], [FOUNDATION]),
    F("chatgpt", "ChatGPT and other AI extensions",
      ["allowExternalIntelligenceIntegrations", "allowExternalIntelligenceIntegrationsSignIn"], since=(15, 2)),
    F("writing-tools", "Writing Tools", ["allowWritingTools"], sets=[FOUNDATION]),
    F("genmoji", "Genmoji", ["allowGenmoji"], sets=[FOUNDATION, VISUAL]),
    F("image-playground", "Image Playground", ["allowImagePlayground"], sets=[FOUNDATION, VISUAL]),
    F("mail", "Mail summaries and smart replies", ["allowMailSummary", "allowMailSmartReplies"],
      [("group.com.apple.mail", "DisableAutomaticMessageSummarization", True),
       ("group.com.apple.mail", "PersonalizedSmartReplies", False)], [FOUNDATION]),
    F("notification-summaries", "Notification summaries",
      prefs=[("group.com.apple.usernoted", "summarize_previews", False)], sets=[FOUNDATION]),
    F("messages-summaries", "Messages summaries",
      prefs=[("com.apple.MobileSMS", "messageSummarizationEnabled", False)], sets=[FOUNDATION]),
    F("safari-summaries", "Safari summaries", ["allowSafariSummary"], sets=[FOUNDATION], since=(15, 4)),
    F("notes-summaries", "Notes transcription summaries", ["allowNotesTranscriptionSummary"], sets=[FOUNDATION], since=(15, 3)),
    F("inline-predictions", "Inline text predictions",
      prefs=[(".GlobalPreferences", "NSAutomaticInlinePredictionEnabled", False)]),
    F("spatial-photos", "Spatial Photos", prefs=[("com.apple.spatialphotosrelive", "LocallyDisabled", True)],
      sets=[SPATIAL], since=(26, 0)),
    F("photos-clean-up", "Photos Clean Up", sets=[CLEANUP]),
    F("xcode-completion", "Xcode predictive code completion", sets=[CODE]),
]

# The profile tweaks of RemoveMacAI: a restriction key set to false, or a locked preference.
TWEAKS = {
    "analytics": ("Turn off Mac Analytics", [("allowDiagnosticSubmission",)], {"recommended"}),
    "personalized-ads": ("Turn off personalized ads", [("allowApplePersonalizedAdvertising",)], {"recommended"}),
    "improve-siri": ("Turn off Improve Siri and Dictation",
                     [("com.apple.assistant.support", "Siri Data Sharing Opt-In Status", 2)], {"recommended"}),
    "improve-search": ("Turn off Improve Search",
                       [("com.apple.assistant.support", "Search Queries Data Sharing Status", 2)], {"recommended"}),
    "spotlight-web": ("Turn off Spotlight internet results", [("allowSpotlightInternetResults",)], {"recommended"}),
    "lookup-suggestions": ("Turn off Look Up suggestions",
                           [("com.apple.lookup.shared", "LookupSuggestionsDisabled", True)], {"recommended"}),
    "safari-suggestions": ("Turn off Safari search suggestions",
                           [("com.apple.Safari", "UniversalSearchEnabled", False),
                            ("com.apple.Safari", "SuppressSearchSuggestions", True)], {"privacy"}),
    "game-center": ("Turn off Game Center", [("allowGameCenter",)], {"privacy"}),
    "iphone-mirroring": ("Turn off iPhone Mirroring", [("allowiPhoneMirroring",)], set()),
    "music-classic": ("Turn off Apple Music in the Music app", [("allowMusicService",)], set()),
    "book-store": ("Turn off the Book Store", [("allowBookstore",)], set()),
}

PREBUILT = {
    "apple-intelligence-off.mobileconfig": {"ai": set(), "tweaks": set()},
    "apple-intelligence-off-recommended.mobileconfig": {"ai": set(), "tweaks": {"analytics", "personalized-ads", "improve-siri", "improve-search", "spotlight-web", "lookup-suggestions"}},
    "privacy-only.mobileconfig": {"ai": None, "tweaks": {"analytics", "personalized-ads", "improve-siri", "improve-search", "spotlight-web", "lookup-suggestions", "safari-suggestions", "game-center"}},
}


def available_features(macos):
    return [f for f in FEATURES if macos >= f["since"]]


def available_sets(macos):
    used = {s for f in available_features(macos) for s in f["sets"]}
    return [s for s in MODEL_SETS if s["name"] in used]


def sets_to_remove(kept, macos):
    """Every available set whose features are all turned off; a kept feature keeps its sets."""
    feats = available_features(macos)
    return [s["name"] for s in available_sets(macos)
            if all(f["id"] not in kept for f in feats if s["name"] in f["sets"])]


def preset(name):
    names = {"recommended", "privacy"} if name == "privacy" else {name}
    return {k for k, (_, _, p) in TWEAKS.items() if p & names}


def uuid5ish(name):
    """SHA1(name)[:16] with version 5 and RFC 4122 variant bits, like RemoveMacAI, so a reinstall replaces the old profile."""
    b = bytearray(hashlib.sha1(name.encode()).digest()[:16])
    b[6] = (b[6] & 0x0F) | 0x50
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b))).upper()


def payload(type_, suffix, name):
    pid = IDENTIFIER + "." + suffix
    return {"PayloadType": type_, "PayloadVersion": 1, "PayloadIdentifier": pid,
            "PayloadUUID": uuid5ish(pid), "PayloadDisplayName": name}


def build(ai, tweaks, macos=(27, 0)):
    """ai: set of features to keep on (None leaves Apple Intelligence alone); tweaks: tweak ids."""
    restrictions = payload(ACCESS, "restrictions", "Restrictions")
    forced = {}
    feats = available_features(macos)
    if ai is not None:
        for f in feats:
            if f["id"] in ai:
                continue
            restrictions.update({k: False for k in f["restrictions"]})
            for domain, key, off in f["prefs"]:
                forced.setdefault(domain, {})[key] = off
        by_name = {s["name"]: s for s in MODEL_SETS}
        for name in sets_to_remove(ai, macos):
            forced.setdefault("com.apple.MobileAsset", {})["DownloadServerBaseURLOverride-" + by_name[name]["asset"]] = BLOCKED_URL
    for tid in sorted(tweaks):
        for change in TWEAKS[tid][1]:
            if len(change) == 1:
                restrictions[change[0]] = False
            else:
                forced.setdefault(change[0], {})[change[1]] = change[2]
    forced[IDENTIFIER] = {"installed": True, "ai": ai is not None, "tweaks": ",".join(sorted(tweaks)),
                          "kept": ",".join(sorted(ai or [])), "features": ",".join(sorted(f["id"] for f in feats))}
    prefs = []
    for domain in sorted(forced):
        p = payload("com.apple.ManagedClient.preferences", "preferences." + domain, "Forced settings: " + domain)
        p["PayloadContent"] = {domain: {"Forced": [{"mcx_preference_settings": forced[domain]}]}}
        prefs.append(p)
    has_restrictions = any(k.startswith("allow") for k in restrictions)
    return {
        "PayloadType": "Configuration", "PayloadVersion": 1, "PayloadIdentifier": IDENTIFIER,
        "PayloadUUID": uuid5ish(IDENTIFIER), "PayloadDisplayName": "mac-ai-off",
        "PayloadDescription": "Turns off Apple Intelligence and the chosen privacy settings, and stops removed "
                              "models downloading again. Remove this profile to undo.",
        "PayloadOrganization": "mac-ai-off", "PayloadScope": "System", "PayloadRemovalDisallowed": False,
        "PayloadContent": ([restrictions] if has_restrictions else []) + prefs,
    }


def dump(profile):
    return plistlib.dumps(profile, fmt=plistlib.FMT_XML, sort_keys=True)


def summary(ai, tweaks, macos):
    lines = []
    if ai is not None:
        for f in available_features(macos):
            lines.append(("  keep " if f["id"] in ai else "  OFF  ") + f["title"])
        titles = {s["name"]: s["title"] for s in MODEL_SETS}
        for name in sets_to_remove(ai, macos):
            lines.append("  BLOCK download: " + titles[name])
    for tid in sorted(tweaks):
        lines.append("  OFF  " + TWEAKS[tid][0])
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", default="mac-ai-off.mobileconfig", help="profile file to write")
    ap.add_argument("--keep", default="", help="comma list of Apple Intelligence features to leave on")
    ap.add_argument("--no-ai", action="store_true", help="leave Apple Intelligence alone (privacy tweaks only)")
    ap.add_argument("--preset", choices=["none", "recommended", "privacy"], default="none")
    ap.add_argument("--tweak", default="", help="comma list of extra tweak ids")
    ap.add_argument("--macos", default="27.0", help="target macOS version (features newer than it are skipped)")
    ap.add_argument("--list", action="store_true", help="list feature and tweak ids")
    ap.add_argument("--build-prebuilt", metavar="DIR", help="write the ready-made profiles into DIR")
    a = ap.parse_args(argv)
    macos = tuple(int(x) for x in a.macos.split("."))[:2] + (0,) * (2 - len(a.macos.split(".")))
    if a.list:
        print("Apple Intelligence features (--keep):")
        print("\n".join(f"  {f['id']:24} {f['title']}" for f in FEATURES))
        print("Tweaks (--tweak):")
        print("\n".join(f"  {k:24} {v[0]}" for k, v in TWEAKS.items()))
        return 0
    if a.build_prebuilt:
        for name, kw in PREBUILT.items():
            with open(f"{a.build_prebuilt}/{name}", "wb") as fh:
                fh.write(dump(build(**kw)))
            print("wrote", name)
        return 0
    kept = {x for x in a.keep.split(",") if x}
    tweaks = {x for x in a.tweak.split(",") if x} | (preset(a.preset) if a.preset != "none" else set())
    bad = (kept - {f["id"] for f in FEATURES}) | (tweaks - set(TWEAKS))
    if bad:
        ap.error("unknown id(s): " + ", ".join(sorted(bad)) + " (see --list)")
    ai = None if a.no_ai else kept
    if ai is None and not tweaks:
        ap.error("nothing to turn off")
    t = time.perf_counter()
    data = dump(build(ai, tweaks, macos))
    ms = (time.perf_counter() - t) * 1000
    with open(a.out, "wb") as fh:
        fh.write(data)
    print(f"macOS {macos[0]}.{macos[1]} profile:")
    print(summary(ai, tweaks, macos))
    print(f"Wrote {a.out} ({len(data)} bytes, built in {ms:.2f} ms).")
    print("On the Mac: double-click it, then approve it in System Settings > General > Device Management.")
    print("Undo: remove the 'mac-ai-off' profile there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
