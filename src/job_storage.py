"""
ANSIBLE-LINK class for jobs
Info: github.com/lfkdev/ansible-link
Author: l.klostermann@pm.me
License: MPL2
"""

import json
from pathlib import Path
from datetime import datetime

class JobStorage:
    def __init__(self, storage_dir):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_job_path(self, job_id):
        return self.storage_dir / f"{job_id}.json"

    def save_job(self, job_id, job_data):
        job_path = self._get_job_path(job_id)
        with open(job_path, 'w') as f:
            json.dump(job_data, f, indent=2)

    def update_job_result(self, job_id, result):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r+') as f:
                job_data = json.load(f)
                job_data['result'] = result
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()

    def update_job_progress(self, job_id, phase=None, label=None, expected_total=None, expected_weight=None, step_weight=None):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r+') as f:
                job_data = json.load(f)
                progress = job_data.get('progress', {
                    'phase': 'pending',
                    'completed_steps': 0,
                    'expected_total_steps': None,
                    'label': None,
                    'completed_weight': 0,
                    'expected_weight_total': None,
                })

                if phase:
                    progress['phase'] = phase
                    if phase == 'start':
                        progress['completed_steps'] = 0
                        progress['completed_weight'] = 0
                        if expected_total is not None:
                            progress['expected_total_steps'] = expected_total
                        if expected_weight is not None:
                            progress['expected_weight_total'] = expected_weight
                    if phase == 'step':
                        progress['completed_steps'] = progress.get('completed_steps', 0) + 1
                        if step_weight is not None:
                            progress['completed_weight'] = progress.get('completed_weight', 0) + step_weight
                    if phase in ['done', 'error']:
                        progress.setdefault('completed_steps', progress.get('completed_steps', 0))
                        progress.setdefault('completed_weight', progress.get('completed_weight', 0))
                if label is not None:
                    progress['label'] = label

                job_data['progress'] = progress
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()

    def append_job_event(self, job_id, event):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r+') as f:
                job_data = json.load(f)
                events = job_data.get('events', [])
                events.append(event)
                job_data['events'] = events
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()

    def get_job(self, job_id):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r') as f:
                return json.load(f)
        return None

    def get_all_jobs(self):
        jobs = {}
        for file_path in self.storage_dir.glob("*.json"):
            job_id = file_path.stem
            with open(file_path, 'r') as f:
                jobs[job_id] = json.load(f)
        return jobs

    def update_job_status(self, job_id, status):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r+') as f:
                job_data = json.load(f)
                job_data['status'] = status
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()

    def save_job_output(self, job_id, stdout, stderr, stats, ansible_cli_command):
        job_path = self._get_job_path(job_id)
        if job_path.exists():
            with open(job_path, 'r+') as f:
                job_data = json.load(f)
                job_data['stdout'] = stdout
                job_data['stderr'] = stderr
                job_data['stats'] = stats
                job_data['end_time'] = datetime.now().isoformat()
                job_data['ansible_cli_command'] = ansible_cli_command
                f.seek(0)
                json.dump(job_data, f, indent=2)
                f.truncate()
