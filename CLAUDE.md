# VisualNovelDatabase

A self-hosted VNDB mirror: five Flask services and a Next.js frontend behind one
Caddy edge.

```
backend/     vndb  userserve  imgserve  transserve  musicserve  logserve   (Flask + Waitress)
             procserve — the launcher's process supervisor; a library, not a service
frontend/    Next.js 16, basePath /visual-novel-database
Caddyfile*   the edge — routing plus the forward_auth gate
docs/api/    one OpenAPI 3.1 document per service, browsable at /docs
docs/assets/ architecture.svg is the source; architecture.png is rendered from it
```

The frontend routes, all under the basePath — `/v17` is served at
`/visual-novel-database/v17`:

| Route | Shows |
| --- | --- |
| `/` | Home — recent releases by year/month |
| `/[slug]` | One segment carries both type and id: `/v` searches visual novels, `/v17` is one |
| `/[slug]/rg` | Relation graph for a visual novel |
| `/u/c` | User collections — browse, search, sort, bulk-edit |
| `/kobayashi` | Music-player showcase of a user's VN collection |
| `/login`, `/reset-password` | Session entry points |

Run the whole stack with `.\start-prod.ps1` (add `-Build` to rebuild the
frontend first, `-Dev` for the dev servers). Postgres runs as a Windows service
and is not spawned by the script. **Do not `npm run build` while the stack is
running** — the running server holds `.next` open; stop the stack first.

`backend/temp/` is superseded code. Ignore it.

---

# Coding conventions

The HTTP contract lives in [docs/api/README.md](docs/api/README.md). The rest of
this document covers the layer beneath it: how the Python inside a service is
arranged, and what a function is expected to return to its own caller.

The two are separate on purpose. A route's job is to translate between the HTTP
contract and the internal one, and neither should leak into the other.

---

## 1. Services share nothing

Five Flask apps live under `backend/`. **No service imports from another** — the
invariant is checked easily and is currently exact:

```
vndb, userserve, imgserve, transserve, musicserve
  -> cross-service imports: none
```

They talk over HTTP through the edge, or not at all. There is deliberately no
shared package: a common library would couple deploy schedules and turn every
change into a five-service change.

The cost is duplication — `errors.py` is copied verbatim into each service, as is
`parse_bool` / `parse_int`. That is accepted. **Consistency is maintained by this
document, not by shared code.** When you change a copied file, change every copy.

The local idiom for sharing *within* a service is `<layer>/common.py`:
`routes/common.py`, `tasks/common.py`, `database/common.py`. Helpers used by one
layer live in that layer's `common.py`, not in a project-wide `utils`.

---

## 2. Layers

Not every service needs every layer — musicserve is one file plus a library
module. Those that do use them in this order, and calls only ever go **downward**:

```
routes/      HTTP in, HTTP out. Parses parameters, chooses status codes.
  |          Contains no business logic and no SQL.
  v
tasks/       Units of work. Runnable synchronously or on Celery.
  |          (transserve calls this layer service.py — one class, no queue.)
  v
search/      Query construction. vndb only: local / remote / both.
  |
  v
database/    Persistence. The only layer that touches the session.
```

`utils/` sits outside the stack and may be called from anywhere, but must depend
on nothing above it. `vndb/utils/ids.py` is the model: pure functions over
strings, no Flask, no database.

A layer may import its own `common.py` and anything below it. Importing upward —
`database` reaching into `tasks` — means the code is in the wrong place.

---

## 3. What a function returns

### Data layer: the value, or `None`

```python
def get(type: str, id: str) -> ImageType | None: ...
```

`None` means "not there". It does **not** mean "the operation failed" — those
raise, and the decorator below deals with them.

Where several distinct failures are possible, `None` is not enough. Either raise
a typed exception (see §4), or have the caller re-ask the question:

```python
# imgserve/tasks/images.py — create() returns None for two different reasons,
# so the task asks first and reports which one happened.
if exists(type, id):
    return CONFLICT
return SUCCESS if create(type, id) else UNAVAILABLE
```

**Never return a bare boolean for something that can fail in more than one way.**
A `False` that means both "nothing to do" and "it broke" cannot be mapped onto a
status code, and the caller ends up guessing.

### Task layer: an outcome envelope

A task may run on a Celery worker, so its result has to survive serialization and
carry its own outcome:

```python
{'status': 'SUCCESS', 'results': ...}
{'status': 'NOT_FOUND', 'results': None}
```

`status` is **internal**. It exists so a queued task can report an outcome across
a process boundary. It must never reach a client — see §5.

Every distinct outcome gets its own name. Do not add a catch-all:

```python
# imgserve
SUCCESS | NOT_FOUND | CONFLICT | UNAVAILABLE | ERROR
```

### Route layer: a Flask response

Routes return `(body, status_code)`. Nothing else in the service knows about
status codes.

### Paginated reads: always the same three keys

```python
{'results': [...], 'count': 1042, 'more': True}
```

`results` is always a list, even when at most one row can match. A function that
returns a bare list in one branch and an envelope in another forces every caller
to type-check.

---

## 4. Errors

### Raise for the exceptional; return for the expected

An empty search is expected — return an empty page. A malformed argument is
exceptional — raise.

### Typed exceptions carry a code

userserve's hierarchy is the model to copy:

```python
class ValidationError(Exception):
    error_code = "validation_error"
    message = "Invalid input."
    http_status = 400

class UsernameTakenError(InvalidUsernameError):
    error_code = "username_taken"
    message = "This username is already taken."
    http_status = 409
```

The class carries everything the route needs, so the route stays a one-liner:

```python
@api_bp.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify(error=e.error_code, message=e.message), e.http_status
```

An exception meant for the client **must** subclass the service's client-facing
base. A plain `Exception` subclass gets swallowed by the decorators below and
degrades into a generic 400 or 500.

### Never put an exception's text in a response

```python
return jsonify(error=str(e)), 500          # no — leaks paths, SQL, driver text
logger.exception(f"{func.__name__} failed") # yes — detail goes to the log
```

### Log with `logger.exception`, never `print`

`logger.exception` inside an `except` block records the traceback. `print` goes
nowhere useful under Waitress and is invisible in the log files.

---

## 5. The envelope stops at the route

This is the rule that connects this document to the HTTP one.

Inside the service, an outcome travels as `{'status': ...}`. At the route it
becomes a status code, and the field is dropped:

```python
TASK_STATUS_CODE = {'SUCCESS': 200, 'NOT_FOUND': 404, 'ERROR': 500}

def task_response(result):
    status = result.get('status', 'SUCCESS')
    code = TASK_STATUS_CODE.get(status, 200)
    if code != 200:
        return jsonify(error=http_error_code(code), message=...), code
    body = {k: v for k, v in result.items() if k != 'status'}
    return jsonify(body), 200
```

Two details that are easy to get wrong:

* **Build a new dict; never `pop`.** `NOT_FOUND` and friends are module-level
  singletons. Popping `status` off one mutates the constant for the rest of the
  process.
* **A queued task maps the same way.** `GET /tasks/<id>` must answer with the
  status code the synchronous call would have produced, or a client has to
  implement the contract twice.

---

## 6. Decorators do the repetitive work

```python
@db_transaction     # commit, or roll back and log        (vndb)
@save_db_operation  # same, but re-raises ValidationError (userserve)
@error_handler      # log the traceback, return ERROR     (tasks)
@task_basic         # celery.task + error_handler
@task_with_memoize  # the above, plus a cache read/write
```

A decorated function is written as if nothing fails: no `try` around the body, no
manual `commit()`, no manual `rollback()`.

`save_db_operation` is worth reading closely — it swallows unexpected exceptions
but **re-raises** the client-facing ones, which is what makes §4's typed errors
reach the client at all:

```python
except ValidationError:
    db.session.rollback()
    raise               # meant for the client
except Exception:
    db.session.rollback()
    logger.exception(...)
    return None         # meant for the log
```

---

## 7. Naming

### Verbs

| Verb | Meaning |
| --- | --- |
| `get_` | Fetch by primary key. `None` when absent. |
| `list_` | Fetch a page. Empty page when nothing matches. |
| `search_` | Fetch by criteria. |
| `lookup_` | Resolve one value to another (translation, id → name). |
| `count_` | An integer. |
| `exists_` / `is_` / `has_` | A boolean, and genuinely cannot fail. |
| `create_` / `update_` / `delete_` | Write one row. |
| `*_all` | The same, over every row of a type. |

### Peers are named symmetrically

If an operation exists for two peer concepts, both get all of it. transserve is
the worked example — `term` and `passage` each have all eight verbs:

```
lookup_term / lookup_passage        get_term / get_passage
list_term   / list_passage          init_term / init_passage
append_term / append_passage        delete_term / delete_passage
count_term  / count_passage         lookup_term_batch / lookup_passage_batch
```

A missing half is a design smell: either the concept is not really a peer, or the
half is missing by oversight.

### Batch variants take a `_batch` suffix

`lookup_term` takes one term; `lookup_term_batch` takes many and returns a dict
keyed by the input. Never overload one function to take either.

### Path and parameter names follow VNDB

`results`, `count`, `more`, and the single-letter type keys (`v`, `r`, `c`, `p`,
`s`, `g`, `i`) are the upstream API's, kept identical on purpose. Don't
"improve" them.

---

## 8. Comments

Comment the **why**, never the **what**. If the code says what it does, a comment
repeating it is noise that will drift out of date:

```python
# Database Initialization
# This section sets up the SQLAlchemy database connection      <- no
db = ExtSQLAchemy(app)

# Direct redis client for single-flight locking + the access ZSET.
# Its own DB, so it never shares a keyspace with Flask-Caching. <- yes
redis_client = ExtRedis(app)
```

Comment when:

* a decision has a reason that is not visible locally (why this timeout, why
  this DB number, why bypass the cache here);
* the code is subtle enough to be misread (the singleton/`pop` trap in §5);
* a section banner genuinely helps navigate a long file.

Banners mark functional groups and carry no prose:

```python
# ----------------------------------------
# Sessions
# ----------------------------------------
```

Delete commented-out code. Git remembers it.

A docstring earns its place when it states something the signature cannot —
what `None` means, what the keys of a returned dict are, which errors are
raised. `"""Get a user."""` on `get_user` is noise.

---

## 9. Configuration

Every knob is an environment variable read in `config.py`, with a default that
works on a fresh machine. A `config.py` comment explains *why* a value is what it
is — that file is the one place where a high comment density is correct.

Secrets have no default: `os.environ['SECRET_KEY']` fails loudly at boot rather
than silently running with a placeholder.
