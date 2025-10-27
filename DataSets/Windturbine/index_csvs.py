#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Indexeer 4 CSV-bestanden (Location1..4.csv) naar 4 aparte OpenSearch-indices.
- Indices: wind-turbine-location1 .. wind-turbine-location4
- Bulk indexatie in batches
- .env wordt automatisch omhoog gezocht (buiten de Windturbine map)
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from typing import Dict, Iterable, Generator

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import NotFoundError

# =========================
# .env laden (omhoog zoeken)
# =========================
def load_env_upwards() -> None:
    """
    Zoekt .env in huidige map en alle bovenliggende mappen en laadt deze.
    Compatibel met python-dotenv maar zonder harde afhankelijkheid.
    """
    try:
        from dotenv import load_dotenv
    except Exception:
        # Geen python-dotenv? Dan proberen we OS env alleen.
        return

    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents):
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(dotenv_path=str(candidate))
            return


# =========================
# OpenSearch client
# =========================
def make_client() -> OpenSearch:
    """
    Maakt een OpenSearch client op basis van env vars.
    Vereiste env variabelen (met default fallbacks):
      OS_HOST=localhost
      OS_PORT=9200
      OS_USER=admin
      OS_PASSWORD=admin
      OS_SCHEME=https  (of http)
      OS_VERIFY_CERTS=false  (true/false)
    """
    host = os.getenv("OS_HOST", "localhost")
    port = int(os.getenv("OS_PORT", "9200"))
    user = os.getenv("OS_USER", "admin")
    password = os.getenv("OS_PASSWORD", "admin")
    scheme = os.getenv("OS_SCHEME", "https")
    verify = os.getenv("OS_VERIFY_CERTS", "false").lower() == "true"

    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(user, password),
        use_ssl=(scheme == "https"),
        verify_certs=verify,
        ssl_assert_hostname=False if not verify else True,
        ssl_show_warn=not verify,
        scheme=scheme,
        timeout=120,
        max_retries=5,
        retry_on_timeout=True,
    )
    return client


# =========================
# Index aanmaken (mapping)
# =========================
def ensure_index(os_client: OpenSearch, index_name: str) -> None:
    """
    Maakt index aan met veilige mapping.
    Let op: GEEN dynamic_date_formats met epoch_millis op index-niveau.
    In plaats daarvan gebruiken we dynamic_templates met per veld 'format'.
    """
    exists = os_client.indices.exists(index=index_name)
    if exists:
        return

    body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 1
            }
        },
        "mappings": {
            "dynamic": True,
            # Gebruik templates om veelvoorkomende datumkolommen correct te parsen
            "dynamic_templates": [
                # Probeer algemene datum/tijd namen
                {
                    "dt_timestamp": {
                        "match": "*timestamp*",
                        "mapping": {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
                    }
                },
                {
                    "dt_datetime": {
                        "match": "*date*time*",
                        "mapping": {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
                    }
                },
                {
                    "dt_date": {
                        "match": "*date*",
                        "mapping": {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
                    }
                },
                {
                    "dt_time": {
                        "match": "*time*",
                        "mapping": {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
                    }
                },
                # Laat strings standaard als keyword binnenkomen (voorkomt onbedoelde full-text analyse)
                {
                    "strings_as_keyword": {
                        "match_mapping_type": "string",
                        "mapping": {"type": "keyword", "ignore_above": 256}
                    }
                }
            ]
        }
    }

    os_client.indices.create(index=index_name, body=body)


# =========================
# Data helpers
# =========================
def row_to_doc(row: Dict[str, str]) -> Dict:
    """
    Eventuele lichte normalisatie. Laat waardes zoals ze zijn;
    mapping/templates zorgen voor types. Trim whitespace.
    """
    doc = {}
    for k, v in row.items():
        if v is None:
            doc[k] = None
        else:
            vv = v.strip()
            # Converteer lege strings naar None
            doc[k] = vv if vv != "" else None
    return doc


def gen_actions(
    csv_path: Path, index_name: str, id_field: str = None
) -> Generator[Dict, None, None]:
    """
    Generator met bulk-acties voor een CSV-bestand.
    """
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            doc = row_to_doc(row)
            action = {
                "_op_type": "index",
                "_index": index_name,
                "_source": doc,
            }
            if id_field and id_field in doc and doc[id_field]:
                action["_id"] = str(doc[id_field])
            yield action


# =========================
# Bulk indexeren
# =========================
def bulk_index_file(
    os_client: OpenSearch,
    location_num: int,
    data_dir: Path,
    chunk_size: int = 2000,
    id_field: str = None,
) -> None:
    """
    Indexeer één CSV-bestand naar de bijhorende index.
    Bestandsnaam: Location{n}.csv
    Indexnaam: wind-turbine-location{n}
    """
    csv_file = data_dir / f"Location{location_num}.csv"
    if not csv_file.exists():
        raise FileNotFoundError(f"Bestand niet gevonden: {csv_file.name}")

    index_name = f"wind-turbine-location{location_num}"
    ensure_index(os_client, index_name)

    print(f"[Loc{location_num}] Start bulk => {csv_file.name} → {index_name} (chunk={chunk_size})")

    # Bulk helper
    successes = 0
    errors = []
    try:
        for ok, info in helpers.streaming_bulk(
            client=os_client,
            actions=gen_actions(csv_file, index_name, id_field=id_field),
            chunk_size=chunk_size,
            max_retries=5,
            raise_on_error=False,
            request_timeout=120,
        ):
            if ok:
                successes += 1
            else:
                errors.append(info)
    except Exception as e:
        print(f"[Loc{location_num}] Fout tijdens bulk: {e}")
        raise

    print(f"[Loc{location_num}] Klaar: {successes} acties geslaagd, {len(errors)} fouten")
    if errors:
        # Toon alleen de eerste paar om log te beperken
        preview = errors[:5]
        print(f"[Loc{location_num}] Voorbeeld fouten (eerste {len(preview)}):")
        for idx, err in enumerate(preview, start=1):
            print(f"  {idx}. {err}")


# =========================
# Main
# =========================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Indexeer 4 Windturbine CSV's naar OpenSearch")
    p.add_argument(
        "--data-dir",
        type=str,
        default=".",
        help="Pad naar de map met Location1..4.csv (default: current dir)",
    )
    p.add_argument(
        "--first",
        type=int,
        default=1,
        help="Eerste locatie nummer (default: 1)",
    )
    p.add_argument(
        "--last",
        type=int,
        default=4,
        help="Laatste locatie nummer (default: 4)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=2000,
        help="Bulk chunk grootte (default: 2000)",
    )
    p.add_argument(
        "--id-field",
        type=str,
        default=None,
        help="Optioneel: kolomnaam die als document _id gebruikt wordt",
    )
    return p.parse_args()


def main() -> None:
    load_env_upwards()
    args = parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        print(f"Fout: data map bestaat niet: {data_dir}")
        sys.exit(1)

    # Client
    try:
        os_client = make_client()
        # eenvoudige ping
        if not os_client.ping():
            print("Waarschuwing: OpenSearch ping faalt, ga toch door met poging tot indexeren…")
    except Exception as e:
        print(f"Kon geen OpenSearch client maken: {e}")
        sys.exit(1)

    # Loop over locaties
    for n in range(args.first, args.last + 1):
        try:
            bulk_index_file(
                os_client=os_client,
                location_num=n,
                data_dir=data_dir,
                chunk_size=args.chunk_size,
                id_field=args.id_field,
            )
        except FileNotFoundError as fnf:
            print(f"Fout bij locatie {n}: {fnf}")
        except Exception as e:
            print(f"OpenSearch-fout bij locatie {n}: {e}")
            # niet meteen stoppen; ga door met volgende
            continue

    # Optioneel: aantallen tonen
    try:
        for n in range(args.first, args.last + 1):
            idx = f"wind-turbine-location{n}"
            try:
                cnt = os_client.count(index=idx).get("count", 0)
                print(f"[{idx}] documenten: {cnt}")
            except NotFoundError:
                print(f"[{idx}] bestaat niet.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
