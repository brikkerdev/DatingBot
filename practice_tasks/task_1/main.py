"""
Online Store Transactions — три сценария транзакций.

Сценарий 1: Размещение заказа (Order + OrderItems + обновление TotalAmount).
Сценарий 2: Атомарное обновление email клиента.
Сценарий 3: Атомарное добавление нового продукта.
"""

import os
import time
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from models import Base, Customer, Product, Order, OrderItem

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://store_user:store_pass@db:5432/store_db",
)


def wait_for_db(engine, retries: int = 10, delay: int = 2) -> None:
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(func.now().select())
            print("Database is ready.")
            return
        except Exception:
            print(f"Waiting for database... attempt {attempt}/{retries}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to database")


def seed(session: Session) -> None:
    """Заполняет БД начальными данными, если таблицы пусты."""
    if session.query(Customer).first():
        return

    c1 = Customer(first_name="Ivan", last_name="Petrov", email="ivan@example.com")
    c2 = Customer(first_name="Anna", last_name="Sidorova", email="anna@example.com")
    session.add_all([c1, c2])

    p1 = Product(product_name="Laptop", price=Decimal("75000.00"))
    p2 = Product(product_name="Mouse", price=Decimal("1500.00"))
    p3 = Product(product_name="Keyboard", price=Decimal("3000.00"))
    session.add_all([p1, p2, p3])

    session.commit()
    print("Seed data inserted.")


def place_order(
    session: Session,
    customer_id: int,
    items: list[dict],  # [{"product_id": int, "quantity": int}, ...]
) -> Order:
    """
    Создаёт заказ в одной транзакции:
    1. INSERT в orders
    2. INSERT позиций в order_items (subtotal = price * quantity)
    3. UPDATE orders.total_amount = SUM(subtotals)
    """
    order = Order(
        customer_id=customer_id,
        order_date=date.today(),
        total_amount=Decimal("0.00"),
    )
    session.add(order)
    session.flush()  # получаем order.id

    total = Decimal("0.00")
    for item in items:
        product = session.get(Product, item["product_id"])
        if product is None:
            raise ValueError(f"Product {item['product_id']} not found")

        subtotal = product.price * item["quantity"]
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item["quantity"],
            subtotal=subtotal,
        )
        session.add(order_item)
        total += subtotal

    order.total_amount = total
    session.commit()

    print(f"[Scenario 1] Order #{order.id} placed, total: {order.total_amount}")
    return order


def update_customer_email(
    session: Session,
    customer_id: int,
    new_email: str,
) -> Customer:
    """Атомарно обновляет email клиента."""
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    old_email = customer.email
    customer.email = new_email
    session.commit()

    print(
        f"[Scenario 2] Customer #{customer.id} email updated: "
        f"{old_email} -> {customer.email}"
    )
    return customer


def add_product(
    session: Session,
    product_name: str,
    price: Decimal,
) -> Product:
    """Атомарно добавляет новый продукт."""
    product = Product(product_name=product_name, price=price)
    session.add(product)
    session.commit()

    print(f"[Scenario 3] Product #{product.id} added: {product.product_name} ({product.price})")
    return product

def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    wait_for_db(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed(session)

    # Сценарий 1
    with Session(engine) as session:
        place_order(
            session,
            customer_id=1,
            items=[
                {"product_id": 1, "quantity": 1},  # Laptop
                {"product_id": 2, "quantity": 2},  # Mouse x2
            ],
        )

    # Сценарий 2
    with Session(engine) as session:
        update_customer_email(session, customer_id=1, new_email="ivan.new@example.com")

    # Сценарий 3
    with Session(engine) as session:
        add_product(session, product_name="Monitor", price=Decimal("25000.00"))

    print("\nAll scenarios completed successfully.")


if __name__ == "__main__":
    main()
