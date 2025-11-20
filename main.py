import threading
import subprocess
from keepalive import run

# start keepalive server
threading.Thread(target=run, daemon=True).start()

# run original script
subprocess.Popen(["python", "Txt.py"])

# keep main alive
import time
while True:
    time.sleep(60)
