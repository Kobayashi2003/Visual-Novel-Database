"""Task outcomes.

Each value names one distinguishable reason a task ended, so the HTTP layer can
map it onto a status code without guessing (see routes/common.py). The previous
catch-all FAILED could not be mapped: it meant "no such image" for update and
delete, but "the upstream fetch did not succeed" for create.
"""

SUCCESS = {'status': 'SUCCESS'}
NOT_FOUND = {'status': 'NOT_FOUND'}      # no such image on record
CONFLICT = {'status': 'CONFLICT'}        # already on record
UNAVAILABLE = {'status': 'UNAVAILABLE'}  # upstream fetch failed or timed out

# No detail: the message would surface filesystem paths and driver text to the
# caller. The traceback goes to the log instead.
ERROR = {'status': 'ERROR'}
