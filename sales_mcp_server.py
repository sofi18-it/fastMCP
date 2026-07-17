import csv
import os
import sys
from pathlib import Path

from fastmcp import FastMCP

from starlette.requests import Request
from starlette.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
mcp = FastMCP("SalesAnalyticsMCP")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "sales-analytics-mcp"})


def safe_csv_path(file_name: str) -> Path:
    if not file_name or Path(file_name).is_absolute():
        raise ValueError("file_name must be a relative CSV file name")

    candidate = (BASE_DIR / file_name).resolve()
    if BASE_DIR not in candidate.parents and candidate != BASE_DIR:
        raise ValueError("file_name must stay inside the demo directory")

    if not candidate.exists():
        raise FileNotFoundError(f"CSV file not found")

    return candidate

@mcp.tool
def load_sales_summary(file_name: str = "sales_data.csv") -> dict[str, object]:
    orders = 0
    revenue = 0.0
    gross_profit = 0.0

    with safe_csv_path(file_name).open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        required_columns = {"quantity", "unit_price", "cost_per_unit"}
        missing_columns = required_columns.difference(reader.fieldnames or [])

        if missing_columns:
            raise ValueError(f"Missing CSV columns {sorted(missing_columns)}")

        for row in reader:
            quantity = int(row['quantity'])
            unit_price = float(row['unit_price'])
            cost_per_unit = float(row['cost_per_unit'])
            orders += 1
            revenue += quantity * unit_price
            gross_profit += quantity * (unit_price - cost_per_unit)

        if not orders:
            return {"file": file_name, "orders": 0, "message": "CSV file is empty"}

        return {
            "file": file_name,
            "orders": orders,
            "revenue_uah": round(revenue, 2),
            "gross_profit_uah": round(gross_profit, 2),
            "gross_margin_pct": round(gross_profit / revenue * 100, 2) if revenue else 0
        }

@mcp.tool
def sales_by_region(file_name: str = "sales_data.csv") -> dict[str, object]:
    with safe_csv_path(file_name).open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        required_columns = {
            "region",
            "quantity",
            "unit_price",
            "cost_per_unit",
        }

        missing_columns = required_columns.difference(reader.fieldnames or [])

        if missing_columns:
            raise ValueError(f"Missing CSV columns {sorted(missing_columns)}")

        regions = {}

        for row in reader:
            region = row["region"]
            quantity = int(row["quantity"])
            unit_price = float(row["unit_price"])
            cost_per_unit = float(row["cost_per_unit"])

            revenue = quantity * unit_price
            gross_profit = quantity * (unit_price - cost_per_unit)

            if region not in regions:
                regions[region] = {
                    "region": region,
                    "orders": 0,
                    "revenue_uah": 0.0,
                    "gross_profit_uah": 0.0,
                }

            regions[region]["orders"] += 1
            regions[region]["revenue_uah"] += revenue
            regions[region]["gross_profit_uah"] += gross_profit

    result = sorted(
        regions.values(),
        key=lambda item: item["revenue_uah"],
        reverse=True,
    )

    for item in result:
        item["revenue_uah"] = round(item["revenue_uah"], 2)
        item["gross_profit_uah"] = round(item["gross_profit_uah"], 2)

    return {
        "file": file_name,
        "regions": result,
    }

@mcp.resource("sales://metrics-definitions")
def metric_definitions_resource() -> str:
    return """\
Визначення метрик продажів:

- revenue_uah — виручка в гривнях: quantity × unit_price.
- gross_profit_uah — валовий прибуток у гривнях: quantity × (unit_price - cost_per_unit).
- gross_margin_pct — валова маржа у відсотках: gross_profit / revenue × 100.
- average_order_value_uah — середня вартість одного замовлення: revenue / orders.
- units_sold — загальна кількість проданих одиниць.
- revenue_by_region_uah — виручка, згрупована за регіонами.
- revenue_by_channel_uah — виручка, згрупована за каналами продажу.
"""

@mcp.prompt
def sales_report_prompt(company_context: str = "B2B SaaS компанія") -> str:
    return f"""\
Ви - AI sales analyst для компанії: {company_context}.

Підготуйте короткий Markdown-звіт українською мовою:
1. Стислий executive summary на 2-3 речення.
2. Основні метрики: revenue, gross profit, margin, average order value.
3. Найсильніші регіони та канали.
4. 2-3 практичні бізнес-рекомендації.

Використовуйте тільки факти, отримані з MCP tools або resources.
Не вигадуйте замовлення, продукти, суми або тренди.
""".strip()


def main() -> None:
    if should_run_http():
        mcp.run(
            transport="http",
            host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "8000")),
            stateless_http=True
        )
    else:
        mcp.run()


def should_run_http() -> bool:
    transport = os.environ.get("MCP_TRANSPORT", "").lower()
    return "--http" in sys.argv or transport in {"http", "streamable-http"} or "PORT" in os.environ


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
