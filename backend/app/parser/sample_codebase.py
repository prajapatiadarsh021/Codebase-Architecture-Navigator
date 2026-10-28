import os

def create_sample_codebase(target_dir: str):
    """
    Creates a realistic multi-module Python enterprise codebase for AST ingestion.
    """
    os.makedirs(os.path.join(target_dir, "models"), exist_ok=True)
    os.makedirs(os.path.join(target_dir, "services"), exist_ok=True)
    os.makedirs(os.path.join(target_dir, "api"), exist_ok=True)
    os.makedirs(os.path.join(target_dir, "workers"), exist_ok=True)

    # 1. models/user_schema.py
    with open(os.path.join(target_dir, "models", "user_schema.py"), "w", encoding="utf-8") as f:
        f.write('''"""Core domain schemas and entity definitions."""

class UserSchema:
    """Represents an authenticated user account and tenant permissions."""
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email = email
        self.role = role

    def validate_user_payload(self) -> bool:
        """Validates email format and role permissions."""
        return "@" in self.email and len(self.user_id) > 0

    def serialize_profile(self) -> dict:
        """Serializes user record into external JSON representation."""
        return {"id": self.user_id, "email": self.email, "role": self.role}


class AccountProfile:
    """Financial ledger balance and billing tier preferences."""
    def __init__(self, account_id: str, balance: float):
        self.account_id = account_id
        self.balance = balance

    def update_balance(self, amount: float) -> float:
        """Applies credit or debit to the active account balance."""
        self.balance += amount
        return self.balance
''')

    # 2. services/auth_service.py
    with open(os.path.join(target_dir, "services", "auth_service.py"), "w", encoding="utf-8") as f:
        f.write('''"""Authentication, password verification, and JWT session handling."""
from models.user_schema import UserSchema

def authenticate_user(email: str, password_hash: str) -> UserSchema:
    """Verifies user credentials and instantiates UserSchema."""
    user = UserSchema("usr_9981", email, "admin")
    if not user.validate_user_payload():
        raise ValueError("Invalid user record encountered")
    return user

def issue_access_token(user: UserSchema) -> str:
    """Generates encrypted session token for authenticated user."""
    profile = user.serialize_profile()
    return f"jwt.{profile['id']}.signed"

def revoke_session(token: str) -> bool:
    """Invalidates active token in distributed cache."""
    return len(token) > 0
''')

    # 3. services/billing_service.py
    with open(os.path.join(target_dir, "services", "billing_service.py"), "w", encoding="utf-8") as f:
        f.write('''"""Billing lifecycle, card processing, and invoice generation."""
from models.user_schema import AccountProfile
from services.auth_service import authenticate_user

def process_subscription_charge(email: str, amount: float) -> bool:
    """Authenticates user and applies payment charge to ledger."""
    user = authenticate_user(email, "hashed_token")
    ledger = AccountProfile("acc_4001", 150.0)
    ledger.update_balance(-amount)
    return True

def calculate_monthly_invoices(account_id: str) -> list:
    """Computes prorated billing increments across billing period."""
    ledger = AccountProfile(account_id, 0.0)
    ledger.update_balance(50.0)
    return [{"invoice_id": "inv_1", "total": 50.0}]
''')

    # 4. services/notification_service.py
    with open(os.path.join(target_dir, "services", "notification_service.py"), "w", encoding="utf-8") as f:
        f.write('''"""Outbound security alerts and transactional customer notifications."""
from services.auth_service import authenticate_user
from services.billing_service import calculate_monthly_invoices

def send_security_alert(email: str, alert_type: str) -> bool:
    """Dispatches high priority security advisory to user email."""
    user = authenticate_user(email, "token_check")
    return True

def dispatch_invoice_receipt(email: str, account_id: str) -> bool:
    """Retrieves computed invoices and emails customer receipt."""
    invoices = calculate_monthly_invoices(account_id)
    return len(invoices) > 0
''')

    # 5. api/controllers.py
    with open(os.path.join(target_dir, "api", "controllers.py"), "w", encoding="utf-8") as f:
        f.write('''"""HTTP REST controllers and incoming request handlers."""
from services.auth_service import authenticate_user, issue_access_token
from services.billing_service import process_subscription_charge
from services.notification_service import send_security_alert, dispatch_invoice_receipt

def handle_login_request(email: str, password_hash: str) -> dict:
    """Endpoint controller handling user authentication and token exchange."""
    user = authenticate_user(email, password_hash)
    token = issue_access_token(user)
    return {"token": token, "email": email}

def handle_checkout_request(email: str, amount: float) -> dict:
    """Endpoint controller processing cart checkout and receipt delivery."""
    success = process_subscription_charge(email, amount)
    dispatch_invoice_receipt(email, "acc_4001")
    return {"status": "paid", "amount": amount}

def handle_password_reset(email: str) -> dict:
    """Endpoint controller dispatching password reset security alerts."""
    send_security_alert(email, "password_reset_initiated")
    return {"status": "alert_dispatched"}
''')

    # 6. workers/cron_worker.py
    with open(os.path.join(target_dir, "workers", "cron_worker.py"), "w", encoding="utf-8") as f:
        f.write('''"""Background workers and scheduled cron tasks."""
from services.billing_service import calculate_monthly_invoices
from services.auth_service import revoke_session

def run_nightly_billing_cycle():
    """Nightly cron job reconciling subscriber ledger accounts."""
    results = calculate_monthly_invoices("acc_enterprise")
    return len(results)

def prune_expired_sessions():
    """Periodic worker clearing stale JWT sessions."""
    revoke_session("jwt.expired.0000")
''')
