# Procurement Module — Phase 3

## Overview

The procurement module implements a complete purchase-to-receive workflow for a single-store inventory system. It covers Purchase Order creation and approval, Goods Received Notes (GRNs), automatic inventory posting, and an immutable inventory ledger.

## Architecture

```
POST /purchase-orders  →  PurchaseOrderService  →  PurchaseOrderRepository
PATCH /{id}/approve    →  GRNService             →  GRNRepository
PATCH /grns/{id}/approve → InventoryLedgerService → InventoryLedgerRepository
                                                  → InventoryLedger (append-only)
```

## Database Tables

| Table                  | Description                                         |
|------------------------|-----------------------------------------------------|
| `purchase_orders`      | PO header: supplier, status, totals, workflow dates |
| `purchase_order_items` | PO line items: product, qty, price, discount, tax   |
| `grns`                 | GRN header: linked PO, received date, workflow      |
| `grn_items`            | GRN line items: po_item link, qty received, cost    |
| `inventory_ledger`     | Immutable stock movement ledger                     |

All tables use UUID primary keys and `TimestampMixin` (created_at, updated_at). Purchase orders also have soft-delete (`is_deleted`, `deleted_at`).

## API Endpoints

### Purchase Orders

| Method | Path                              | Permission           | Description                        |
|--------|-----------------------------------|----------------------|------------------------------------|
| GET    | `/api/v1/purchase-orders/`        | Authenticated        | List POs (paginated, filterable)   |
| POST   | `/api/v1/purchase-orders/`        | `procurement:write`  | Create DRAFT PO                    |
| GET    | `/api/v1/purchase-orders/{id}`    | Authenticated        | Get PO details                     |
| PUT    | `/api/v1/purchase-orders/{id}`    | `procurement:write`  | Update DRAFT PO                    |
| DELETE | `/api/v1/purchase-orders/{id}`    | `procurement:write`  | Soft delete DRAFT PO               |
| PATCH  | `/api/v1/purchase-orders/{id}/submit`  | `procurement:write`  | Submit for approval           |
| PATCH  | `/api/v1/purchase-orders/{id}/approve` | `procurement:approve`| Approve submitted PO          |
| PATCH  | `/api/v1/purchase-orders/{id}/reject`  | `procurement:approve`| Reject submitted PO           |
| PATCH  | `/api/v1/purchase-orders/{id}/cancel`  | `procurement:write`  | Cancel DRAFT/SUBMITTED PO     |
| POST   | `/api/v1/purchase-orders/{id}/duplicate` | `procurement:write` | Duplicate as new DRAFT       |
| GET    | `/api/v1/purchase-orders/{id}/print`   | Authenticated        | Get print-ready JSON data     |
| POST   | `/api/v1/purchase-orders/{id}/email`   | `procurement:write`  | Email PO to supplier          |

### GRNs

| Method | Path                        | Permission            | Description                    |
|--------|-----------------------------|-----------------------|--------------------------------|
| GET    | `/api/v1/grns/`             | Authenticated         | List GRNs (paginated)          |
| POST   | `/api/v1/grns/`             | `procurement:write`   | Create DRAFT GRN               |
| GET    | `/api/v1/grns/{id}`         | Authenticated         | Get GRN details                |
| PUT    | `/api/v1/grns/{id}`         | `procurement:write`   | Update DRAFT GRN               |
| PATCH  | `/api/v1/grns/{id}/submit`  | `procurement:write`   | Submit GRN for approval        |
| PATCH  | `/api/v1/grns/{id}/approve` | `procurement:approve` | Approve GRN (posts inventory)  |
| PATCH  | `/api/v1/grns/{id}/cancel`  | `procurement:write`   | Cancel DRAFT/SUBMITTED GRN     |

### Procurement Reports & Dashboard

| Method | Path                                            | Permission          | Description                     |
|--------|-------------------------------------------------|---------------------|---------------------------------|
| GET    | `/api/v1/procurement/reports/purchase-orders`   | `reports:export`    | Export PO report (Excel)        |
| GET    | `/api/v1/procurement/reports/grns`              | `reports:export`    | Export GRN report (Excel)       |
| GET    | `/api/v1/procurement/reports/supplier-purchases`| `reports:export`    | Export supplier purchase report |
| GET    | `/api/v1/procurement/dashboard`                 | Authenticated       | Procurement summary dashboard   |

## Permissions

| Permission           | Granted To                    |
|----------------------|-------------------------------|
| `procurement:read`   | ADMIN, OFFICER, STORE_KEEPER  |
| `procurement:write`  | ADMIN, OFFICER                |
| `procurement:approve`| ADMIN only                    |

## PO Number & GRN Number Format

- PO numbers: `PO-YYYYMMDD-NNNNN` (e.g. `PO-20260723-00001`)
- GRN numbers: `GRN-YYYYMMDD-NNNNN` (e.g. `GRN-20260723-00001`)

Numbers are unique and generated automatically on creation.

## Totals Calculation

For each PO item:
```
base       = quantity_ordered × unit_price
discount   = base × (discount_percent / 100)
net        = base - discount
tax        = net × (tax_percent / 100)
line_total = net + tax
```

PO totals are the sum across all items:
- `subtotal = sum(quantity × unit_price)`
- `discount_amount = sum(discounts)`
- `tax_amount = sum(taxes)`
- `total_amount = subtotal - discount_amount + tax_amount`

## Real-time Notifications

WebSocket events are broadcast on every major workflow transition:

| Event                         | Trigger                        |
|-------------------------------|--------------------------------|
| `procurement.po_created`      | PO created                     |
| `procurement.po_submitted`    | PO submitted for approval      |
| `procurement.po_approved`     | PO approved                    |
| `procurement.po_rejected`     | PO rejected                    |
| `procurement.po_cancelled`    | PO cancelled                   |
| `procurement.po_emailed`      | PO emailed to supplier         |
| `procurement.grn_created`     | GRN created                    |
| `procurement.grn_approved`    | GRN approved (inventory posted)|
| `procurement.grn_cancelled`   | GRN cancelled                  |

Events follow the `WebSocketEvent` schema: `{event, payload, room, sender}`.

## Inventory Ledger

The `inventory_ledger` table is append-only. Every approved GRN adds a `PURCHASE_RECEIPT` entry:

```json
{
  "product_id": "...",
  "entry_type": "PURCHASE_RECEIPT",
  "quantity_before": 0.0,
  "quantity_change": 10.0,
  "quantity_after": 10.0,
  "unit_cost": 95.00,
  "grn_id": "...",
  "reference_number": "GRN-20260723-00001"
}
```

Current stock for a product is always the most recent `quantity_after` value.
