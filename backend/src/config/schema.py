from sqlalchemy import inspect,text
# Portable, idempotent upgrade for databases created before FX support.
# MySQL 8 and the SQLite test harness both accept these statements.
def ensure_schema(engine):
 insp=inspect(engine)
 tables=set(insp.get_table_names())
 if 'claims' not in tables:return
 cols={c['name'] for c in insp.get_columns('claims')}
 with engine.begin() as c:
  if 'currency' not in cols:c.execute(text("ALTER TABLE claims ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'CNY'"))
  if 'claim_date' not in cols:c.execute(text('ALTER TABLE claims ADD COLUMN claim_date VARCHAR(10)'))
  c.execute(text("UPDATE claims SET currency='CNY' WHERE currency IS NULL OR currency=''"))
 if 'trainings' in tables:
  cols={c['name'] for c in insp.get_columns('trainings')}
  with engine.begin() as c:
   if 'fx_book_id' not in cols:c.execute(text('ALTER TABLE trainings ADD COLUMN fx_book_id INTEGER'))
   if 'fx_rates' not in cols:c.execute(text('ALTER TABLE trainings ADD COLUMN fx_rates JSON'))
