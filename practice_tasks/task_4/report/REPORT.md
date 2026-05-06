# Отчёт: Аномалии изоляции в SQL

## Выбранные аномалии

1. **Dirty Read** — чтение неподтверждённых данных
2. **Non-Repeatable Read** — неповторяемое чтение
3. **Phantom Read** — фантомное чтение
4. **Lost Update** — потерянное обновление

---

## Стек

- MySQL 8
- Python 3.12
- Docker Compose
- aiomysql

---

## Dirty Read

### Определение
Транзакция T1 читает данные, которые были изменены другой транзакцией T2, но ещё не подтверждены (COMMIT).

### Особенность MySQL
MySQL поддерживает READ UNCOMMITTED, что позволяет видеть неподтверждённые данные.

### Шаги воспроизведения

| Шаг | T1 | T2 |
|-----|----|----|
| 1 | BEGIN (READ UNCOMMITTED) | |
| 2 | | BEGIN |
| 3 | | UPDATE accounts SET balance=2000 |
| 4 | SELECT balance → 2000 | |
| 5 | | ROLLBACK |
| 6 | SELECT balance → 1000 | |

### Результат

```json
{
  "tx1_first_read": "2000.00",
  "tx1_second_read": "1000.00",
  "outcome": "DIRTY_READ occurred - TX1 read uncommitted data"
}
```

**Вывод:** MySQL с READ UNCOMMITTED позволяет читать неподтверждённые данные (dirty read).

### Как избежать
- Использовать уровень изоляции READ COMMITTED (по умолчанию в MySQL) или выше

---

## Non-Repeatable Read

### Определение
Транзакция T1 читает строку дважды и получает разные значения.

### Шаги воспроизведения

| Шаг | T1 | T2 |
|-----|----|----|
| 1 | BEGIN (READ COMMITTED) | |
| 2 | SELECT balance → 1000 | |
| 3 | | BEGIN |
| 4 | | UPDATE balance=1500 |
| 5 | | COMMIT |
| 6 | SELECT balance → 1500 | |

### Результат

```json
{
  "tx1_first_read": "1000.00",
  "tx1_second_read": "1500.00",
  "outcome": "NON_REPEATABLE_READ occurred"
}
```

### Как избежать
- REPEATABLE READ или SERIALIZABLE
- `SELECT ... FOR UPDATE`

---

## Phantom Read

### Определение
Транзакция T1 выполняет SELECT дважды, получает разное количество строк.

### Шаги воспроизведения

| Шаг | T1 | T2 |
|-----|----|----|
| 1 | BEGIN (READ COMMITTED) | |
| 2 | SELECT COUNT(*) → 3 | |
| 3 | | BEGIN |
| 4 | | INSERT INTO products |
| 5 | | COMMIT |
| 6 | SELECT COUNT(*) → 4 | |

### Результат

```json
{
  "tx1_first_count": "3",
  "tx1_second_count": "4",
  "outcome": "PHANTOM_READ occurred"
}
```

### Как избежать
- REPEATABLE READ с gap locks
- SERIALIZABLE

---

## Lost Update

### Определение
Две транзакции читают одно значение, обновляют независимо — последнее перезаписывает первое.

### Шаги воспроизведения

| Шаг | T1 | T2 |
|-----|----|----|
| 1 | BEGIN | BEGIN |
| 2 | SELECT balance → 1000 | SELECT balance → 1000 |
| 3 | UPDATE balance=1100 | |
| 4 | | UPDATE balance=1200 |
| 5 | COMMIT | COMMIT |
| | Результат: 1100 | (потеряно!) |

### Результат

```json
{
  "tx1_initial": "1000.0",
  "tx2_initial": "1000.0",
  "tx2_final": "1200.0",
  "tx1_final": "1100.0",
  "final_balance": "1100.00",
  "outcome": "LOST_UPDATE occurred - update from TX1 was lost"
}
```

**Вывод:** Lost update detected! Ожидалось 1200, получили 1100.

### Как избежать
- SERIALIZABLE
- `SELECT ... FOR UPDATE`
- Использовать транзакционные блокировки

---

## Результаты тестирования

| Аномалия | Воспроизведена | Уровень изоляции |
|----------|--------------|-----------------|
| Dirty Read | Да | READ UNCOMMITTED |
| Non-Repeatable Read | Да | READ COMMITTED |
| Phantom Read | Да | READ COMMITTED |
| Lost Update | Да | READ COMMITTED (autocommit) |

---

## Выводы

MySQL с уровнем READ UNCOMMITTED:
- Позволяет Dirty Read (чтение неподтверждённых данных)

MySQL с уровнем READ COMMITTED:
- Предотвращает Dirty Read
- Допускает Non-Repeatable Read
- Допускает Phantom Read
- Допускает Lost Update

MySQL с REPEATABLE READ:
- Предотвращает Dirty Read
- Предотвращает Non-Repeatable Read
- Предотвращает Phantom Read (благодаря gap locks)
- Допускает Lost Update

Для полной изоляции: SERIALIZABLE

---

## Инструкция по запуску

```bash
# Запуск тестов
docker compose up --build

# Проверить результаты
type results\run.log

# Проверить JSON результаты
type results\dirty_read.json
type results\non_repeatable_read.json
type results\phantom_read.json
type results\lost_update.json
```