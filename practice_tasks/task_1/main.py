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

def verify_no_order(session: Session, label: str) -> None:
    """Проверяет, что после rollback заказ и позиции НЕ попали в БД."""
    order_count = session.query(Order).count()
    item_count = session.query(OrderItem).count()
    print(f"  [{label}] Orders: {order_count}, OrderItems: {item_count}")


def verify_email_unchanged(session: Session, customer_id: int, expected: str) -> None:
    """Проверяет, что email не изменился после rollback."""
    customer = session.get(Customer, customer_id)
    actual = customer.email if customer else "<not found>"
    match = "OK" if actual == expected else "MISMATCH"
    print(f"  [Check] email = {actual} (expected {expected}) — {match}")


def verify_product_count(session: Session, expected: int) -> None:
    """Проверяет количество продуктов после rollback."""
    count = session.query(Product).count()
    match = "OK" if count == expected else "MISMATCH"
    print(f"  [Check] products count = {count} (expected {expected}) — {match}")


# ---------------------------------------------------------------------------
# Демонстрации rollback (inconsistent-состояние предотвращено)
# ---------------------------------------------------------------------------
def demo_rollback_scenario1(session: Session) -> None:
    """
    Сценарий 1 — rollback: второй товар не существует (product_id=999).
    Без транзакции заказ бы создался, но без части позиций — inconsistent.
    С транзакцией: ничего не сохраняется.
    """
    print("\n--- Scenario 1: ROLLBACK demo (bad product_id) ---")
    try:
        place_order(
            session,
            customer_id=1,
            items=[
                {"product_id": 1, "quantity": 1},
                {"product_id": 999, "quantity": 1},  # не существует
            ],
        )
    except ValueError as e:
        session.rollback()
        print(f"  Transaction rolled back: {e}")


def demo_rollback_scenario2(session: Session) -> None:
    """
    Сценарий 2 — rollback: обновляем email несуществующего клиента.
    """
    print("\n--- Scenario 2: ROLLBACK demo (bad customer_id) ---")
    try:
        update_customer_email(session, customer_id=999, new_email="ghost@example.com")
    except ValueError as e:
        session.rollback()
        print(f"  Transaction rolled back: {e}")


def demo_rollback_scenario3(session: Session) -> None:
    """
    Сценарий 3 — rollback: цена отрицательная — нарушение бизнес-правила.
    """
    print("\n--- Scenario 3: ROLLBACK demo (negative price) ---")
    try:
        if Decimal("-100") < 0:
            raise ValueError("Price must be positive")
        add_product(session, product_name="Bad Product", price=Decimal("-100"))
    except ValueError as e:
        session.rollback()
        print(f"  Transaction rolled back: {e}")


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    wait_for_db(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed(session)

    # Успешные сценарии
    print("\nSuccessful transactions:")

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

    # Демонстрация rollback
    print("\nRollback demos (inconsistency prevention):")

    # Запоминаем состояние ДО rollback-демонстраций
    with Session(engine) as session:
        orders_before = session.query(Order).count()
        items_before = session.query(OrderItem).count()
        products_before = session.query(Product).count()

    # Rollback сценарий 1: заказ с несуществующим товаром
    with Session(engine) as session:
        demo_rollback_scenario1(session)
    with Session(engine) as session:
        verify_no_order(session, "After rollback")
        assert session.query(Order).count() == orders_before, "Order leaked!"
        assert session.query(OrderItem).count() == items_before, "OrderItems leaked!"
        print("  -> БД consistent: ни Order, ни OrderItems не утекли.")

    # Rollback сценарий 2: обновление email несуществующего клиента
    with Session(engine) as session:
        demo_rollback_scenario2(session)
    with Session(engine) as session:
        verify_email_unchanged(session, customer_id=1, expected="ivan.new@example.com")
        print("  -> БД consistent: email не изменился.")

    # Rollback сценарий 3: продукт с отрицательной ценой
    with Session(engine) as session:
        demo_rollback_scenario3(session)
    with Session(engine) as session:
        verify_product_count(session, expected=products_before)
        print("  -> БД consistent: лишний продукт не добавлен.")

    print("\nAll done.")


if __name__ == "__main__":
    main()
