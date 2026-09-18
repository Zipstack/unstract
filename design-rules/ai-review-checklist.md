# AI Review Checklist

Every change must answer "yes" to all applicable questions. A "no" or "unsure" is a blocking finding.

---

## 1. Org scoping (P1)

|  |  |
|---|---|
| **Question** | Does every new or modified read/write of tenant data pass through a manager or filter backend that scopes by organization? |

---

## 2. Credentials (P2)

|  |  |
|---|---|
| **Question** | Are any new credential, token, or secret fields stored in `EncryptedBinaryField` (or equivalent)? |

---

## 3. Publishing gate (P3)

|  |  |
|---|---|
| **Question** | If the change introduces an authoring artifact, is there an explicit publish step that produces a separate runtime artifact? |

---

## 4. Audit/billing durability (P4)

|  |  |
|---|---|
| **Question** | If the change touches usage, billing, or audit-style records, do those records survive the deletion of their source? |
| **Question** | Does this PR add or change an `on_delete` behavior on an FK? If yes, is the intent documented inline on the field, and is the cascade safe for audit/retention (P4)? Models are the source of truth for cascades — verify via `grep on_delete` rather than a separate list. |

---

## 5. Fail closed (P5)

|  |  |
|---|---|
| **Question** | Do permission and feature checks default to deny on missing or ambiguous inputs? |

---

## 6. Execution org inheritance (P6)

|  |  |
|---|---|
| **Question** | If the change adds an execution-side model, does it inherit org through its parent rather than duplicating `organization_id`? |

---

## 7. Deployments as triggers (P7)

|  |  |
|---|---|
| **Question** | If the change adds a deployment or schedule, does it reference the workflow rather than copying its data? |

---

## 8. Internal vs external (P8)

|  |  |
|---|---|
| **Question** | Is service-to-service traffic on `/internal/...` with internal auth, and end-user traffic on the external surface? |

---

## 9. Anchor integrity (P9)

|  |  |
|---|---|
| **Question** | If the change adds a model that belongs to an anchor entity (e.g. `Workflow`), does it derive org from that anchor rather than introducing a parallel direct FK? |
