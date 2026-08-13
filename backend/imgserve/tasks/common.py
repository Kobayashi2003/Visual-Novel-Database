SUCCESS = {'status': 'SUCCESS'}
FAILED = {'status': 'FAILED'}
NOT_FOUND = {'status': 'NOT_FOUND'}
# No detail: the message would surface filesystem paths and driver text to the
# caller. The traceback goes to the log instead.
ERROR = {'status': 'ERROR'}
