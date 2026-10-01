import json

import aio_pika

from src.utils.settings import settings


class RabbitMQ:

    connection = None
    channel = None

    @classmethod
    async def connect(cls):
        cls.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        cls.channel = await cls.connection.channel()
        await cls.channel.declare_queue("product_bulk_queue", durable=True)

    @classmethod
    async def publish(cls, message):
        if cls.channel is None:
            await cls.connect()

        await cls.channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="product_bulk_queue",
        )

    @classmethod
    async def close(cls):
        if cls.connection is not None and not cls.connection.is_closed:
            await cls.connection.close()
        cls.connection = None
        cls.channel = None
