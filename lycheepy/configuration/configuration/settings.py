DATABASE = 'postgresql://lycheepy:lycheepy@persistence/lycheepy'
# DATABASE = 'postgresql://postgres:postgres@gpc/lycheepy'

HOST = '0.0.0.0'
PORT = 5000
DEBUG = True

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

PROCESS_SPECIFICATION_FIELD = 'specification'
PROCESS_FILE_FIELD = 'file'

ALLOWED_PROCESSES_EXTENSIONS = ['py']

PROCESSES_GATEWAY_HOST = 'processes'
PROCESSES_GATEWAY_USER = 'lycheepy'
PROCESSES_GATEWAY_PASS = 'lycheepy'
PROCESSES_GATEWAY_TIMEOUT = 30
PROCESSES_GATEWAY_DIRECTORY = 'processes'
