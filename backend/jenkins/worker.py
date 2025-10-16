import os
import django

# 1️⃣ Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jenkins.settings")  # <- replace with your project settings

# 2️⃣ Initialize Django
django.setup()

# 3️⃣ Now import tasks and broker
from builds.tasks import broker
import dramatiq
from dramatiq.worker import worker

# 4️⃣ Run worker
if __name__ == "__main__":
    dramatiq.set_broker(broker)
    worker.main()
