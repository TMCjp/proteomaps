import logging
import sys
import os
from time import time

formatter = logging.Formatter('%(asctime)s %(filename)s %(lineno)s %(levelname)s  %(message)s')

stdout_handler = logging.StreamHandler(sys.stdout)
stderr_handler = logging.StreamHandler(sys.stderr)
file_handler = logging.FileHandler('/tmp/component_contribution_%f.log'%time())
stdout_handler.setFormatter(formatter)
stderr_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger = logging.getLogger('')
logger.addHandler(stdout_handler)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

print os.path.join(os.path.dirname(__file__), "../src")
