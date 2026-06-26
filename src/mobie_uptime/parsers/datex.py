from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable

from lxml import etree

from ..statuses import normalize_status


@dataclass(frozen=True)
class StaticEvseRecord:
    uid: str
    evse_id: str | None
    site_id: str | None
    station_id: str | None
    operator_id: str | None
    operator_name: str | None
    site_name: str | None
    city: str | None
    postcode: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    max_power_kw: float | None
    connector_count: int | None
    is_24_7: bool | None

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class DynamicStatusRecord:
    uid: str
    status: str
    site_id: str | None = None
    station_id: str | None = None
    source_timestamp: datetime | None = None


def _root(payload: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True)
    return etree.fromstring(payload, parser=parser)


def _direct_children(node: etree._Element, local_name: str) -> list[etree._Element]:
    return node.xpath(f'./*[local-name()="{local_name}"]')


def _descendants(node: etree._Element, local_name: str) -> list[etree._Element]:
    return node.xpath(f'.//*[local-name()="{local_name}"]')


def _first_text(node: etree._Element, paths: Iterable[str]) -> str | None:
    for path in paths:
        value = node.xpath(f"string({path})")
        if value and value.strip():
            return value.strip()
    return None


def _first_float(node: etree._Element, paths: Iterable[str]) -> float | None:
    text = _first_text(node, paths)
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _parse_datetime(text: str | None) -> datetime | None:
    if not text:
        return None
    value = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _xsi_type(node: etree._Element) -> str:
    for key, value in node.attrib.items():
        if key.endswith("}type") or key == "type":
            return value
    return ""


def _name_value(node: etree._Element) -> str | None:
    preferred = node.xpath(
        'string(./*[local-name()="name"]/*[local-name()="values"]/'
        '*[local-name()="value"][@lang="pt-pt" or @lang="pt-PT"])'
    )
    if preferred.strip():
        return preferred.strip()
    return _first_text(
        node,
        [
            './*[local-name()="name"]//*[local-name()="value"][1]',
            './/*[local-name()="name"]//*[local-name()="value"][1]',
        ],
    )


def parse_static(payload: bytes) -> list[StaticEvseRecord]:
    root = _root(payload)
    output: list[StaticEvseRecord] = []

    for site in root.xpath('//*[local-name()="energyInfrastructureSite"]'):
        site_id = site.get("id")
        site_name = _name_value(site)
        city = _first_text(site, ['.//*[local-name()="city"]//*[local-name()="value"][1]'])
        postcode = _first_text(site, ['.//*[local-name()="postcode"][1]'])
        address = _first_text(
            site,
            [
                './/*[local-name()="addressLine"]/*[local-name()="text"]/'
                '*[local-name()="values"]/*[local-name()="value"][1]',
                './/*[local-name()="addressLine"]//*[local-name()="value"][1]',
            ],
        )
        latitude = _first_float(site, ['.//*[local-name()="pointCoordinates"]/*[local-name()="latitude"][1]'])
        longitude = _first_float(site, ['.//*[local-name()="pointCoordinates"]/*[local-name()="longitude"][1]'])

        operator_nodes = _direct_children(site, "operator")
        operator_node = operator_nodes[0] if operator_nodes else None
        operator_id = operator_node.get("id") if operator_node is not None else None
        operator_name = _name_value(operator_node) if operator_node is not None else None

        operating_nodes = _direct_children(site, "operatingHours")
        is_24_7: bool | None = None
        if operating_nodes:
            type_value = _xsi_type(operating_nodes[0]).lower()
            is_24_7 = "openallhours" in type_value

        station_nodes = _direct_children(site, "energyInfrastructureStation")
        if not station_nodes:
            station_nodes = _descendants(site, "energyInfrastructureStation")

        for station in station_nodes:
            station_id = station.get("id") or site_id
            refill_points = _direct_children(station, "refillPoint")
            if not refill_points:
                refill_points = _descendants(station, "refillPoint")

            for refill in refill_points:
                type_value = _xsi_type(refill).lower()
                if type_value and "electricchargingpoint" not in type_value:
                    continue
                uid = (refill.get("id") or "").strip()
                if not uid:
                    continue
                evse_id = _first_text(refill, ['./*[local-name()="externalIdentifier"][1]'])
                connectors = _direct_children(refill, "connector")
                if not connectors:
                    connectors = _descendants(refill, "connector")
                connector_count = len(connectors) or None

                powers: list[float] = []
                refill_power = _first_float(refill, ['./*[local-name()="availableChargingPower"][1]'])
                if refill_power is not None:
                    powers.append(refill_power)
                for connector in connectors:
                    power = _first_float(connector, ['./*[local-name()="maxPowerAtSocket"][1]'])
                    if power is not None:
                        powers.append(power)
                max_power_kw = max(powers) if powers else None

                output.append(
                    StaticEvseRecord(
                        uid=uid,
                        evse_id=evse_id,
                        site_id=site_id,
                        station_id=station_id,
                        operator_id=operator_id,
                        operator_name=operator_name,
                        site_name=site_name,
                        city=city,
                        postcode=postcode,
                        address=address,
                        latitude=latitude,
                        longitude=longitude,
                        max_power_kw=max_power_kw,
                        connector_count=connector_count,
                        is_24_7=is_24_7,
                    )
                )

    return output


def parse_dynamic(payload: bytes) -> list[DynamicStatusRecord]:
    root = _root(payload)
    publication_timestamp = _parse_datetime(
        _first_text(
            root,
            [
                '//*[local-name()="publicationTime"][1]',
                '//*[local-name()="publicationTimestamp"][1]',
                '//*[local-name()="lastUpdated"][1]',
            ],
        )
    )

    output: list[DynamicStatusRecord] = []
    for node in root.xpath('//*[local-name()="refillPointStatus"]'):
        type_value = _xsi_type(node).lower()
        if type_value and "electricchargingpointstatus" not in type_value:
            continue

        uid = _first_text(
            node,
            [
                './*[local-name()="reference"][@targetClass="FacilityObject"]/@id',
                './*[local-name()="reference"]/@id',
                './/*[local-name()="reference"][@targetClass="FacilityObject"][1]/@id',
            ],
        )
        raw_status = _first_text(node, ['./*[local-name()="status"][1]', './/*[local-name()="status"][1]'])
        if not uid or not raw_status:
            continue

        station_id = _first_text(
            node,
            [
                '../*[local-name()="reference"][@targetClass="FacilityObject"]/@id',
                '../*[local-name()="reference"]/@id',
            ],
        )
        site_id = _first_text(
            node,
            [
                '../../*[local-name()="reference"][@targetClass="FacilityObject"]/@id',
                '../../*[local-name()="reference"]/@id',
            ],
        )
        output.append(
            DynamicStatusRecord(
                uid=uid,
                status=normalize_status(raw_status),
                site_id=site_id,
                station_id=station_id,
                source_timestamp=publication_timestamp,
            )
        )

    return output
