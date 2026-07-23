# Inventory Ledger

## Overview

The inventory ledger (`inventory_ledger_entries`) is the single source of truth for all stock movements in SIMS Lite. Every change to inventory — whether from a GRN receipt, a stock adjustment, or a stock release — appends a new row to this table.

The core principle is **immutability**: ledger records are never updated or deleted after creation. This ensures a complete, tamper-proof audit trail of every quantity and cost change across the system's lifetime.

## Invariant

Every ledger entry satisfies the following invariant:

```
quantity_before + quantity_change = quantity_after
```

This holds for both increases (positive `quantity_change`) and decreases (negative `quantity_change`). The `inventory` table's `quantity_on_hand` always mirrors the most recent `quantity_after` for that product.

## Reference Types

Each ledger entry links back to the source document that caused the movement via `reference_type` and `reference_id`.

| Reference Type | Source Document | Description |
|---|---|---|
| `GRN` | Goods Received Note | Stock received from a supplier on an approved GRN |
| `STOCK_ADJUSTMENT` | Stock Adjustment | Manual correction via an approved Stock Adjustment |
| `STOCK_RELEASE` | Stock Release | Stock issued or consumed via an approved Stock Release |
| `INITIAL` | Initial setup | Opening balance entry during system setup |

## API Reference

The ledger is read-only — there are no create, update, or delete endpoints.

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/v1/inventory-ledger/` | `inventory:read` | Paginated list of all ledger entries |
| `GET` | `/api/v1/inventory-ledger/{id}` | `inventory:read` | Single entry by ID |
| `GET` | `/api/v1/inventory-ledger/product/{product_id}` | `inventory:read` | Full ledger history for a specific product |
| `GET` | `/api/v1/inventory-ledger/reference/{ref_type}/{ref_id}` | `inventory:read` | All entries created by a specific source document |

## Filtering

The list endpoint (`GET /api/v1/inventory-ledger/`) accepts the following query parameters:

| Parameter | Type | Description |
|---|---|---|
| `page` | integer | Page number (default: 1) |
| `size` | integer | Page size, max 200 (default: 50) |
| `product_id` | UUID | Filter by product |
| `entry_type` | string | Filter by entry type (e.g. `PURCHASE_RECEIPT`) |
| `reference_type` | string | Filter by reference type (e.g. `GRN`) |
| `from_date` | datetime | Include only entries created on or after this date |
| `to_date` | datetime | Include only entries created on or before this date |

## How a GRN Approval Creates a Ledger Entry

```mermaid
sequenceDiagram
    participant User
    participant GRN API
    participant Inventory Service
    participant DB: inventory
    participant DB: inventory_ledger_entries

    User->>GRN API: PATCH /grns/{id}/approve
    GRN API->>Inventory Service: apply_grn_receipt()
    Inventory Service->>DB: inventory: UPDATE quantity_on_hand
    Inventory Service->>DB: inventory_ledger_entries: INSERT (immutable)
    Inventory Service-->>GRN API: LedgerEntry
    GRN API-->>User: GRN approved
```

The same pattern applies to stock adjustments and stock releases — the approval endpoint calls into `InventoryService` or `StockAdjustmentService`, which calls `_apply_inventory_change()`. That function atomically updates the `inventory` row and appends a new `inventory_ledger_entries` row in a single database flush.
