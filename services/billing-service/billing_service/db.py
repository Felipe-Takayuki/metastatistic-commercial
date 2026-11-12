import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from billing_service.models import InvoiceResponse, SubscriptionResponse, TierType, SubscriptionStatusType, InvoiceStatusType


class BillingStore:
    def __init__(self, db_path: str = "./billing.db"):
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "")
        elif db_path.startswith("sqlite://"):
            self.db_path = db_path.replace("sqlite://", "")
        else:
            self.db_path = db_path

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenant_customers (
                    tenant_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL UNIQUE,
                    email TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    stripe_subscription_id TEXT UNIQUE,
                    plan_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_period_start TEXT,
                    current_period_end TEXT,
                    cancel_at_period_end INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sub_tenant ON subscriptions(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_sub_stripe ON subscriptions(stripe_subscription_id);

                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subscription_id TEXT,
                    stripe_invoice_id TEXT UNIQUE,
                    amount_due INTEGER,
                    amount_paid INTEGER,
                    currency TEXT DEFAULT 'usd',
                    status TEXT NOT NULL,
                    hosted_invoice_url TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inv_tenant ON invoices(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_inv_stripe ON invoices(stripe_invoice_id);
            """)
            conn.commit()

    def get_customer(self, tenant_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tenant_customers WHERE tenant_id = ?", (tenant_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def get_tenant_by_customer_id(self, customer_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT tenant_id FROM tenant_customers WHERE customer_id = ?", (customer_id,)).fetchone()
            if row:
                return row["tenant_id"]
            row_sub = conn.execute("SELECT tenant_id FROM subscriptions WHERE customer_id = ?", (customer_id,)).fetchone()
            if row_sub:
                return row_sub["tenant_id"]
            return None

    def save_customer(self, tenant_id: str, customer_id: str, email: Optional[str] = None):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tenant_customers (tenant_id, customer_id, email, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    email = COALESCE(excluded.email, tenant_customers.email)
                """,
                (tenant_id, customer_id, email, now_iso),
            )
            conn.commit()

    def get_subscription_by_tenant(self, tenant_id: str) -> Optional[SubscriptionResponse]:
        with self._get_connection() as conn:
            # Pega a assinatura mais recente ou ativa do tenant
            row = conn.execute(
                """
                SELECT * FROM subscriptions
                WHERE tenant_id = ?
                ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """,
                (tenant_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_sub(row)

    def get_subscription_by_stripe_id(self, stripe_sub_id: str) -> Optional[SubscriptionResponse]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE stripe_subscription_id = ?",
                (stripe_sub_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_sub(row)

    def upsert_subscription(
        self,
        tenant_id: str,
        customer_id: str,
        plan_id: str,
        tier: TierType,
        status: SubscriptionStatusType,
        stripe_subscription_id: Optional[str] = None,
        current_period_start: Optional[str] = None,
        current_period_end: Optional[str] = None,
        cancel_at_period_end: bool = False,
    ) -> SubscriptionResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing = None
            if stripe_subscription_id:
                existing = cursor.execute(
                    "SELECT * FROM subscriptions WHERE stripe_subscription_id = ?",
                    (stripe_subscription_id,),
                ).fetchone()

            if not existing:
                existing = cursor.execute(
                    "SELECT * FROM subscriptions WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()

            if existing:
                sub_id = existing["id"]
                cursor.execute(
                    """
                    UPDATE subscriptions SET
                        customer_id = ?,
                        stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                        plan_id = ?,
                        tier = ?,
                        status = ?,
                        current_period_start = COALESCE(?, current_period_start),
                        current_period_end = COALESCE(?, current_period_end),
                        cancel_at_period_end = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        customer_id,
                        stripe_subscription_id,
                        plan_id,
                        tier,
                        status,
                        current_period_start,
                        current_period_end,
                        1 if cancel_at_period_end else 0,
                        now_iso,
                        sub_id,
                    ),
                )
            else:
                sub_id = f"sub_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO subscriptions (
                        id, tenant_id, customer_id, stripe_subscription_id,
                        plan_id, tier, status, current_period_start, current_period_end,
                        cancel_at_period_end, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sub_id,
                        tenant_id,
                        customer_id,
                        stripe_subscription_id,
                        plan_id,
                        tier,
                        status,
                        current_period_start,
                        current_period_end,
                        1 if cancel_at_period_end else 0,
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
            updated_row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
            return self._row_to_sub(updated_row)

    def save_invoice(
        self,
        tenant_id: str,
        amount_due: int,
        amount_paid: int,
        status: InvoiceStatusType,
        subscription_id: Optional[str] = None,
        stripe_invoice_id: Optional[str] = None,
        currency: str = "usd",
        hosted_invoice_url: Optional[str] = None,
    ) -> InvoiceResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            inv_id = f"inv_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO invoices (
                    id, tenant_id, subscription_id, stripe_invoice_id,
                    amount_due, amount_paid, currency, status,
                    hosted_invoice_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stripe_invoice_id) DO UPDATE SET
                    amount_due = excluded.amount_due,
                    amount_paid = excluded.amount_paid,
                    status = excluded.status,
                    hosted_invoice_url = COALESCE(excluded.hosted_invoice_url, invoices.hosted_invoice_url)
                """,
                (
                    inv_id,
                    tenant_id,
                    subscription_id,
                    stripe_invoice_id,
                    amount_due,
                    amount_paid,
                    currency,
                    status,
                    hosted_invoice_url,
                    now_iso,
                ),
            )
            conn.commit()
            if stripe_invoice_id:
                row = conn.execute("SELECT * FROM invoices WHERE stripe_invoice_id = ?", (stripe_invoice_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
            return self._row_to_invoice(row)

    def list_invoices_by_tenant(self, tenant_id: str) -> List[InvoiceResponse]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
            return [self._row_to_invoice(r) for r in rows]

    def _row_to_sub(self, row: sqlite3.Row) -> SubscriptionResponse:
        return SubscriptionResponse(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            stripe_subscription_id=row["stripe_subscription_id"],
            plan_id=row["plan_id"],
            tier=row["tier"],
            status=row["status"],
            current_period_start=row["current_period_start"],
            current_period_end=row["current_period_end"],
            cancel_at_period_end=bool(row["cancel_at_period_end"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_invoice(self, row: sqlite3.Row) -> InvoiceResponse:
        return InvoiceResponse(
            id=row["id"],
            tenant_id=row["tenant_id"],
            subscription_id=row["subscription_id"],
            stripe_invoice_id=row["stripe_invoice_id"],
            amount_due=row["amount_due"],
            amount_paid=row["amount_paid"],
            currency=row["currency"],
            status=row["status"],
            hosted_invoice_url=row["hosted_invoice_url"],
            created_at=row["created_at"],
        )
