"""Money formatting.

One filter so every price on the site is punctuated the same way, rather than
each template remembering the symbol and the separator.
"""

from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def taka(amount, places=0):
    """Format an amount as Bangladeshi Taka: ``3500`` -> ``৳3,500``.

    `places` sets the decimals, so an order total can show ``৳3,500.00``.
    A negative amount uses a true minus sign, matching the design.
    """
    try:
        value = Decimal(amount)
    except (TypeError, ValueError, InvalidOperation):
        return ""
    sign = "−" if value < 0 else ""
    formatted = f"{abs(value):,.{int(places)}f}"
    return f"{sign}{settings.SITE['currency_symbol']}{formatted}"
