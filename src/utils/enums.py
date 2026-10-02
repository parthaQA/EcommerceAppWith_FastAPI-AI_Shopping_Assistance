class OrderStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    READY_TO_SHIP = "READY TO SHIP"
    PACKED = "PACKED"
    OUT_FOR_DELIVERY = "OUT FOR DELIVERY"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

    @classmethod
    def cannot_cancel(cls) -> set[str]:
        return {
            cls.ACCEPTED,
            cls.READY_TO_SHIP,
            cls.PACKED,
            cls.OUT_FOR_DELIVERY,
            cls.CONFIRMED,
            cls.CANCELLED,
        }


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