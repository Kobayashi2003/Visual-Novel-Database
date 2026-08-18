# Comment Standard

## 1. Kinds

Only four kinds of comment are written. Anything that is none of them is not
written.

| Kind | States |
| --- | --- |
| **what** | What this code is |
| **how** | How this code is used |
| **why** | Why this code had to be written |
| **dev** | A note left during development — always carries its marker: `TODO`, `TEST`, … |

## 2. Necessity

Before writing a comment, be sure the comment is necessary.

## 3. Similarity

There is no prescribed format. Before and after writing a comment, look at how
similar code is commented: the more alike two pieces of code are, the more alike
their comments should be.

## 4. Completeness

There is no length limit. Every point must be stated clearly and completely;
under that constraint, keep the comment as brief as it can be.

## 5. Language

All comments are written in English.

## 6. Exclusions

No comments are written in `temp/`, which holds superseded versions, or in
`backend/*/migrations/`, which Alembic generates.

Within the codebase, `__init__.py` that only re-exports and modules named after
their single purpose (`logger.py`, `extensions.py`) are left uncommented.
