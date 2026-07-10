#!/usr/bin/env python3
"""Source of truth for the code-review case set (the moat).

Each dirty case is a small, focused diff where ONE planted defect is the salient
issue and the rest of the change is clean. Each clean case is a genuine, faithful
change a good review should leave alone (the false-positive guard). Run this to
(re)emit cases.jsonl next to it. Keeping the diffs as readable triple-quoted
strings — instead of hand-escaped JSONL — is what lets a human (or codex) extend
the set without introducing quoting bugs.

Schema (mirrors highsignal): {id, kind, expect, context, draft, [spec]}
  kind   = "dirty" | "clean"
  expect = one category id (dirty only; ignored for clean)
  draft  = the diff to review
  spec   = optional PRD text (spec-* cases include it)
"""
import json
from pathlib import Path

# Closed output vocabulary. 12 Fowler smells + 3 spec-defect types.
CATEGORIES = {
    "mysterious-name": "a name that doesn't reveal what it does/holds",
    "duplicated-code": "the same logic shape in more than one place in the change",
    "feature-envy": "a method that reaches into another object's data more than its own",
    "data-clumps": "the same few fields/params keep travelling together",
    "primitive-obsession": "a primitive/string standing in for a domain concept",
    "repeated-switches": "the same switch/if-cascade on the same type recurs",
    "shotgun-surgery": "one logical change forces scattered edits across many files",
    "divergent-change": "one module edited for several unrelated reasons",
    "speculative-generality": "abstraction/params/hooks added for needs the spec doesn't have",
    "message-chains": "long a.b().c().d() navigation the caller shouldn't depend on",
    "middle-man": "a class/function that mostly just delegates onward",
    "refused-bequest": "a subclass that ignores/overrides most of what it inherits",
    "spec-missing": "a required behaviour is absent or only partially implemented",
    "spec-scope-creep": "behaviour added that the spec did not ask for",
    "spec-wrong": "a required behaviour implemented incorrectly",
}

CASES = []


def dirty(id, expect, draft, context="typescript", spec=None):
    case = {"id": id, "kind": "dirty", "expect": expect, "context": context, "draft": draft.strip("\n")}
    if spec:
        case["spec"] = spec.strip("\n")
    CASES.append(case)


def clean(id, draft, context="typescript", spec=None):
    case = {"id": id, "kind": "clean", "expect": [], "context": context, "draft": draft.strip("\n")}
    if spec:
        case["spec"] = spec.strip("\n")
    CASES.append(case)


# ---------------------------------------------------------------------------
# DIRTY — Fowler smells (7 high-headroom)
# ---------------------------------------------------------------------------

dirty("cr-mysterious-name", "mysterious-name", """
--- a/src/cart.ts
+++ b/src/cart.ts
@@ export class Cart {
+  calc(d: LineItem[]): number {
+    let x = 0
+    for (const i of d) x += i.price * i.qty
+    return x
+  }
 }
""")

dirty("cr-duplicated-code", "duplicated-code", """
--- a/src/users.ts
+++ b/src/users.ts
@@ export function createUser(input: NewUser) {
+  if (!input.email.includes("@") || input.email.length < 3) {
+    throw new Error("invalid email")
+  }
   return db.users.insert(input)
 }
@@ export function updateUser(id: string, input: NewUser) {
+  if (!input.email.includes("@") || input.email.length < 3) {
+    throw new Error("invalid email")
+  }
   return db.users.update(id, input)
 }
""")

dirty("cr-feature-envy", "feature-envy", """
--- a/src/invoice.ts
+++ b/src/invoice.ts
@@ export class Invoice {
+  formatShippingLabel(): string {
+    return [
+      this.customer.street,
+      this.customer.city + ", " + this.customer.state,
+      this.customer.zip,
+      this.customer.country,
+    ].join("\\n")
+  }
 }
""")

dirty("cr-data-clumps", "data-clumps", """
--- a/src/canvas.ts
+++ b/src/canvas.ts
@@
+export function drawRect(x: number, y: number, width: number, height: number, color: string) { /* ... */ }
+export function clearRect(x: number, y: number, width: number, height: number) { /* ... */ }
+export function isInside(px: number, py: number, x: number, y: number, width: number, height: number) { /* ... */ }
""")

dirty("cr-primitive-obsession", "primitive-obsession", """
--- a/src/billing.ts
+++ b/src/billing.ts
@@ export function charge(
-  amount: number,
-  currency: string,
+  amount: number,   // cents
+  currency: string, // "usd" | "eur" | ...
   card: Card,
 ) {
-  return gateway.charge(amount, currency, card)
+  const formatted = (amount / 100).toFixed(2) + " " + currency.toUpperCase()
+  logger.info("charging " + formatted)
+  return gateway.charge(amount, currency, card)
 }
""")

dirty("cr-speculative-generality", "speculative-generality", """
--- a/src/notify.ts
+++ b/src/notify.ts
@@
-export function sendWelcome(user: User) {
-  mailer.send(user.email, welcomeTemplate(user))
+export interface NotifyOptions { retries?: number; channel?: string; transform?: (s: string) => string }
+export function sendWelcome(user: User, options: NotifyOptions = {}) {
+  mailer.send(user.email, welcomeTemplate(user))
 }
""")

dirty("cr-message-chains", "message-chains", """
--- a/src/tax.ts
+++ b/src/tax.ts
@@ export function taxRegionFor(order: Order): string {
+  return order.getCustomer().getAddress().getCountry().getTaxAuthority().getCode()
 }
""")

# ---------------------------------------------------------------------------
# DIRTY — Spec defects (all 3 types; each carries a spec)
# ---------------------------------------------------------------------------

dirty(
    "cr-spec-missing", "spec-missing",
    spec="""
Ticket ACC-12 — deposit()
- Add funds to the account balance.
- Reject non-positive amounts (amount <= 0) by throwing a ValidationError.
""",
    draft="""
--- a/src/account.ts
+++ b/src/account.ts
@@ export class Account {
+  deposit(amount: number) {
+    this.balance += amount
+    return this.balance
+  }
 }
""",
)

dirty(
    "cr-spec-scope-creep", "spec-scope-creep",
    spec="""
Ticket BLOG-7 — add a `slug` field to Post
- Posts get a URL-safe `slug` string, derived from the title on create.
""",
    draft="""
--- a/src/post.ts
+++ b/src/post.ts
@@ export function createPost(input: NewPost) {
-  return db.posts.insert(input)
+  const slug = slugify(input.title)
+  analytics.track("post_created", { title: input.title })
+  mailer.send(ADMIN_EMAIL, "New post: " + input.title)
+  return db.posts.insert({ ...input, slug })
 }
""",
)

dirty(
    "cr-spec-wrong", "spec-wrong",
    spec="""
Ticket ACC-15 — withdraw()
- Subtract `amount` from the balance and return the NEW (post-withdrawal) balance.
""",
    draft="""
--- a/src/account.ts
+++ b/src/account.ts
@@ export class Account {
+  withdraw(amount: number) {
+    const previous = this.balance
+    this.balance -= amount
+    return previous
+  }
 }
""",
)

# ---------------------------------------------------------------------------
# CLEAN — faithful, well-formed changes a good review leaves alone
# ---------------------------------------------------------------------------

clean("cr-clean-rename", """
--- a/src/cart.ts
+++ b/src/cart.ts
@@ export class Cart {
+  totalPrice(items: LineItem[]): number {
+    return items.reduce((sum, item) => sum + item.price * item.qty, 0)
+  }
 }
""")

clean(
    "cr-clean-spec-match", spec="""
Ticket USR-3 — add `isActive`
- User gains an `isActive` boolean, defaulting to true on create.
""",
    draft="""
--- a/src/user.ts
+++ b/src/user.ts
@@ export function createUser(input: NewUser) {
-  return db.users.insert(input)
+  return db.users.insert({ ...input, isActive: input.isActive ?? true })
 }
""",
)

clean("cr-clean-idiomatic-switch", """
--- a/src/status.ts
+++ b/src/status.ts
@@
+export function label(status: Status): string {
+  switch (status) {
+    case "open": return "Open"
+    case "closed": return "Closed"
+    case "pending": return "Pending"
+  }
+}
""")

clean("cr-clean-small-type", """
--- a/src/geo.ts
+++ b/src/geo.ts
@@
+export interface LatLng { lat: number; lng: number }
+export function distanceKm(a: LatLng, b: LatLng): number {
+  const dLat = toRad(b.lat - a.lat)
+  const dLng = toRad(b.lng - a.lng)
+  return haversine(dLat, dLng, a.lat, b.lat)
+}
""")

# ---------------------------------------------------------------------------
# DIRTY — more Fowler smells
# ---------------------------------------------------------------------------

dirty("cr-repeated-switches", "repeated-switches", """
--- a/src/orders.ts
+++ b/src/orders.ts
@@
+export function statusLabel(status: OrderStatus): string {
+  switch (status) {
+    case "new": return "New"
+    case "paid": return "Paid"
+    case "shipped": return "Shipped"
+  }
+}
+
+export function statusColor(status: OrderStatus): string {
+  switch (status) {
+    case "new": return "gray"
+    case "paid": return "green"
+    case "shipped": return "blue"
+  }
+}
""")

dirty("cr-repeated-switches-notifications", "repeated-switches", """
--- a/src/notifications.ts
+++ b/src/notifications.ts
@@
+export function subjectFor(event: Event): string {
+  if (event.type === "invite") return "You were invited"
+  if (event.type === "reminder") return "Reminder"
+  return "Update"
+}
+
+export function templateFor(event: Event): string {
+  if (event.type === "invite") return "invite-email"
+  if (event.type === "reminder") return "reminder-email"
+  return "default-email"
+}
""")

dirty("cr-shotgun-surgery", "shotgun-surgery", """
--- a/src/orders/model.ts
+++ b/src/orders/model.ts
@@
-export type OrderStatus = "new" | "paid"
+export type OrderStatus = "new" | "paid" | "refunded"
--- a/src/orders/badge.ts
+++ b/src/orders/badge.ts
@@
+export const refundedBadge = { label: "Refunded", color: "orange" }
--- a/src/orders/email.ts
+++ b/src/orders/email.ts
@@
+export const refundedSubject = "Your order was refunded"
--- a/src/orders/report.ts
+++ b/src/orders/report.ts
@@
+export const refundedColumn = "refunded_at"
""")

dirty("cr-shotgun-surgery-role", "shotgun-surgery", """
--- a/src/auth/roles.ts
+++ b/src/auth/roles.ts
@@
-export type Role = "admin" | "member"
+export type Role = "admin" | "member" | "auditor"
--- a/src/nav.ts
+++ b/src/nav.ts
@@
+export const auditorNav = ["/reports", "/exports"]
--- a/src/reports/permissions.ts
+++ b/src/reports/permissions.ts
@@
+export const auditorReports = ["monthly", "annual"]
--- a/src/users/badge.ts
+++ b/src/users/badge.ts
@@
+export const auditorBadge = "Auditor"
""")

# divergent-change intentionally omitted as a dirty case: it is a LONGITUDINAL smell
# (one module edited for many UNRELATED reasons over time) that a single-diff snapshot
# can't fairly show — GPT-5.5 reliably read our attempts as primitive-obsession instead
# (the params are stringly-typed). Its single-diff-representable sibling shotgun-surgery
# IS covered above. `divergent-change` stays in the vocabulary; it just has no gold case.

dirty("cr-middle-man", "middle-man", """
--- a/src/user-service.ts
+++ b/src/user-service.ts
@@
+export class UserService {
+  constructor(private readonly users: UserRepository) {}
+  find(id: string) { return this.users.find(id) }
+  save(user: User) { return this.users.save(user) }
+  remove(id: string) { return this.users.remove(id) }
+}
""")

dirty("cr-middle-man-logger", "middle-man", """
--- a/src/audit.ts
+++ b/src/audit.ts
@@
+export function recordLogin(userId: string) {
+  return auditLog.recordLogin(userId)
+}
+
+export function recordLogout(userId: string) {
+  return auditLog.recordLogout(userId)
+}
""")

dirty("cr-refused-bequest", "refused-bequest", """
--- a/src/repository.ts
+++ b/src/repository.ts
@@
+export class ReadOnlyUserRepository extends UserRepository {
+  save(_user: User): never { throw new Error("read only") }
+  delete(_id: string): never { throw new Error("read only") }
+  update(_user: User): never { throw new Error("read only") }
+}
""")

dirty("cr-refused-bequest-export", "refused-bequest", """
--- a/src/exporters.ts
+++ b/src/exporters.ts
@@
+export class CsvPreviewExporter extends CsvExporter {
+  writeHeader(): string { return "" }
+  writeRow(_row: Row): string { return "" }
+  save(_path: string): never { throw new Error("preview only") }
+  preview(rows: Row[]) { return rows.slice(0, 5).map(row => row.name).join("\\n") }
+}
""")

# ---------------------------------------------------------------------------
# DIRTY — more spec defects
# ---------------------------------------------------------------------------

dirty(
    "cr-spec-missing-timeout", "spec-missing",
    spec="""
Ticket AUTH-21 — password reset token
- Generate a reset token.
- Token must expire 30 minutes after creation.
""",
    draft="""
--- a/src/auth/reset.ts
+++ b/src/auth/reset.ts
@@
+export function createResetToken(userId: string) {
+  return db.resetTokens.insert({ userId, token: randomToken() })
+}
""",
)

dirty(
    "cr-spec-scope-creep-cache", "spec-scope-creep",
    spec="""
Ticket PROF-4 — expose displayName
- Add `displayName` to the profile response.
""",
    draft="""
--- a/src/profile.ts
+++ b/src/profile.ts
@@ export function profileResponse(user: User) {
-  return { id: user.id, email: user.email }
+  cache.set(user.id, user)
+  return { id: user.id, email: user.email, displayName: user.name }
 }
""",
)

dirty(
    "cr-spec-wrong-sort", "spec-wrong",
    spec="""
Ticket ORD-9 — recent orders
- Return orders from newest to oldest.
""",
    draft="""
--- a/src/orders.ts
+++ b/src/orders.ts
@@ export function recentOrders(orders: Order[]) {
-  return orders
+  return orders.sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
 }
""",
)

# ---------------------------------------------------------------------------
# CLEAN — more false-positive guards
# ---------------------------------------------------------------------------

clean("cr-clean-standalone-reducer", """
--- a/src/cart-summary.ts
+++ b/src/cart-summary.ts
@@
+export function summarize(items: LineItem[]) {
+  return items.reduce((total, item) => total + item.price * item.qty, 0)
+}
""")

clean("cr-clean-single-switch", """
--- a/src/payment.ts
+++ b/src/payment.ts
@@
+export function gatewayFor(method: PaymentMethod): Gateway {
+  switch (method) {
+    case "card": return stripeGateway
+    case "bank": return achGateway
+    case "cash": return offlineGateway
+  }
+}
""")

clean("cr-clean-short-local-names", """
--- a/src/grid.ts
+++ b/src/grid.ts
@@
+export function neighbors(x: number, y: number): Point[] {
+  const out: Point[] = []
+  for (let i = 0; i < DIRECTIONS.length; i++) {
+    const [dx, dy] = DIRECTIONS[i]
+    out.push({ x: x + dx, y: y + dy })
+  }
+  return out
+}
""")

clean("cr-clean-primitive-value-object", """
--- a/src/rgb.ts
+++ b/src/rgb.ts
@@
+export interface Rgb {
+  r: number
+  g: number
+  b: number
+}
""")

clean("cr-clean-local-wrapper", """
--- a/src/session.ts
+++ b/src/session.ts
@@
+export function requireSession(request: Request) {
+  const session = sessionStore.get(request)
+  if (!session) throw new Error("unauthorized")
+  return session
+}
""")

# (removed cr-clean-message-chain-data: whether optional-chaining property access
#  `a?.b?.c` counts as a Fowler message-chain — which is about METHOD-call navigation —
#  is genuinely debatable, so "clean" is not a defensible gold label. GPT-5.5 read it as
#  message-chains 2/3 of runs; that's a fair reviewer call, not a false positive.)

clean("cr-clean-subclass-specialization", """
--- a/src/csv.ts
+++ b/src/csv.ts
@@
+export class SemicolonCsvWriter extends CsvWriter {
+  protected delimiter() {
+    return ";"
+  }
+}
""")

clean("cr-clean-small-data-clump", """
--- a/src/search.ts
+++ b/src/search.ts
@@
+export function page(items: Result[], offset: number, limit: number) {
+  return items.slice(offset, offset + limit)
+}
""")


def main():
    out = Path(__file__).with_name("cases.jsonl")
    with out.open("w") as f:
        for case in CASES:
            f.write(json.dumps(case) + "\n")
    dirty_n = sum(1 for c in CASES if c["kind"] == "dirty")
    clean_n = sum(1 for c in CASES if c["kind"] == "clean")
    print(f"wrote {out}  ({len(CASES)} cases: {dirty_n} dirty, {clean_n} clean)")
    # sanity: every dirty expect is in the closed vocabulary
    bad = [c["id"] for c in CASES if c["kind"] == "dirty" and c["expect"] not in CATEGORIES]
    if bad:
        raise SystemExit(f"dirty cases with unknown category id: {bad}")


if __name__ == "__main__":
    main()
