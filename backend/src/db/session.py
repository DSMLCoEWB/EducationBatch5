import sqlite3
import psycopg2
import re
from contextlib import contextmanager
from config import DB_PATH, DATABASE_TYPE, DATABASE_URL

# Rebind sqlite3 exceptions to psycopg2 exceptions when running on Postgres
# so that repository.py's 'except sqlite3.OperationalError:' blocks work on both backends.
if DATABASE_TYPE == "postgres":
    sqlite3.OperationalError = psycopg2.DatabaseError

BOOLEAN_COLS = [
    "is_inbox", "is_sent", "is_trashed", "is_priority_refined", "is_ocr_processed",
    "is_resolved", "manual_override", "replied", "is_demo", "has_attachment", "is_active"
]

def adapt_insert_vars(query: str, vars):
    if not vars:
        return vars
    
    query_upper = query.upper().strip()
    if not (query_upper.startswith("INSERT INTO") or query_upper.startswith("INSERT OR REPLACE INTO")):
        return vars
        
    start = query.find("(")
    if start == -1:
        return vars
    end = query.find(")", start)
    if end == -1:
        return vars
        
    cols_str = query[start+1:end]
    cols = [c.strip().strip('"').strip('`').lower() for c in cols_str.split(",")]
    
    new_vars = list(vars)
    for i, col in enumerate(cols):
        if i < len(new_vars) and col in BOOLEAN_COLS:
            val = new_vars[i]
            if val == 1 or val == "1":
                new_vars[i] = True
            elif val == 0 or val == "0":
                new_vars[i] = False
                
    return tuple(new_vars) if isinstance(vars, tuple) else new_vars

# Threaded connection pool for PostgreSQL (lazily initialized)
_pg_pool = None

def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import psycopg2.pool
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=30,
            dsn=DATABASE_URL
        )
    return _pg_pool

def translate_sqlite_to_postgres(query: str) -> str:
    """Translates SQLite SQL queries to PostgreSQL dialect on-the-fly."""
    if not query:
        return query
    
    # Fix subqueries without alias for PostgreSQL
    if ") ORDER BY" in query and "FROM (" in query:
        query = query.replace(") ORDER BY", ") AS subquery_alias ORDER BY")
    
    # Special handle for view check
    query = query.replace("COALESCE(a.manual_override, 0) = 0", "COALESCE(a.manual_override, FALSE) = FALSE")
    query = query.replace("COALESCE(manual_override, 0) = 0", "COALESCE(manual_override, FALSE) = FALSE")

    # Qualify column references in ON CONFLICT block for PostgreSQL
    query = query.replace("COALESCE(excluded.gmail_id, gmail_id)", "COALESCE(excluded.gmail_id, emails.gmail_id)")
    query = query.replace("COALESCE(excluded.thread_id, thread_id)", "COALESCE(excluded.thread_id, emails.thread_id)")
    query = query.replace("COALESCE(excluded.parent_email_id, parent_email_id)", "COALESCE(excluded.parent_email_id, emails.parent_email_id)")
    query = query.replace("COALESCE(excluded.sender, sender)", "COALESCE(excluded.sender, emails.sender)")
    query = query.replace("COALESCE(excluded.sender_email, sender_email)", "COALESCE(excluded.sender_email, emails.sender_email)")
    query = query.replace("COALESCE(excluded.recipient_email, recipient_email)", "COALESCE(excluded.recipient_email, emails.recipient_email)")
    query = query.replace("COALESCE(excluded.subject, subject)", "COALESCE(excluded.subject, emails.subject)")
    query = query.replace("COALESCE(excluded.content, content)", "COALESCE(excluded.content, emails.content)")
    query = query.replace("COALESCE(excluded.mail_type, mail_type)", "COALESCE(excluded.mail_type, emails.mail_type)")
    query = query.replace("COALESCE(excluded.date, date)", "COALESCE(excluded.date, emails.date)")
    query = query.replace("COALESCE(excluded.attachments, attachments)", "COALESCE(excluded.attachments, emails.attachments)")
    query = query.replace("COALESCE(excluded.attachment_content, attachment_content)", "COALESCE(excluded.attachment_content, emails.attachment_content)")
    query = query.replace("COALESCE(excluded.html_content, html_content)", "COALESCE(excluded.html_content, emails.html_content)")
    query = query.replace("COALESCE(excluded.followup_count, followup_count)", "COALESCE(excluded.followup_count, emails.followup_count)")
    query = query.replace("COALESCE(excluded.institute_name, institute_name)", "COALESCE(excluded.institute_name, emails.institute_name)")
    query = query.replace("COALESCE(excluded.to_address, to_address)", "COALESCE(excluded.to_address, emails.to_address)")
    query = query.replace("COALESCE(excluded.cc_address, cc_address)", "COALESCE(excluded.cc_address, emails.cc_address)")
    query = query.replace("COALESCE(excluded.bcc_address, bcc_address)", "COALESCE(excluded.bcc_address, emails.bcc_address)")
    # has_attachment: translate before the generic MAX→GREATEST pass so column is fully qualified
    query = query.replace(
        "has_attachment=MAX(COALESCE(has_attachment, 0), COALESCE(excluded.has_attachment, 0))",
        "has_attachment=GREATEST(COALESCE(emails.has_attachment, FALSE), COALESCE(excluded.has_attachment, FALSE))"
    )

    # MAX and Boolean logic in ON CONFLICT
    query = query.replace("MAX(replied, excluded.replied)", "(emails.replied OR excluded.replied)")
    query = query.replace("MAX(is_trashed, excluded.is_trashed)", "(emails.is_trashed OR excluded.is_trashed)")
    query = query.replace("MAX(is_inbox, excluded.is_inbox)", "(emails.is_inbox OR excluded.is_inbox)")
    query = query.replace("MAX(is_sent, excluded.is_sent)", "(emails.is_sent OR excluded.is_sent)")
    query = query.replace("MAX(is_priority_refined, excluded.is_priority_refined)", "(emails.is_priority_refined OR excluded.is_priority_refined)")
    query = query.replace("MAX(is_ocr_processed, excluded.is_ocr_processed)", "(emails.is_ocr_processed OR excluded.is_ocr_processed)")

    # CASE statements in ON CONFLICT
    query = query.replace("WHEN is_trashed=1 OR excluded.is_trashed=1", "WHEN emails.is_trashed=TRUE OR excluded.is_trashed=TRUE")
    query = query.replace("WHEN category IS NULL OR category = 'Sent' OR category = ''", "WHEN emails.category IS NULL OR emails.category = 'Sent' OR emails.category = ''")
    query = query.replace("ELSE category", "ELSE emails.category")
    query = query.replace("WHEN is_priority_refined=1", "WHEN emails.is_priority_refined=TRUE")
    query = query.replace("ELSE priority", "ELSE emails.priority")
    query = query.replace("THEN priority", "THEN emails.priority")

    # Translate MAX(col, excluded.col) to OR logic for boolean columns before general MAX replacement
    for col in BOOLEAN_COLS:
        pattern = r"\bMAX\(\s*([\w\.]+)?\b" + col + r"\b\s*,\s*([\w\.]+)?\b" + col + r"\b\s*\)"
        def repl_max(m):
            p1 = m.group(1) or ""
            p2 = m.group(2) or ""
            return f"({p1}{col} OR {p2}{col})"
        query = re.sub(pattern, repl_max, query, flags=re.IGNORECASE)

    # 1. Replace parameter placeholder
    query = query.replace("%", "%%")
    query = query.replace("?", "%s")
    
    # Translate boolean comparisons (e.g. is_inbox = 1 -> is_inbox = TRUE)
    for col in BOOLEAN_COLS:
        pattern = r"\b([\w\.]+)?\b" + col + r"\b\s*(=|!=|IS\s+NOT|IS)\s*(1|0|%s)\b"
        def repl_comp(m):
            prefix = m.group(1) or ""
            op = m.group(2)
            val = m.group(3)
            if val == "1":
                new_val = "TRUE"
            elif val == "0":
                new_val = "FALSE"
            else:
                new_val = "%s::boolean"
            return f"{prefix}{col} {op} {new_val}"
        query = re.sub(pattern, repl_comp, query, flags=re.IGNORECASE)
    
    # 2. Convert SQLite INTEGER PRIMARY KEY AUTOINCREMENT to PostgreSQL SERIAL PRIMARY KEY
    query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    
    # 3. Convert SQLite BOOLEAN defaults to Postgres BOOLEAN defaults
    query = query.replace("BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE")
    query = query.replace("BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE")
    
    # Translate LIKE to ILIKE for Postgres case-insensitivity (SQLite LIKE is case-insensitive)
    # Be careful not to replace it inside words, so use a regex or replace with spaces.
    query = re.sub(r'\bLIKE\b', 'ILIKE', query, flags=re.IGNORECASE)
    
    # 4. Convert SQLite scalar MAX(a, b) to PostgreSQL GREATEST(a, b)
    query = query.replace("MAX(", "GREATEST(")
    
    # 5. Translate SQLite INSERT OR REPLACE to PostgreSQL ON CONFLICT
    if "INSERT OR REPLACE INTO system_metadata" in query:
        query = query.replace("INSERT OR REPLACE INTO system_metadata", "INSERT INTO system_metadata")
        query += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    elif "INSERT OR REPLACE INTO revoked_sessions" in query:
        query = query.replace("INSERT OR REPLACE INTO revoked_sessions", "INSERT INTO revoked_sessions")
        query += " ON CONFLICT (user_email) DO UPDATE SET reason = EXCLUDED.reason"
    elif "INSERT OR REPLACE INTO priority_rules" in query:
        query = query.replace("INSERT OR REPLACE INTO priority_rules", "INSERT INTO priority_rules")
        query += " ON CONFLICT (priority, user_email) DO UPDATE SET label = EXCLUDED.label, keywords = EXCLUDED.keywords, description = EXCLUDED.description"
        
    return query

class PostgresRow(dict):
    """Custom dictionary-like row class that supports both key and integer index lookups like sqlite3.Row."""
    def __init__(self, data, description):
        super().__init__(data)
        self._keys = [desc[0] for desc in description]
        self._values = [data.get(k) for k in self._keys]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def keys(self):
        return self._keys
        
    def __iter__(self):
        # sqlite3.Row iterates over values when unpacked (e.g. a, b = row)
        return iter(self._values)

class PostgresCursorProxy:
    """Proxy wrapper for psycopg2 cursor to intercept and adapt SQLite commands and rows."""
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, vars=None):
        # Ignore SQLite-specific PRAGMA commands
        if query.strip().upper().startswith("PRAGMA"):
            return self
        
        adapted_query = translate_sqlite_to_postgres(query)
        adapted_vars = adapt_insert_vars(query, vars)
        
        # Use savepoints to prevent transaction abort on failed queries (e.g. migration checks)
        try:
            self._cursor.execute("SAVEPOINT sp_query")
        except Exception:
            self._cursor.execute(adapted_query, adapted_vars)
            return self

        try:
            self._cursor.execute(adapted_query, adapted_vars)
            # Release savepoint using a separate cursor to preserve the main cursor's result set
            temp_cur = self._cursor.connection.cursor()
            try:
                temp_cur.execute("RELEASE SAVEPOINT sp_query")
            finally:
                temp_cur.close()
        except Exception as e:
            try:
                temp_cur = self._cursor.connection.cursor()
                try:
                    temp_cur.execute("ROLLBACK TO SAVEPOINT sp_query")
                finally:
                    temp_cur.close()
            except Exception:
                pass
            raise e
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        desc = self._cursor.description
        data = {desc[i][0]: row[i] for i in range(len(desc))}
        return PostgresRow(data, desc)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        desc = self._cursor.description
        return [PostgresRow({desc[i][0]: r[i] for i in range(len(desc))}, desc) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        if not rows:
            return []
        desc = self._cursor.description
        return [PostgresRow({desc[i][0]: r[i] for i in range(len(desc))}, desc) for r in rows]

    def __getattr__(self, name):
        return getattr(self._cursor, name)

class PostgresConnectionProxy:
    """Proxy wrapper for psycopg2 connection to intercept and adapt SQLite patterns like row_factory."""
    def __init__(self, conn):
        self._conn = conn
        self.row_factory = None

    def cursor(self, *args, **kwargs):
        # Always wrap the cursor in PostgresCursorProxy
        cursor = self._conn.cursor(*args, **kwargs)
        return PostgresCursorProxy(cursor)

    def __getattr__(self, name):
        return getattr(self._conn, name)

@contextmanager
def get_db_conn(tenant_email: str = None):
    """Context manager for SQLite or PostgreSQL connections with proper pool recycling, transaction defaults, and Row-Level Security (RLS)."""
    if DATABASE_TYPE == "postgres":
        pool = _get_pg_pool()
        conn = pool.getconn()
        
        # Apply Row-Level Security tenant context
        if tenant_email:
            try:
                temp_cur = conn.cursor()
                temp_cur.execute("SET LOCAL app.current_tenant = %s", (tenant_email,))
                temp_cur.close()
            except Exception:
                pass
                
        proxy = PostgresConnectionProxy(conn)
        try:
            yield proxy
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        else:
            try:
                conn.commit()
            except Exception:
                pass
        finally:
            pool.putconn(conn)
    else:
        # SQLite
        conn = sqlite3.connect(DB_PATH, timeout=30)
        try:
            yield conn
        finally:
            conn.close()
