# Purchase Order Workflow

## Status Lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT : Create PO
    DRAFT --> SUBMITTED : Officer/Admin submits
    DRAFT --> CANCELLED : Officer/Admin cancels
    SUBMITTED --> APPROVED : Admin approves
    SUBMITTED --> REJECTED : Admin rejects
    SUBMITTED --> CANCELLED : Officer/Admin cancels
    APPROVED --> PARTIALLY_RECEIVED : First GRN approved
    PARTIALLY_RECEIVED --> FULLY_RECEIVED : All items received
    PARTIALLY_RECEIVED --> PARTIALLY_RECEIVED : More GRNs approved
```

## State Transition Rules

| From Status    | Action   | To Status    | Who                   | Rule                                    |
|----------------|----------|--------------|-----------------------|-----------------------------------------|
| DRAFT          | Submit   | SUBMITTED    | Officer / Admin       | PO must have at least one item          |
| DRAFT          | Cancel   | CANCELLED    | Officer / Admin       | Any reason required                     |
| SUBMITTED      | Approve  | APPROVED     | Admin                 | —                                       |
| SUBMITTED      | Reject   | REJECTED     | Admin                 | Rejection reason required               |
| SUBMITTED      | Cancel   | CANCELLED    | Officer / Admin       | Any reason required                     |
| APPROVED       | GRN Approved | PARTIALLY_RECEIVED | System       | Triggered when a GRN is approved        |
| PARTIALLY_RECEIVED | GRN Approved | FULLY_RECEIVED | System    | All ordered quantities received         |

## Business Rules

1. **Only DRAFT POs are editable.** Once submitted, the PO content is locked.
2. **Only SUBMITTED POs can be approved or rejected.**
3. **Only APPROVED or PARTIALLY_RECEIVED POs can have GRNs created against them.**
4. **A PO can be duplicated in any status.** The duplicate is always created as DRAFT.
5. **Only APPROVED (or later) POs can be emailed.** The email goes to the supplier's email address by default, but can be overridden.

## Full Workflow Sequence

```mermaid
sequenceDiagram
    participant Officer
    participant Admin
    participant System
    participant Supplier

    Officer->>System: POST /purchase-orders (DRAFT)
    System-->>Officer: PO created (PO-YYYYMMDD-NNNNN)

    Officer->>System: PATCH /purchase-orders/{id}/submit
    System-->>Officer: PO status → SUBMITTED
    System->>Admin: WebSocket: procurement.po_submitted

    Admin->>System: PATCH /purchase-orders/{id}/approve
    System-->>Admin: PO status → APPROVED
    System->>Officer: WebSocket: procurement.po_approved

    Officer->>System: POST /purchase-orders/{id}/email
    System->>Supplier: Email with HTML PO document
    System-->>Officer: email_sent_at recorded

    Supplier->>Officer: Delivers goods

    Officer->>System: POST /grns (DRAFT, linked to PO)
    System-->>Officer: GRN created (GRN-YYYYMMDD-NNNNN)

    Officer->>System: PATCH /grns/{id}/submit
    System-->>Officer: GRN status → SUBMITTED

    Admin->>System: PATCH /grns/{id}/approve
    System->>System: Post inventory to ledger
    System->>System: Update PO received quantities
    System-->>Admin: GRN status → APPROVED
    System->>Officer: WebSocket: procurement.grn_approved
```

## Email Template

When a PO is emailed, the system generates a professional HTML document containing:

- Supplier information (name, email, contact person)
- PO number and order date
- Itemised table (product, quantity, unit price, discount, tax, line total)
- Financial summary (subtotal, discount, tax, total)
- Optional custom message
- Notes and terms & conditions

The email is sent via SMTP using the existing `EmailService`.

## Duplicate PO

The `POST /purchase-orders/{id}/duplicate` endpoint:

1. Reads all items from the original PO
2. Creates a new DRAFT PO with today's date
3. Copies all line items (product, quantity, price, discount, tax)
4. Assigns a new PO number
5. Returns the new PO

Useful for recurring orders from the same supplier.
