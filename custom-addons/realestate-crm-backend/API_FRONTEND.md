# Real Estate CRM — HTTP JSON API (frontend integration)

Base path prefix: **`/api/real-estate/`** (relative to your Odoo origin, e.g. `https://your-domain.com`).

All successful responses use JSON with a top-level **`success: true`** where noted. Errors return JSON with **`error`** (string) and an appropriate HTTP status.

---

## 1. Authentication and session (required for almost all routes)

### `POST /api/real-estate/auth`

| | |
|---|---|
| **Auth** | `none` (no session required) |
| **CSRF** | Disabled (`csrf=False`) |
| **Content-Type** | `application/json` |

**Body (required fields)**

| Field | Type | Required |
|--------|------|----------|
| `username` | string | Yes |
| `password` | string | Yes |

**Example**

```json
{ "username": "sales@example.com", "password": "your-password" }
```

**Success (200)** — Odoo sets the **session cookie** on the response. The frontend must send this cookie on every following request (`credentials: 'include'` in `fetch`, or `withCredentials: true` in Axios).

```json
{
  "success": true,
  "user_id": 2,
  "username": "sales@example.com",
  "name": "Sales User",
  "email": "sales@example.com",
  "company_id": 1,
  "company_name": "My Company"
}
```

**Errors:** `400` missing credentials, `401` invalid login, `500` server error.

---

## 2. Recommended frontend flow (high level)

1. **`POST /api/real-estate/auth`** with username/password → store session (cookie).
2. **`GET /api/real-estate/projects`** and/or **`GET /api/real-estate/units`** for catalog and maps.
3. **`GET /api/real-estate/opportunities`** — list opportunities assigned to the logged-in user.
4. For installments on an opportunity:
   - **`GET /api/real-estate/installment-templates`** (optionally with `project_id` / `sector_id` from the opportunity) to fill a template picker.
   - **`POST .../installments/regenerate`** after the user picks a template (and opportunity has a **unit** in Odoo).
   - **`GET .../installments`** to display the schedule.

**Important:** Installment **GET/POST** routes only work if the CRM opportunity’s **Salesperson** (`user_id`) is the **same user** as the one logged in via the API. Otherwise you get **`403 Forbidden`**.

**Prerequisites to regenerate installments** (same rules as Odoo “Generate schedule”):

- Record must be an **opportunity** (not a lead).
- **`unit_id`** must be set on the opportunity (and unit price / base amount rules apply in the backend).
- **`installment_system_id`** must be set (either already on the opportunity or sent in the regenerate body).

---

## 3. Endpoint reference

Unless stated otherwise: **`auth: user`**, send session cookie, **`Content-Type: application/json`** for POST bodies.

### Projects

| Method | Path | Body / query | Notes |
|--------|------|----------------|------|
| **GET** | `/api/real-estate/projects` | — | Active projects list. |

---

### Units

| Method | Path | Query parameters | Notes |
|--------|------|------------------|------|
| **GET** | `/api/real-estate/units` | `project_id` (optional), `status` (optional) | Filters active units. Example: `/api/real-estate/units?project_id=3` |

No body.

---

### Opportunities

| Method | Path | Body / query | Notes |
|--------|------|----------------|------|
| **GET** | `/api/real-estate/opportunities` | — | Only opportunities with `user_id = current user`. |
| **POST** | `/api/real-estate/opportunities` | JSON (see below) | `csrf=False`. |

**`POST /api/real-estate/opportunities` — body fields**

| Field | Type | Required | Default / notes |
|--------|------|----------|------------------|
| `name` | string | **Yes** (for a sensible record) | Opportunity title |
| `type` | string | No | Default **`"opportunity"`** so the record appears in `GET /opportunities` and installment APIs. Use `"lead"` only if you intentionally want a lead. |
| `partner_id` | integer | Recommended | Customer `res.partner` id |
| `project_id` | integer | No | |
| `sector_id` | integer | No | Phase / sector |
| `building_id` | integer | No | |
| `unit_id` | integer | No | |
| `property_type` | string | No | Default `"residential"` |
| `expected_revenue` | number | No | |
| `probability` | number | No | Default `10` |
| `agent_latitude` | number | No | |
| `agent_longitude` | number | No | |

`user_id` is forced server-side to the current user.

---

### Activities

| Method | Path | Body / query |
|--------|------|----------------|
| **GET** | `/api/real-estate/activities` | — |
| **POST** | `/api/real-estate/activities` | JSON (see below), `csrf=False` |
| **POST** | `/api/real-estate/activities/<activity_id>/complete` | JSON (optional fields), `csrf=False` |

**`POST /api/real-estate/activities` — body fields**

| Field | Type | Required | Notes |
|--------|------|----------|--------|
| `summary` | string | **Yes** for a normal activity | |
| `res_model` | string | **Yes** | e.g. `"crm.lead"` |
| `res_id` | integer | **Yes** | Record id |
| `date_deadline` | string (date) | No | e.g. `"2026-05-15"` |
| `activity_type_id` | integer | No | Preferred if known |
| `activity_type_name` or `activity_type` | string | No | Resolved to first matching `mail.activity.type` by name |
| `agent_latitude` / `agent_longitude` | number | No | |

**`POST .../activities/<id>/complete` — body (optional)**

| Field | Type | Notes |
|--------|------|--------|
| `completion_latitude` | number | Both lat/long written if both truthy |
| `completion_longitude` | number | |

---

### Contacts

| Method | Path | Notes |
|--------|------|--------|
| **GET** | `/api/real-estate/contacts/<contact_id>/phone` | Partner phone / mobile / email |

---

### Unit WhatsApp

| Method | Path | Notes |
|--------|------|--------|
| **GET** | `/api/real-estate/units/<unit_id>/whatsapp` | Returns `whatsapp_url` and `message` text |

---

### Map data

| Method | Path | Notes |
|--------|------|--------|
| **GET** | `/api/real-estate/map-data` | Projects and units that have coordinates |

---

## 4. Installment APIs (detail)

### 4.1 List installment templates

**`GET /api/real-estate/installment-templates`**

**Query parameters (all optional)**

| Parameter | Type | Effect |
|-----------|------|--------|
| `project_id` | integer | Only templates compatible with that project (matches Odoo domain: not project-scoped, or scoped to this project). |
| `sector_id` | integer | Phase/sector filter; can be used alone or with `project_id`. |

Examples:

- All active templates:  
  `GET /api/real-estate/installment-templates`
- Match an opportunity’s project + phase:  
  `GET /api/real-estate/installment-templates?project_id=1&sector_id=2`

**Success (200)**

```json
{
  "success": true,
  "templates": [
    {
      "id": 1,
      "code": "STD12",
      "name": "12 months standard",
      "active": true,
      "valid_from": null,
      "valid_to": null,
      "duration_years": 1,
      "payment_frequency": "monthly",
      "installments_per_year": 12,
      "installment_count": 12,
      "dp_type": "percent",
      "down_payment_percent": 10,
      "down_payment_amount": 0,
      "disc_type": "percent",
      "discount_percent": 0,
      "discount_amount": 0,
      "pen_type": "percent",
      "penalty_percent": 0,
      "penalty_amount": 0,
      "grace_period_days": 0,
      "scope_project_enabled": false,
      "scope_project_id": null,
      "scope_project_name": null,
      "scope_phase_enabled": false,
      "scope_phase_id": null,
      "scope_phase_name": null,
      "bullet_lines": [
        {
          "id": 1,
          "sequence": 10,
          "name": "Annual bullet",
          "frequency": "annual",
          "value_type": "percent",
          "amount_value": 5
        }
      ]
    }
  ]
}
```

---

### 4.2 Get installment lines for an opportunity

**`GET /api/real-estate/opportunities/<opportunity_id>/installments`**

- **Path parameter:** `opportunity_id` — CRM lead id (`crm.lead`).
- **Access:** opportunity must exist, `type === 'opportunity'`, and **`user_id`** must be the logged-in user.

**Success (200)**

```json
{
  "success": true,
  "opportunity_id": 42,
  "installment_system_id": 1,
  "installment_system_name": "12 months standard",
  "installment_base_price": 1500000,
  "installment_start_date": "2026-05-01",
  "unit_price": 1500000,
  "lines": [
    {
      "id": 100,
      "installment_no": 1,
      "installment_type": "down_payment",
      "due_date": "2026-05-01",
      "amount": 150000,
      "discount_amount": 0,
      "penalty_rate": 0,
      "penalty_amount_fixed": 0,
      "grace_days": 0,
      "remaining_installment": 150000,
      "remaining_penalty": 0,
      "total_payable": 150000,
      "status": "upcoming",
      "currency": "USD"
    }
  ]
}
```

**`installment_type`** values (examples): `down_payment`, `installment`, `milestone`, etc. (see Odoo model `real.estate.installment.line`).

**Errors:** `404` not found, `400` not an opportunity, `403` forbidden (wrong salesperson).

---

### 4.3 Regenerate installment schedule

**`POST /api/real-estate/opportunities/<opportunity_id>/installments/regenerate`**

| | |
|---|---|
| **CSRF** | Disabled — safe for mobile / SPA using cookie auth |
| **Body** | JSON object; **all keys optional** |

**Body fields (optional)**

| Field | Type | Notes |
|--------|------|--------|
| `installment_system_id` | integer \| null | Set or clear template before generation. |
| `installment_base_price` | number | Amount used for calculation (falls back to unit price in backend if not set). |
| `installment_start_date` | string (date) \| null | First schedule anchor; empty clears to backend default. |

Empty body `{}` is valid: updates nothing, then runs generation with current opportunity values.

**Success (200)**

```json
{
  "success": true,
  "message": "Schedule regenerated.",
  "opportunity_id": 42,
  "lines_count": 13,
  "lines": [ /* same shape as GET /installments lines */ ]
}
```

**Error (400)** — business rule / validation (same messages as Odoo UI), example:

```json
{ "error": "Please set a unit and an installment template." }
```

**Other errors:** `403`, `404`, `400` invalid JSON, `500`.

---

## 5. Frontend implementation checklist

| Item | Detail |
|------|--------|
| Session | After auth, include cookies on every request to the **same origin** as Odoo. |
| POST routes | Use `Content-Type: application/json` and `csrf=False` is already on the server; you do **not** need Odoo’s `csrf_token` for these routes. |
| CORS | If the SPA is on **another domain**, you must configure CORS and credentials on the reverse proxy or Odoo; same-origin SPAs avoid this. |
| Installments | Ensure opportunity has **unit** + **template** before calling regenerate; handle `400` `error` text for user messaging. |
| Salesperson | API installments only for opportunities assigned to the logged-in user. |

---

## 6. Quick `fetch` examples (browser)

```javascript
// 1) Login
const base = 'https://your-odoo.com';
await fetch(`${base}/api/real-estate/auth`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'sales@example.com', password: '***' }),
});

// 2) Templates for opportunity context
const pid = 1, sid = 2;
await fetch(
  `${base}/api/real-estate/installment-templates?project_id=${pid}&sector_id=${sid}`,
  { credentials: 'include' }
);

// 3) Regenerate schedule
await fetch(
  `${base}/api/real-estate/opportunities/42/installments/regenerate`,
  {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      installment_system_id: 3,
      installment_base_price: 1200000,
      installment_start_date: '2026-06-01',
    }),
  }
);
```

---

*Generated for module **real_estate_crm**; keep in sync with `controllers/controllers.py` when adding routes.*
