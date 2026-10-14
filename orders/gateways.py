"""Payment gateways.

A gateway takes an order and returns the URL to send the student to. The
gateway then calls back; `verify` decides whether that callback really means
"paid". Keeping both sides behind one small interface means switching provider
touches this file only.

The default `sandbox` gateway completes the round-trip locally so the whole
checkout -> enrolment path is testable without credentials. SSLCommerz is
wired up to the point where only live credentials and the provider's current
endpoint are missing.
"""

import hashlib
import hmac
import logging

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """The gateway could not be reached or rejected the request."""


class BaseGateway:
    name = "base"

    def start_url(self, order, request):
        """Where to send the student to pay."""
        raise NotImplementedError

    def verify(self, order, data):
        """Return (is_paid, gateway_reference, reason) for a callback."""
        raise NotImplementedError


class SandboxGateway(BaseGateway):
    """Local stand-in for a hosted payment page.

    It redirects to a page in this project that offers "payment succeeded"
    and "payment failed", so failed-payment handling can be tested too.
    """

    name = "sandbox"

    def start_url(self, order, request):
        return reverse("orders:sandbox", kwargs={"reference": order.reference})

    def verify(self, order, data):
        token = data.get("token", "")
        if not hmac.compare_digest(token, order.callback_token):
            return False, "", "Callback token did not match."
        if data.get("result") != "success":
            return False, "", "Payment was declined."
        return True, f"SBX-{order.reference}", ""


class SSLCommerzGateway(BaseGateway):
    """SSLCommerz hosted checkout.

    Chosen as the default for Bangladesh: it covers bKash, Nagad, local cards
    and international cards under one settlement, which is what the brief asks
    for. `aamarPay` fits the same interface if fees favour it later.
    """

    name = "sslcommerz"
    SESSION_URL = (
        "https://sandbox.sslcommerz.com/gwprocess/v4/api.php",
        "https://securepay.sslcommerz.com/gwprocess/v4/api.php",
    )

    def __init__(self):
        config = settings.SSLCOMMERZ
        self.store_id = config["store_id"]
        self.store_password = config["store_password"]
        self.sandbox = config["sandbox"]
        if not (self.store_id and self.store_password):
            raise GatewayError(
                "SSLCOMMERZ_STORE_ID and SSLCOMMERZ_STORE_PASSWORD are not set."
            )

    @property
    def endpoint(self):
        return self.SESSION_URL[0 if self.sandbox else 1]

    def start_url(self, order, request):
        import json
        import urllib.parse
        import urllib.request

        base = settings.SITE["base_url"]
        payload = {
            "store_id": self.store_id,
            "store_passwd": self.store_password,
            "total_amount": f"{order.amount:.2f}",
            "currency": "BDT",
            "tran_id": order.reference,
            "success_url": base + reverse("orders:callback", kwargs={"outcome": "success"}),
            "fail_url": base + reverse("orders:callback", kwargs={"outcome": "fail"}),
            "cancel_url": base + reverse("orders:callback", kwargs={"outcome": "cancel"}),
            "ipn_url": base + reverse("orders:ipn"),
            "value_a": order.callback_token,
            "cus_name": order.student.get_full_name(),
            "cus_email": order.student.email,
            "cus_phone": "N/A",
            "product_name": order.course.title,
            "product_category": "Education",
            "product_profile": "non-physical-goods",
            "shipping_method": "NO",
        }
        request_body = urllib.parse.urlencode(payload).encode()
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed https endpoint
                self.endpoint, data=request_body, timeout=20
            ) as response:
                result = json.loads(response.read().decode())
        except Exception as exc:  # pragma: no cover - network path
            logger.exception("SSLCommerz session failed for %s", order.reference)
            raise GatewayError("Could not reach the payment gateway.") from exc
        url = result.get("GatewayPageURL")
        if not url:
            raise GatewayError(result.get("failedreason") or "Gateway refused the request.")
        return url

    def verify(self, order, data):
        """Validate the callback's own signature, then the amount and status."""
        if not self._signature_ok(data):
            return False, "", "Callback signature did not match."
        if data.get("value_a") and not hmac.compare_digest(
            data.get("value_a", ""), order.callback_token
        ):
            return False, "", "Callback token did not match."
        if data.get("status") not in {"VALID", "VALIDATED"}:
            return False, "", data.get("error") or "Payment was not completed."
        try:
            paid = float(data.get("amount") or data.get("store_amount") or 0)
        except (TypeError, ValueError):
            return False, "", "Callback amount was unreadable."
        if round(paid, 2) < round(float(order.amount), 2):
            return False, "", "Callback amount was lower than the order total."
        return True, data.get("bank_tran_id") or data.get("val_id", ""), ""

    def _signature_ok(self, data):
        received = data.get("verify_sign")
        keys = data.get("verify_key")
        if not (received and keys):
            return False
        store_hash = hashlib.md5(  # noqa: S324 - hash algorithm fixed by SSLCommerz
            self.store_password.encode()
        ).hexdigest()
        parts = sorted(f"{key}={data.get(key, '')}" for key in keys.split(","))
        parts.append(f"store_passwd={store_hash}")
        expected = hashlib.md5("&".join(sorted(parts)).encode()).hexdigest()  # noqa: S324
        return hmac.compare_digest(expected, received)


GATEWAYS = {
    SandboxGateway.name: SandboxGateway,
    SSLCommerzGateway.name: SSLCommerzGateway,
}


def get_gateway():
    try:
        return GATEWAYS[settings.PAYMENT_GATEWAY]()
    except KeyError as exc:
        raise GatewayError(f"Unknown gateway {settings.PAYMENT_GATEWAY!r}.") from exc
