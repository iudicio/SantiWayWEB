import clickhouse_connect

client = clickhouse_connect.get_client(
    host='localhost',
    port=8123,
    username='default',
    password=''
)

print("Подключение к ClickHouse... OK")

print("\nВыполняю schema.sql...")
with open('clickhouse/schema.sql', 'r') as f:
    sql = f.read()

statements = []
current = []
for line in sql.split('\n'):
    line = line.strip()
    if line.startswith('--') or not line:
        continue
    current.append(line)
    if line.endswith(';'):
        stmt = ' '.join(current)
        statements.append(stmt)
        current = []

for stmt in statements:
    if stmt.strip():
        try:
            client.command(stmt)
            print(f"{stmt[:60]}...")
        except Exception as e:
            print(f"Ошибка: {e}")

print("\nВыполняю views.sql...")
with open('clickhouse/views.sql', 'r') as f:
    sql = f.read()

statements = []
current = []
in_create = False
for line in sql.split('\n'):
    line_stripped = line.strip()
    if line_stripped.startswith('--') or not line_stripped:
        continue
    
    if 'CREATE MATERIALIZED VIEW' in line_stripped or 'CREATE TABLE' in line_stripped:
        if current:
            statements.append(' '.join(current))
            current = []
        in_create = True
    
    current.append(line_stripped)
    
    if line_stripped.endswith(';') and in_create:
        statements.append(' '.join(current))
        current = []
        in_create = False

if current:
    statements.append(' '.join(current))

for stmt in statements:
    if stmt.strip():
        try:
            client.command(stmt)
            print(f"{stmt[:60]}...")
        except Exception as e:
            print(f"Ошибка: {e}")

print("\n=== Таблицы в anomaly_demo ===")
result = client.query("SHOW TABLES FROM anomaly_demo")
for row in result.result_rows:
    print(f"  - {row[0]}")

print("\n База данных готова!")
