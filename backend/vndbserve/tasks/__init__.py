"""Every task module, imported for its registration side effect.

A Celery task exists in a process only if the module defining it was imported
there. Most arrive by accident — the blueprints import the tasks their routes
call — but a task no route calls would then be registered only in the process
that sends it, and the worker would answer the message with `unregistered task`.

So the set of tasks a process knows is declared here rather than inferred from
which blueprints it happened to load, and `create_app` imports this package.
"""

from . import backfill, related_resources, relation_graph, resources, trash

__all__ = ['backfill', 'related_resources', 'relation_graph', 'resources', 'trash']
