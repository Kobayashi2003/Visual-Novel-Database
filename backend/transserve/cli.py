"""`flask transserve` commands: schema, seeding, and the bundled snapshot.

`seed-terms` / `seed-passages` load translations from a file; `export-init`
writes the current contents back out to data/init.json, which is the snapshot
the Docker deployment ships so a fresh install starts with a populated term
base instead of an empty one.
"""

import os
import json
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import inspect

from transserve import db
from .models import MODEL_MAP
from . import operations

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DEFAULT_TERMS_FILE = os.path.join(DATA_DIR, 'terms.json')
DEFAULT_PASSAGES_FILE = os.path.join(DATA_DIR, 'passages.json')
DEFAULT_INIT_FILE = os.path.join(DATA_DIR, 'init.json')


def register_commands(app):
    app.cli.add_command(init_db)
    app.cli.add_command(drop_db)
    app.cli.add_command(clean_db)
    app.cli.add_command(inspect_db)
    app.cli.add_command(backup_db)
    app.cli.add_command(restore_db)
    app.cli.add_command(seed_terms)
    app.cli.add_command(seed_passages)
    app.cli.add_command(seed_init)
    app.cli.add_command(export_init)


@click.command('init-db')
@click.option('--drop', is_flag=True, help='Create after drop.')
@with_appcontext
def init_db(drop):
    """Initialize the database."""
    if drop:
        click.confirm('This operation will delete the database, do you want to continue?', abort=True)
        db.drop_all()
        click.echo('Dropped all tables.')
    db.create_all()
    click.echo('Initialized the database.')


@click.command('drop-db')
@click.option('--force', is_flag=True, help='Drop without confirmation.')
@with_appcontext
def drop_db(force):
    """Drop all tables in the database."""
    if not force:
        click.confirm('This operation will drop all tables in the database, do you want to continue?', abort=True)
    db.drop_all()
    click.echo('All tables have been dropped.')


@click.command('clean-db')
@click.option('--force', is_flag=True, help='Clean without confirmation.')
@with_appcontext
def clean_db(force):
    """Remove all data from the tables without dropping them."""
    if not force:
        click.confirm('This operation will delete all data in the database, do you want to continue?', abort=True)
    for model_name, model_class in MODEL_MAP.items():
        try:
            num_rows_deleted = db.session.query(model_class).delete()
            db.session.commit()
            click.echo(f'Deleted {num_rows_deleted} rows from {model_name}.')
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error cleaning {model_name}: {str(e)}', err=True)
    click.echo('Database cleaned successfully.')


@click.command('inspect-db')
@with_appcontext
def inspect_db():
    """Inspect the database schema."""
    inspector = inspect(db.engine)
    for model_name, model_class in MODEL_MAP.items():
        columns = inspector.get_columns(model_class.__tablename__)
        print(f"Table: {model_class.__tablename__}")
        print("Columns:")
        for column in columns:
            print(f"  - {column['name']} ({column['type']})")
        print("\n")


@click.command('seed-terms')
@click.option('-f', '--file', 'file_path', default=DEFAULT_TERMS_FILE,
              help='Path to the term JSON file.')
@click.option('--replace', is_flag=True,
              help='Clear the language pair before loading (full reinitialize).')
@with_appcontext
def seed_terms(file_path, replace):
    """Seed the term base from a JSON file (default: data/terms.json).

    File shape:
        {
          "source_lang": "en", "target_lang": "ja",
          "tag":   {"English tag name": "日本語訳", ...},
          "trait": {"English trait name": "日本語訳", ...}
        }
    Any top-level key whose value is an object of source→target pairs is loaded
    as a category. `source_lang` / `target_lang` are optional (default en→ja).
    """
    if not os.path.exists(file_path):
        click.echo(f"Term file not found: {file_path}", err=True)
        raise click.Abort()

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'ja')

    entries = []
    for category, mapping in data.items():
        if category in ('source_lang', 'target_lang') or not isinstance(mapping, dict):
            continue
        for source, target in mapping.items():
            if source and target:
                entries.append({'source': source, 'target': target, 'category': category})

    if not entries:
        click.echo("No entries found in the term file.", err=True)
        raise click.Abort()

    submitted = operations.init_term(
        entries, source_lang=source_lang, target_lang=target_lang, replace=replace)
    total = operations.count_term(source_lang, target_lang)
    click.echo(f"Seeded {submitted} entries ({source_lang}->{target_lang}); "
               f"term base now holds {total} entries for this pair.")


@click.command('seed-passages')
@click.option('-f', '--file', 'file_path', default=DEFAULT_PASSAGES_FILE,
              help='Path to the passages JSON file.')
@click.option('--replace', is_flag=True,
              help='Clear the language pair before loading (full reinitialize).')
@with_appcontext
def seed_passages(file_path, replace):
    """Seed the passage translation memory from a JSON file
    (default: data/passages.json).

    File shape:
        {
          "source_lang": "en", "target_lang": "ja",
          "passages": [
            {"source": "English description …",
             "target": "日本語訳 …",
             "entity_type": "tag" | "trait" | ...}
          ]
        }
    `source_lang` / `target_lang` are optional (default en->ja). Each translation
    is validated to preserve the source's VNDB markup tokens; a bad entry aborts
    the seed with a precise error.
    """
    if not os.path.exists(file_path):
        click.echo(f"Passages file not found: {file_path}", err=True)
        raise click.Abort()

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'ja')
    passages = data.get('passages') or []
    entries = [p for p in passages if p.get('source') and p.get('target')]

    if not entries:
        click.echo("No entries found in the passages file.", err=True)
        raise click.Abort()

    try:
        submitted = operations.init_passage(
            entries, source_lang=source_lang, target_lang=target_lang, replace=replace)
    except operations.ValidationError as e:
        click.echo(f"Seed aborted: {e.message}", err=True)
        raise click.Abort()
    total = operations.count_passage(source_lang, target_lang)
    click.echo(f"Seeded {submitted} passages ({source_lang}->{target_lang}); "
               f"memory now holds {total} passages for this pair.")


@click.command('seed-init')
@click.option('-f', '--file', 'file_path', default=DEFAULT_INIT_FILE,
              help='Path to the combined init JSON file.')
@click.option('--replace', is_flag=True,
              help='Clear each language pair before loading (full reinitialize).')
@with_appcontext
def seed_init(file_path, replace):
    """Seed both the term base and the passage TM from one combined init file
    (default: transserve/init.json).

    File shape:
        {
          "source_lang": "en", "target_lang": "ja",
          "terms": {"tag": {"name": "訳", ...}, "trait": {...}},
          "passages":  [{"source": "...", "target": "...", "entity_type": "tag"}, ...]
        }
    `source_lang` / `target_lang` are optional (default en->ja) and apply to both
    halves. Term entries load like `seed-terms`; passages load like
    `seed-passages` (markup preservation is validated, a bad entry aborts).
    """
    if not os.path.exists(file_path):
        click.echo(f"Init file not found: {file_path}", err=True)
        raise click.Abort()

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'ja')

    # --- term half ---
    # Accept the legacy 'dictionary' key so older exports still load.
    terms_by_category = data.get('terms') or data.get('dictionary') or {}
    dict_entries = []
    for category, mapping in terms_by_category.items():
        if not isinstance(mapping, dict):
            continue
        for source, target in mapping.items():
            if source and target:
                dict_entries.append({'source': source, 'target': target, 'category': category})

    if dict_entries:
        operations.init_term(
            dict_entries, source_lang=source_lang, target_lang=target_lang, replace=replace)
    dict_total = operations.count_term(source_lang, target_lang)
    click.echo(f"Terms: seeded {len(dict_entries)} entries; "
               f"now holds {dict_total} ({source_lang}->{target_lang}).")

    # --- passages half ---
    passages = data.get('passages') or []
    passage_entries = [p for p in passages if p.get('source') and p.get('target')]
    if passage_entries:
        try:
            operations.init_passage(
                passage_entries, source_lang=source_lang, target_lang=target_lang, replace=replace)
        except operations.ValidationError as e:
            click.echo(f"Passage seed aborted: {e.message}", err=True)
            raise click.Abort()
    passage_total = operations.count_passage(source_lang, target_lang)
    click.echo(f"Passages: seeded {len(passage_entries)} entries; "
               f"memory now holds {passage_total} ({source_lang}->{target_lang}).")


@click.command('export')
@click.option('-f', '--file', 'file_path', default=DEFAULT_INIT_FILE,
              help='Output path for the combined init JSON (default: data/init.json).')
@click.option('--source-lang', 'source_lang', default=None,
              help='Source language to export (default: app config / en).')
@click.option('--target-lang', 'target_lang', default=None,
              help='Target language to export (default: app config / ja).')
@with_appcontext
def export_init(file_path, source_lang, target_lang):
    """Export the term base + passage TM to a combined init JSON file.

    The inverse of `seed-init`: dumps the current DB in exactly the shape
    `seed-init` reads, so the bundled seed (data/init.json) can be refreshed
    from the live translation memory before a release. Term rows are
    grouped by `category`; passages become a flat list carrying `entity_type`
    (and `category` when set). Only the chosen language pair is exported, to
    mirror seed-init (which applies one pair to the whole file). Output is
    deterministically ordered so re-exports produce clean diffs.
    """
    from .models import TermEntry, PassageEntry

    source_lang = source_lang or current_app.config.get('SOURCE_LANG', 'en')
    target_lang = target_lang or current_app.config.get('TARGET_LANG', 'ja')

    # Sorting is done in Python (codepoint order on the source text), not in SQL:
    # the output must be byte-stable across machines, and a DB ORDER BY would
    # follow the server's collation instead. Categories and term entries
    # sort by source text; passages sort by (entity_type, source text) so each
    # entity group stays contiguous.

    # --- term half: {category: {source_text: target_text}} ---
    dict_rows = (db.session.query(TermEntry)
                 .filter(TermEntry.source_lang == source_lang)
                 .filter(TermEntry.target_lang == target_lang)
                 .all())
    grouped: dict[str, dict] = {}
    for row in dict_rows:
        grouped.setdefault(row.category or 'general', {})[row.source_text] = row.target_text
    terms_out = {
        cat: {src: grouped[cat][src] for src in sorted(grouped[cat])}
        for cat in sorted(grouped)
    }

    # --- passages half: [{source, target, entity_type[, category]}] ---
    passage_rows = (db.session.query(PassageEntry)
                    .filter(PassageEntry.source_lang == source_lang)
                    .filter(PassageEntry.target_lang == target_lang)
                    .all())
    passages = []
    for row in sorted(passage_rows, key=lambda r: (r.entity_type or '', r.source_text)):
        entry = {'source': row.source_text, 'target': row.target_text}
        if row.entity_type:
            entry['entity_type'] = row.entity_type
        if row.category:
            entry['category'] = row.category
        passages.append(entry)

    # Preserve an existing top-level `_comment` (a human note about the seed) if
    # the target file already carries one; otherwise omit it.
    comment = None
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding='utf-8') as f:
                comment = json.load(f).get('_comment')
        except (json.JSONDecodeError, OSError):
            comment = None

    out = {'source_lang': source_lang, 'target_lang': target_lang}
    if comment:
        out['_comment'] = comment
    out['terms'] = terms_out
    out['passages'] = passages

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    term_total = sum(len(v) for v in terms_out.values())
    breakdown = ', '.join(f'{k}:{len(v)}' for k, v in terms_out.items())
    click.echo(f"Exported {term_total} term entries ({breakdown}) and "
               f"{len(passages)} passages ({source_lang}->{target_lang}) to {file_path}.")


@click.command('backup-db')
@click.option('-f', '--filename', default=None, help='Specify a filename for the backup file.')
@with_appcontext
def backup_db(filename):
    """Backup the database using pg_dump."""
    if not filename:
        filename = 'transserve_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '.dump'

    db_url = urlparse(current_app.config['SQLALCHEMY_DATABASE_URI'])
    db_name = db_url.path[1:]
    db_user = db_url.username
    db_password = db_url.password
    db_host = db_url.hostname
    db_port = str(db_url.port)

    backup_folder = current_app.config['BACKUP_FOLDER']
    backup_path = os.path.join(backup_folder, filename)
    os.makedirs(backup_folder, exist_ok=True)

    env = os.environ.copy()
    env['PGPASSWORD'] = db_password

    command = [
        'pg_dump', '-h', db_host, '-p', db_port, '-U', db_user,
        '-F', 'c', '-f', backup_path, db_name,
    ]
    try:
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        click.echo("Database backup created successfully")
    except Exception as e:
        click.echo(f"Error creating database backup: {str(e)}", err=True)


@click.command('restore-db')
@click.argument('filename', type=click.Path(exists=True))
@with_appcontext
def restore_db(filename):
    """Restore the database from a backup file."""
    db_url = urlparse(current_app.config['SQLALCHEMY_DATABASE_URI'])
    db_name = db_url.path[1:]
    db_user = db_url.username
    db_password = db_url.password
    db_host = db_url.hostname
    db_port = str(db_url.port)

    env = os.environ.copy()
    env['PGPASSWORD'] = db_password

    command = [
        'pg_restore', '-h', db_host, '-p', db_port, '-U', db_user,
        '-d', db_name, '--clean', '--if-exists', '--no-owner', '--no-privileges',
        filename,
    ]
    try:
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        click.echo(f"Database restored successfully from: {filename}")
    except Exception as e:
        click.echo(f"Error restoring database: {str(e)}", err=True)
