from pathlib import Path

from mobie_uptime.parsers.datex import parse_dynamic, parse_static

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_static() -> None:
    records = parse_static((FIXTURES / "static_sample.xml").read_bytes())
    assert len(records) == 1
    record = records[0]
    assert record.uid == "EVSE-001"
    assert record.evse_id == "PT*OP1*E0001*1"
    assert record.operator_name == "Operador Um"
    assert record.city == "Lisboa"
    assert record.is_24_7 is True
    assert record.max_power_kw == 50


def test_parse_dynamic() -> None:
    records = parse_dynamic((FIXTURES / "dynamic_sample_2.xml").read_bytes())
    assert len(records) == 1
    assert records[0].uid == "EVSE-001"
    assert records[0].status == "OUTOFORDER"
    assert records[0].site_id == "SITE-001"
    assert records[0].station_id == "STATION-001"
