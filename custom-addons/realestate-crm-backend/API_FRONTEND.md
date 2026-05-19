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
**Geolocation requirements:** 
- Opportunities must have **`agent_latitude`** and **`agent_longitude`** populated to appear in map dashboard filters.
- If creating opportunities via the API, provide `agent_latitude` and `agent_longitude` in the POST body; these capture the salesperson's location when the opportunity was created.
- Linked units must also have **`latitude`** and **`longitude`** for proper geolocation filtering on the map.
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
| **GET** | `/api/real-estate/projects` | — | Returns the active project portfolio payload. |

**Exact payload shape**

```json
{
  "success": true,
  "projects": [
    {
      "id": 1,
      "name": "Ocean View Residences",
      "code": "OVR-001",
      "sector_id": [3, "North Sector"],
      "location": "Riverside Avenue, Cairo",
      "total_units": 120
    }
  ]
}
```

**Notes**

- `sector_id` is a two-item relation array `[id, name]`.
- If a project has no linked sector, `sector_id` is `null`.

---

### Buildings

| Method | Path | Query parameters | Notes |
|--------|------|------------------|------|
| **GET** | `/api/real-estate/buildings` | `project_id` (optional) | Returns active buildings, optionally filtered to one project. |

**Exact payload shape**

```json
{
  "success": true,
  "buildings": [
    {
      "id": 7,
      "name": "Tower B",
      "project_id": [1, "Ocean View Residences"],
      "floors_count": 24,
      "amenities": [
        "Rooftop pool"
      ]
    }
  ]
}
```

**Notes**

- `amenities` is an array of strings. When the model has no dedicated amenities field, the backend currently falls back to the building description as a single entry.
- `project_id` is `null` if the building has no parent project.

---

### Units

| Method | Path | Query parameters | Notes |
|--------|------|------------------|------|
| **GET** | `/api/real-estate/units` | `building_id` (optional), `status` (optional), `project_id` (optional legacy compatibility filter) | Returns active units with coordinates. |

**Valid `status` filters**

- `available`
- `reserved`
- `sold`

**Exact payload shape**

```json
{
  "success": true,
  "units": [
    {
      "id": 42,
      "name": "Apartment 402",
      "building_id": [7, "Tower B"],
      "price": 1250000,
      "status": "available",
      "floor": 4,
      "rooms_count": 3,
      "latitude": 30.0444,
      "longitude": 31.2357
    }
  ]
}
```

**Notes**

- `building_id` is a two-item relation array `[id, name]`.
- `latitude` and `longitude` are serialized directly from the unit record for map rendering.

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
| **GET** | `/api/real-estate/contacts` | Returns the authenticated user’s contact directory payload. |

**Backend filter rules**

The backend applies the following live filters when building the contacts directory response:

- `active = True`
- `customer_rank > 0` **OR** the partner is linked to a `crm.lead` owned by the current authenticated user

This means the response is effectively a cross-filter of:

1. all active partners that are customers, plus
2. any active partners attached to the current user’s CRM leads

**Success response example**

```json
{
  "success": true,
  "contacts": [
    {
      "id": 12,
      "name": "Amina Hassan",
      "email": "amina@example.com",
      "phone": "+201234567890",
      "company": "Hassan Properties"
    },
    {
      "id": 19,
      "name": "Omar Farouk",
      "email": "omar@example.com",
      "phone": "+201112223334",
      "company": null
    }
  ]
}
```

**TypeScript typing shape**

```ts
export interface ContactDirectoryItem {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
}

export interface ContactDirectoryResponse {
  success: boolean;
  contacts: ContactDirectoryItem[];
}
```

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
[
  {
    "id": 1,
    "name": "12 months standard",
    "down_payment_percentage": 10,
    "number_of_installments": 12
  }
]
```

---

### 4.2 Get installment lines for an opportunity

**`GET /api/real-estate/opportunities/<opportunity_id>/installments`**

- **Path parameter:** `opportunity_id` — CRM lead id (`crm.lead`).
- **Access:** opportunity must exist, `type === 'opportunity'`, and **`user_id`** must be the logged-in user.

**Success (200)**

```json
[
  {
    "id": 100,
    "opportunity_id": 42,
    "amount": 150000,
    "due_date": "2026-05-01",
    "payment_status": "pending"
  }
]
```

**`payment_status` values**

- `paid`
- `pending`
- `overdue`

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
| Local test records | See the module demo data for `demo_opportunity` and `demo_opportunity_2`, created for login `demo.agent` / `demo`. |

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
