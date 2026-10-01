class OrderStatus:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentStatus:
    UNPAID = "UNPAID"
    PAID = "PAID"


class PaymentMode:
    COD = "COD"
    ONLINE = "ONLINE"

    @classmethod
    def values(cls) -> set[str]:
        return {
            value
            for key, value in vars(cls).items()
            if key.isupper() and isinstance(value, str)
        }