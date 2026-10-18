import datetime as dt, tzdrift
s = dt.datetime(2026, 10, 17, tzinfo=dt.timezone.utc)
assert tzdrift.release_to_pip("2026b") == "2026.2"
r = tzdrift.drift("2026a", "2026e", s, 365, step=3)
assert r["keys"] == 11 and len(r["rule_sets"]) == 6
van = next(x for x in r["rule_sets"] if x["zone"] == "America/Vancouver")
assert van["first_wrong"].startswith("2026-11-01") and van["shift_min"] == -60     # Cal issue #30104, from first principles
assert any(x["zone"] == "America/Winnipeg" for x in r["rule_sets"])                 # canonical name, not Rainy_River
r2 = tzdrift.drift("2026b", "2026e", s, 365, step=3)
assert "America/Vancouver" not in {x["zone"] for x in r2["rule_sets"]} and len(r2["rule_sets"]) == 5
print("all tests passed")
