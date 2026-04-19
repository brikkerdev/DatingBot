import os
import sys


def main() -> None:
    role = os.getenv("ROLE", "").lower()
    if role == "producer":
        import producer
        producer.run()
    elif role == "consumer":
        import consumer
        consumer.run()
    else:
        print(f"Unknown ROLE: {role!r}. Expected 'producer' or 'consumer'.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
