"""Checks ported from RemoveMacAI's SelfTest.swift (profile and catalog parts)."""
import contextlib
import io
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mac_ai_off as m  # noqa: E402

ALL = {f["id"] for f in m.available_features((27, 0))}


def payloads(profile):
    return profile["PayloadContent"]


def restrictions(profile):
    return next((p for p in payloads(profile) if p["PayloadType"] == "com.apple.applicationaccess"), None)


def forced(profile, domain):
    p = next((p for p in payloads(profile) if p["PayloadIdentifier"].endswith(".preferences." + domain)), None)
    return p and p["PayloadContent"][domain]["Forced"][0]["mcx_preference_settings"]


class Catalog(unittest.TestCase):
    def test_off_removes_every_model_set(self):
        self.assertEqual(set(m.sets_to_remove(set(), (27, 0))), {s["name"] for s in m.available_sets((27, 0))})

    def test_kept_feature_keeps_its_models_only(self):
        kept = m.sets_to_remove({"writing-tools"}, (27, 0))
        self.assertNotIn(m.FOUNDATION, kept)
        self.assertIn(m.VISUAL, kept)

    def test_keeping_everything_removes_nothing(self):
        self.assertEqual(m.sets_to_remove(ALL, (27, 0)), [])

    def test_catalog_is_consistent(self):
        names = {s["name"] for s in m.MODEL_SETS}
        self.assertTrue(all(s in names for f in m.FEATURES for s in f["sets"]))
        self.assertEqual(len({f["id"] for f in m.FEATURES}), len(m.FEATURES))

    def test_features_follow_macos_version(self):
        ids = {f["id"] for f in m.available_features((15, 1))}
        self.assertNotIn("chatgpt", ids)          # 15.2
        self.assertNotIn("spatial-photos", ids)   # 26.0
        self.assertNotIn(m.SPATIAL, {s["name"] for s in m.available_sets((15, 1))})
        self.assertEqual(len(ALL), 14)


class Profile(unittest.TestCase):
    def test_full_off_profile(self):
        p = m.build(ai=set(), tweaks=set(), macos=(27, 0))
        r = restrictions(p)
        self.assertIs(r["allowWritingTools"], False)
        self.assertIs(r["allowAssistant"], False)
        blocks = forced(p, "com.apple.MobileAsset")
        self.assertEqual(len(blocks), len(m.available_sets((27, 0))))
        self.assertTrue(all(v.startswith("https://127.0.0.1:9/") for v in blocks.values()))
        self.assertIs(forced(p, "com.apple.Siri")["VoiceTriggerUserEnabled"], False)
        self.assertIs(forced(p, "group.com.apple.mail")["DisableAutomaticMessageSummarization"], True)

    def test_uuids_unique_and_stable(self):
        p = m.build(ai=set(), tweaks=set(), macos=(27, 0))
        uuids = [x["PayloadUUID"] for x in payloads(p)] + [p["PayloadUUID"]]
        self.assertEqual(len(set(uuids)), len(uuids))
        self.assertEqual(m.uuid5ish("a"), m.uuid5ish("a"))
        # Same bytes as Swift: SHA1(name)[:16] with version 5 and RFC 4122 variant bits.
        self.assertEqual(m.uuid5ish("a"), "86F7E437-FAA5-57FC-A15D-1DDCB9EAEAEA")

    def test_marker_records_features(self):
        mk = forced(m.build(ai=set(), tweaks=set(), macos=(27, 0)), m.IDENTIFIER)
        self.assertEqual(mk["features"], ",".join(sorted(ALL)))
        self.assertIs(mk["installed"], True)
        self.assertIs(mk["ai"], True)

    def test_kept_feature_left_alone(self):
        r = restrictions(m.build(ai={"writing-tools"}, tweaks=set(), macos=(27, 0)))
        self.assertNotIn("allowWritingTools", r)
        self.assertIs(r["allowGenmoji"], False)

    def test_tweak_only_profile(self):
        p = m.build(ai=None, tweaks={"analytics", "lookup-suggestions"}, macos=(27, 0))
        r = restrictions(p)
        self.assertIs(r["allowDiagnosticSubmission"], False)
        self.assertNotIn("allowWritingTools", r)
        self.assertIsNone(forced(p, "com.apple.MobileAsset"))
        mk = forced(p, m.IDENTIFIER)
        self.assertIs(mk["ai"], False)
        self.assertEqual(mk["tweaks"], "analytics,lookup-suggestions")
        self.assertIs(forced(p, "com.apple.lookup.shared")["LookupSuggestionsDisabled"], True)

    def test_forced_int_values_stay_integers(self):
        s = forced(m.build(ai=None, tweaks={"improve-siri"}, macos=(27, 0)), "com.apple.assistant.support")
        self.assertEqual(s["Siri Data Sharing Opt-In Status"], 2)
        self.assertIsInstance(s["Siri Data Sharing Opt-In Status"], int)

    def test_no_restrictions_payload_without_allow_keys(self):
        p = m.build(ai=None, tweaks={"lookup-suggestions"}, macos=(27, 0))
        self.assertIsNone(restrictions(p))

    def test_presets(self):
        self.assertEqual(m.preset("recommended"), {"analytics", "personalized-ads", "improve-siri",
                                                   "improve-search", "spotlight-web", "lookup-suggestions"})
        self.assertEqual(m.preset("privacy"), m.preset("recommended") | {"safari-suggestions", "game-center"})

    def test_unknown_names_rejected(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            m.main(["--keep", "siri-ai", "-o", os.devnull])


class Cli(unittest.TestCase):
    def test_writes_a_valid_plist(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "x.mobileconfig")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "mac_ai_off.py"), "--keep", "siri",
                                "--preset", "recommended", "-o", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as f:
                p = plistlib.load(f)
            self.assertEqual(p["PayloadType"], "Configuration")
            self.assertNotIn("allowAssistant", restrictions(p))
            self.assertIs(restrictions(p)["allowSpotlightInternetResults"], False)
            self.assertIn("Writing Tools", r.stdout)

    def test_prebuilt_profiles_match_generator(self):
        for name, kw in m.PREBUILT.items():
            with open(os.path.join(ROOT, "profiles", name), "rb") as f:
                self.assertEqual(f.read(), m.dump(m.build(**kw)), name)


if __name__ == "__main__":
    unittest.main()
