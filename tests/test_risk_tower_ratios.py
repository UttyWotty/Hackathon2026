"""
Tests for the Risk Tower tool's fleet-relative outlier detection.

The underlying analysis only compares MTTR and MTBF against peers when
stability is already below 70, so machines with good stability but abnormal
repair or stop behaviour are reported Stable. These pure helpers restore that
comparison. No I/O, no dataset on disk.
"""

from services.config.features.analytics.tools.risk_tower_tools import (
    _add_fleet_ratios,
    _fleet_average,
    _summarize,
)


def _row(code, mttr, mtbf, declining=False):
    return {
        "equipment_code": code,
        "mttr_minutes": mttr,
        "mtbf_minutes": mtbf,
        "is_declining": declining,
        "rag_status": "Green",
    }


# One machine with long repairs, one with frequent stops, three healthy peers.
FLEET = [
    _row("EMA-4101", 2.0, 25.0),
    _row("EMA-4102", 2.0, 25.0),
    _row("EMA-4103", 2.0, 25.0),
    _row("EMA-4104", 2.0, 8.0),
    _row("EMA-4105", 12.0, 25.0),
]


class TestFleetAverage:
    def test_excludes_the_machine_under_test(self):
        # Leave-one-out: a machine must not be judged against an average it is
        # itself dragging. This is how the dataset contract defines it.
        rows = [_row("A", 10.0, 1.0), _row("B", 2.0, 1.0), _row("C", 2.0, 1.0)]
        assert _fleet_average(rows, "mttr_minutes", exclude="A") == 2.0

    def test_without_exclusion_the_outlier_skews_it(self):
        rows = [_row("A", 10.0, 1.0), _row("B", 2.0, 1.0), _row("C", 2.0, 1.0)]
        assert _fleet_average(rows, "mttr_minutes") > 4.0

    def test_zero_and_missing_values_are_skipped(self):
        rows = [_row("A", 0, 1.0), _row("B", 4.0, 1.0), {"equipment_code": "C"}]
        assert _fleet_average(rows, "mttr_minutes") == 4.0

    def test_no_usable_values_returns_zero(self):
        assert _fleet_average([{"equipment_code": "A"}], "mttr_minutes") == 0.0


class TestFleetRatios:
    def test_long_repairs_are_flagged(self):
        rows = _add_fleet_ratios([dict(r) for r in FLEET])
        target = next(r for r in rows if r["equipment_code"] == "EMA-4105")
        assert target["high_mttr"] is True
        assert target["mttr_vs_peers"] > 1.2

    def test_frequent_stops_are_flagged(self):
        rows = _add_fleet_ratios([dict(r) for r in FLEET])
        target = next(r for r in rows if r["equipment_code"] == "EMA-4104")
        assert target["frequent_stops"] is True
        assert target["mtbf_vs_peers"] < 0.8

    def test_healthy_peers_are_not_flagged(self):
        rows = _add_fleet_ratios([dict(r) for r in FLEET])
        healthy = [r for r in rows if r["equipment_code"] in ("EMA-4101", "EMA-4102")]
        assert not any(r["high_mttr"] or r["frequent_stops"] for r in healthy)

    def test_a_uniform_fleet_flags_nobody(self):
        # Guards against a detector that always finds something.
        rows = _add_fleet_ratios([_row(f"EMA-410{i}", 3.0, 20.0) for i in range(5)])
        assert not any(r["high_mttr"] or r["frequent_stops"] for r in rows)

    def test_zero_mtbf_is_not_read_as_frequent_stops(self):
        # A machine with no recorded stops has MTBF 0; that is absence of data,
        # not perfect reliability, and must not be flagged as stopping often.
        rows = _add_fleet_ratios([_row("A", 3.0, 0.0)] + [dict(r) for r in FLEET])
        target = next(r for r in rows if r["equipment_code"] == "A")
        assert target["frequent_stops"] is False


class TestSummary:
    def test_summary_lists_each_outlier_group(self):
        summary = _summarize(_add_fleet_ratios([dict(r) for r in FLEET]))
        assert summary["high_mttr_equipment"] == ["EMA-4105"]
        assert summary["frequent_stops_equipment"] == ["EMA-4104"]
        assert summary["total_equipment"] == len(FLEET)

    def test_declining_is_listed_separately(self):
        rows = [dict(r) for r in FLEET]
        rows[0]["is_declining"] = True
        summary = _summarize(_add_fleet_ratios(rows))
        assert summary["declining_equipment"] == ["EMA-4101"]
