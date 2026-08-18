"""D1-7 - register the repaired price source and its B-21 provenance.

Produces the `PriceSourceContract` the retrospective adapter checks, so the route
can verify the source rather than a closure document quoting a hash at it.

Identity is the COMPOSED canonical source:
    <= 2018  existing yearly export
    >= 2019  the 20260817 re-export
fingerprinted the same way the contaminated corpus was, so the two are directly
comparable and the new one is demonstrably a different artefact.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_price_universe import (            # noqa: E402
    CONTAMINATED_CORPUS_SHA256, PriceSourceContract,
    assert_price_source_admissible, quarantined_sources,
)
from core.b0_provenance import file_sha256      # noqa: E402
from rebuild_audit_new_source import coverage   # noqa: E402

OUT = os.path.join(HERE, "price_source_contract.json")
AUDIT_CSV = os.path.join(REPO, "data", "b0", "price_universe_audit.csv")
CLUSTER_CSV = os.path.join(REPO, "data", "b0", "price_universe_clusters.csv")
NEW_EXPORT_DIR = os.path.join(REPO, "tej_exports", "DataExport0806",
                              "個股股價、本益比2004-20260817")

SCHEMA_2019PLUS = (
    "證券代碼", "年月日", "開盤價(元)", "最高價(元)", "最低價(元)", "收盤價(元)",
    "成交量(千股)", "成交值(千元)", "流通在外股數(千股)", "本益比-TEJ", "股價淨值比-TEJ",
)


def main():
    years, first, last = coverage("new")
    manifest = "\n".join(sorted(
        f"{s}:{first[s]}:{last[s]}:{len(years[s])}" for s in first))
    content_sha = hashlib.sha256(manifest.encode("utf-8")).hexdigest()

    audit_sha = file_sha256(AUDIT_CSV)
    inventory = json.load(open(
        os.path.join(HERE, "new_export_inventory.json"), encoding="utf-8"))

    contract = PriceSourceContract(
        name="b0_price_universe_20260817",
        importer_version="b0_price_importer@2",
        content_sha256=content_sha,
        schema_sha256=hashlib.sha256(
            "|".join(SCHEMA_2019PLUS).encode("utf-8")).hexdigest(),
        date_min=min(first.values()),
        date_max=max(last.values()),
        securities=len(first),
        includes_delisted=True,       # verified by the audit, not asserted
        audit_sha256=audit_sha,
        lineage=("<=2018 existing yearly export; >=2019 "
                 "tej_exports/DataExport0806/個股股價、本益比2004-20260817 "
                 "(股價 2019-2022.zip, 股價2023-20260817.zip)"),
    )
    assert_price_source_admissible(contract)

    payload = {
        "study": "D1-7 price source contract",
        "read_only": True, "performance_computed": False,
        "contract": contract.__dict__,
        "b21_dataset_provenance": contract.to_dataset_provenance().__dict__,
        "upstream_zips": {m["zip"]: m["zip_sha256"] for m in inventory["members"]},
        "upstream_zip_bytes": {m["zip"]: m["zip_bytes"] for m in inventory["members"]},
        "derived_artifacts": {
            "price_universe_audit.csv": audit_sha,
            "price_universe_clusters.csv": file_sha256(CLUSTER_CSV),
            "price_2019plus_new.parquet": file_sha256(
                os.path.join(REPO, "data", "b0", "price_2019plus_new.parquet")),
        },
        "differs_from_quarantined_corpus": content_sha != CONTAMINATED_CORPUS_SHA256,
        "quarantined": list(quarantined_sources()),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print("name           :", contract.name)
    print("securities     :", contract.securities)
    print("coverage       :", contract.date_min, "..", contract.date_max)
    print("content_sha256 :", contract.content_sha256)
    print("  quarantined  :", contract.content_sha256)
    print("  differs from :", CONTAMINATED_CORPUS_SHA256)
    print("  -> different :", payload["differs_from_quarantined_corpus"])
    print("schema_sha256  :", contract.schema_sha256)
    print("audit_sha256   :", contract.audit_sha256)
    print("admissible     : yes")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
