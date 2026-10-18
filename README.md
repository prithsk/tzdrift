# tzdrift

See timezone bugs before they happen.

A runtime's timezone database is a snapshot. When a government changes its clock rules, every server on an older snapshot starts rendering that zone wrong on the day the change takes effect. tzdrift diffs your runtime's IANA release against the latest one, hour by hour, across every zone, and lists each zone and date that will go wrong inside your horizon.

## Why now

On **November 1, 2026**, British Columbia, Alberta, Manitoba and parts of the Northwest Territories stop changing their clocks. Morocco's rules changed too. The fixes landed across five IANA releases, 2026b through 2026e, the last of them very recently.

| Runtime tzdata | Rule sets wrong in the next 12 months | Timezone keys |
|---|---|---|
| 2026a or older | 6 | 11 |
| 2026b | 5 | 9 |
| 2026c | 2 | 4 |
| 2026d | 1 | 3 |
| 2026e | 0 | 0 |

Measured from October 17, 2026, in three-hour steps.

## Calibration against a real bug

Cal.com issue [#30104](https://github.com/calcom/cal.diy/issues/30104), filed September 6, reports that Cal's default booking emails render America/Vancouver an hour early after November 1, while the slots API and booking page are correct, and that the correct surfaces use tzdb 2026b or later.

tzdrift reproduces that from the IANA data alone. Vancouver first becomes correct in **2026b**, and any older runtime renders it at UTC−08:00 when it should be UTC−07:00, from November 1, an hour early.

It then predicts what the issue doesn't:

- The same stale renderer also gets **Edmonton, Inuvik, Winnipeg, Casablanca and El Aaiún** wrong, five more rule sets and nine more keys.
- A runtime on exactly 2026b, the floor the issue reports for Cal's correct surfaces, is **still wrong for those five**. Edmonton and Morocco were fixed in 2026c, Inuvik in 2026d, Winnipeg in 2026e.

`cal_check.py` tests the second prediction against Cal's live slots API.

<!-- calcheck:start -->
# Cal.com /v2/slots vs IANA 2026e, 2026-11-20

| Zone | Cal returned | Correct (2026e) | Match |
|---|---|---|---|
| America/Vancouver | UTC-07:00 | UTC-07:00 | yes |
| America/Edmonton | UTC-06:00 | UTC-06:00 | yes |
| America/Inuvik | UTC-07:00 | UTC-06:00 | NO |
| America/Winnipeg | UTC-06:00 | UTC-05:00 | NO |
| Africa/Casablanca | UTC+00:00 | UTC+00:00 | yes |
| Africa/El_Aaiun | UTC+00:00 | UTC+00:00 | yes |
| America/Toronto | UTC-05:00 | UTC-05:00 | yes |
| Europe/London | UTC+00:00 | UTC+00:00 | yes |

**2 of 8 zones with slots came back with the wrong offset.**
<!-- calcheck:end -->

## Use it

```
python tzdrift.py --runtime 2026b
python tzdrift.py --node                         # reads process.versions.tz from your Node
python tzdrift.py --node --fail-within 30        # exit 1 if any zone breaks within 30 days
```

As a CI step on every service that formats times, it catches the next rule change before your users do:

```yaml
- run: pip install tzdata && python tzdrift.py --node --fail-within 30
```

It fetches each IANA release from PyPI's `tzdata` package and caches it in `~/.cache/tzdrift`.

## Honest limits

- tzdrift knows what each runtime's database says, not what code does with it. A service that converts in the browser, or caches offsets, can be right or wrong independently.
- "Latest" means the newest release on PyPI when you run it. Governments sometimes announce changes days before they take effect, so a clean run today can go red next month. That is the point of running it in CI.
- Three-hour sampling can miss a transition shorter than three hours. None exist in the current database.

## License

MIT
