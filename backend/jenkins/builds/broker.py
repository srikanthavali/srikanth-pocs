import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from dramatiq.middleware import TimeLimit

broker = RabbitmqBroker(url="amqp://guest:guest@localhost:5672/")

# Only add TimeLimit if not already added
if not any(isinstance(m, TimeLimit) for m in broker.middleware):
    broker.add_middleware(TimeLimit(time_limit=7200000))  # 2 hours

dramatiq.set_broker(broker)
