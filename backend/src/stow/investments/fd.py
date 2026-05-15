from datetime import date
from decimal import Decimal


def accrued_interest(principal: int, rate_bps: int, start: date, compounding: str) -> int:
    t_days = (date.today() - start).days
    if t_days <= 0:
        return 0
    rate = Decimal(rate_bps) / Decimal(10000)
    t_years = Decimal(t_days) / Decimal(365)
    periods = {"simple": None, "monthly": 12, "quarterly": 4, "yearly": 1}
    n = periods[compounding]
    if n is None:
        interest = Decimal(principal) * rate * t_years
    else:
        interest = Decimal(principal) * ((1 + rate / n) ** (n * t_years) - 1)
    return int(interest)
