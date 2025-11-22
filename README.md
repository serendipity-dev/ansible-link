<div align="center" style="display: flex; align-items: center;">
  <img src="logo.png" alt="Ansible Link Logo" width="100" height="100" style="margin-right: 20px;">
  <div>
    <h1>ANSIBLE LINK</h1>
    <p>
      RESTful API for executing Ansible playbooks remotely
    </p>
  </div>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.7%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Linux-lightgrey" alt="Linux">
  <img src="https://img.shields.io/badge/Flask--RESTx-Swagger-green" alt="Flask-RESTx">
  <img src="https://img.shields.io/badge/Ansible--Runner-1.4-red" alt="Ansible Runner">
</p>

## Features
- **Playbook Execution** Asynchronous playbook executions with real-time status updates.
- **Playbook History** Keep track of playbook executions and their status.
- **Playbook History** Keep track of playbook executions and their status, including incremental progress logs captured from ansible-runner callbacks.
- **API Documentation** Swagger UI documentation for easy exploration of the API endpoints.
- **Metrics** Exposes Prometheus metrics for playbook runs, durations, and active jobs.
- **Webhook Notifications** Send notifications to Slack, Discord, or custom webhooks for job events.

<b>NOTE</b> Project is usable but still in early development.

## Motivation
Searched for a way to run our playbooks automated without the need of AWX or other big projects while still being more stable and less error-prone than custom bash scripts. So I made Ansible-Link. This projects aims to be a KISS way to run ansible jobs remotely. Essentially a RESTful API sitting on top of [ansible-runner](https://github.com/ansible/ansible-runner).

## Prerequisites
* Ansible CLI installed
* Your playbooks and inventory files

## Installation
The fastest way to set up Ansible-Link is by using the provided `install.sh` script:

**Download and run the install script:**
```shell
wget https://raw.githubusercontent.com/lfkdev/ansible-link/main/install.sh
sudo bash install.sh
```

This script will:
- Check for necessary dependencies and install them if missing.
- Download and install Ansible-Link.
- Set up a Python virtual environment.
- Configure a systemd service for Ansible-Link.

After the installation, you can start using Ansible-Link immediately. You probably need to change some config values for your ansible environment `/opt/ansible-link/config.yml`

```yaml
playbook_dir: '/etc/ansible/'
inventory_file: '/etc/ansible/environments/hosts'
...
```
To add more workers or change the user, modify `/etc/systemd/system/ansible-link.service`
> ⚠️ **Note:** Currently, only Ubuntu versions 16.04 and higher, or Debian versions 9 and higher are officially supported.
> Other operating systems might also work but have not been tested. You can clone the repository and perform a manual installation if you are using a different OS.

## Esecuzione con Docker
Il progetto include un container pronto all'uso che ha al suo interno tutte le dipendenze (incluso Ansible) e i playbook di esempio.

### Build dell'immagine
```bash
docker build -t ansible-link .
```

### Avvio con Docker
```bash
docker run --rm \
  -p 5001:5001 \
  -p 9090:9090 \
  ansible-link
```

### Avvio con Docker Compose
```bash
docker compose up --build
```

### Verifica esecuzione API e playbook di esempio
L'API espone la documentazione Swagger su `http://localhost:5001/api/v2/`. Per avviare un playbook di esempio già presente nel container, puoi usare:
```bash
curl -X POST http://localhost:5001/api/v2/ansible/playbook \
  -H "Content-Type: application/json" \
  -d '{"playbook": "bootstrap_tenant.yml", "inventory": "/app/examples/inventory/hosts"}'
```
Il container monta automaticamente una cartella persistente per lo `job_storage` tramite un volume nominato nel file `docker-compose.yml`.

## API Documentation
The API documentation is available via the Swagger UI.

<img src="docs.png" alt="Ansible Link Docs">

## API Endpoints

* <code>POST /ansible/playbook: Execute a playbook</code>
* <code>GET /ansible/jobs: List all jobs</code>
* <code>GET /ansible/job/<job_id>: Get job status</code>
* <code>GET /ansible/job/<job_id>/output: Get job output</code>
* <code>GET /ansible/job/<job_id>/output: Get combined live output, progress events, and any structured <code>result</code> emitted via set_stats at completion</code>
* <code>GET /ansible/job/<job_id>/progress: Retrieve only the tracked progress snapshot and the filtered progress events</code>
* <code>GET /ansible/job/<job_id>/result: Retrieve only the final structured result captured via <code>set_stats</code></code>
* <code>GET /health: Health check endpoint</code>

### Standard progress markers for roles
To avoid mixing noise with progress updates, Ansible-Link filters structured progress events emitted on stdout.

- Prefix progress lines with the marker `[AL_PROGRESS <phase>]` where `<phase>` is `start`, `step`, `done`, or `error`.
- Append space-separated `key=value` pairs. Numbers are parsed as integers; quoted strings are preserved. JSON payloads are also parsed when provided as compact JSON (or quoted) values.
- The API aggregates these markers and stores them under `job.progress`, which is returned by `GET /ansible/job/<job_id>/output` together with the raw `events` list and can be queried alone via `GET /ansible/job/<job_id>/progress`.
- Standard parameters:
  - `start`: `expected_total=<int>` (numero di step previsti), `expected_weight=<int>` (peso totale previsto), `label="..."` opzionale.
  - `step`: `weight=<int>` per il peso dello step corrente, `label="..."` opzionale.
  - `done|error`: `label="..."` opzionale. Gli output finali strutturati non si passano più via marker `done`, ma tramite `set_stats` (vedi sotto).

Suggested events for a task with 3 steps:

```yaml
- name: announce job start with total steps
  ansible.builtin.debug:
    msg: "[AL_PROGRESS start] expected_total=3 expected_weight=3 label=\"Deploy stack\""

- name: do step one
  ansible.builtin.shell: ./step1.sh
- name: step one done
  ansible.builtin.debug:
    msg: "[AL_PROGRESS step] weight=1 label=\"Step 1 completed\""

# ...repeat for steps 2 and 3...

- name: all done
  ansible.builtin.debug:
    msg: "[AL_PROGRESS done] label=\"Deployment finished\""

# emit structured result via set_stats
- name: publish final structured result
  ansible.builtin.set_stats:
    data:
      endpoint: "https://app.example.com"
      version: "1.2.3"
```

If a fatal condition occurs, emit `[AL_PROGRESS error] label="reason"` before failing the task to update the tracked phase.

### Playbook di esempio
Nella cartella `examples/playbooks` sono disponibili playbook dimostrativi che emettono marker di avanzamento e restituiscono un risultato strutturato tramite `set_stats`:

- `bootstrap_tenant.yml`: bootstrap di un tenant con pesi percentuali e pubblicazione degli endpoint di automazione.
- `vps.yml`: provisioning di una VPS con step ponderati e credenziali di amministrazione generate al termine.
- `k8s.yml`: creazione di un cluster Kubernetes/OpenShift con kubeconfig fittizia come artifact finale.
- `nstar.yml`: provisioning applicativo con creazione schema tenant e credenziali admin.
- `cost_report.yml`: generazione di un report costi con filtri opzionali e breakdown per categoria.


## Configuration
The API configuration is stored in the `config.yml` file. 
If you move your config to a different location you can use `ANSIBLE_LINK_CONFIG_PATH` 
```shell
$ export ANSIBLE_LINK_CONFIG_PATH='/etc/ansible-link/config.yml'
```

You can customize the following settings:

```yaml
# webhook
# webhook:
#   url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
#   type: "slack" # "slack", "discord" or "generic" supported
#   timeout: 5  # optional, default 5 seconds

# flask
host: '127.0.0.1'
port: 5001
debug: false

# ansible-runner
suppress_ansible_output: false
omit_event_data: false
only_failed_event_data: false

# promtetheus
metrics_port: 9090

# general
playbook_dir: '/etc/ansible/'
inventory_file: '/etc/ansible/environments/hosts'
job_storage_dir: '/var/lib/ansible-link/job-storage'
log_level: 'INFO'

# ansible-link
playbook_whitelist: []
# playbook_whitelist:
#   - monitoring.yml
#   - mariadb.yml
```

The whitelist supports <b>full regex</b>, you could go wild:
```yaml
playbook_whitelist:
  # Allow all playbooks in the 'test' directory
  - ^test/.*\.ya?ml$

  # Allow playbooks starting with 'prod_' or 'dev_'
  - ^(prod|dev)_.*\.ya?ml$

  # Allow specific playbooks
  - ^(backup|restore|maintenance)\.ya?ml$
```
Leave empty to allow all playbooks. This is for the backend, you could also use the `limit` arg from ansible-runner in the request directly.

## Prod environment

You can use the install script `install.sh` to get a production-ready environment for Ansible-Link.

The install script will:
- Set up a Python VENV
- Configure a systemd service to manage Ansible-Link
- Utilize Gunicorn as the WSGI server
- Start Ansible-Link to liste only on localhost

You can use a webserver like Caddy to add Basic Authentication and TLS to your Ansible-Link setup.

Also, if you're using a webserver, you can change Gunicorn to use sockets instead. For example:
```shell
ExecStart=$VENV_DIR/bin/gunicorn --workers 1 --bind unix:$INSTALL_DIR/ansible_link.sock -m 007 wsgi:application
```


### unitD example
```
[Unit]
Description=Ansible Link Service
After=network.target

[Service]
ExecStart=$VENV_DIR/bin/gunicorn --workers 1 --bind 127.0.0.1:$ANSIBLE_LINK_PORT wsgi:application
WorkingDirectory=$INSTALL_DIR
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

### Example setup:
```
├── etc/
│   └── ansible/
│       ├── playbooks/
│       │   └── some_playbooks.yml
│       └── inventory/
│           ├── production
│           └── staging
│
├── opt/
│   └── ansible-link/
│       ├── ansible-link.py
│       └── config.yml
│
└── var/
    └── lib/
        └── ansible-link/
            └── job-storage/
                └── playbook_name_20230624_130000_job_id.json
```

## Webhook Configuration
Ansible-Link supports sending webhook notifications for job events. You can configure webhooks for Slack, Discord, or a generic endpoint. Add the following to your config.yml:

```yaml
webhook:
  url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
  type: "slack"  # Options: slack, discord, generic
  timeout: 5  # Optional, defaults to 5 seconds
```

or leave it commented out to disable webhooks

* **url** The webhook URL for your chosen platform.
* **type** The type of webhook (slack, discord, or generic).
* **timeout** The timeout for webhook requests in seconds (optional, default is 5 seconds).

Only Slack and Discord are supported for now, you can also use `generic` which will send the base JSON payload:

```json
{
    "event_type": event_type,
    "job_id": job_data['job_id'],
    "playbook": job_data['playbook'],
    "status": job_data['status'],
    "timestamp": datetime.now().isoformat()
}
```

The following notifcations are sent:

* Job Started
* Job Completed (success or failure)
* Job Error

View `webhook.py` for more info.

## Usage

Below are examples demonstrating how to use ansible-link API compared to Ansible CLI.

---
```bash
$ ansible-playbook site.yml
```

```json
{
  "playbook": "site.yml"
}
```

```bash
curl -X POST http://your-ansible-link-server/ansible/playbook \
  -H "Content-Type: application/json" \
  -d '{"playbook": "site.yml"}'
```
---

```bash
$ ansible-playbook deploy.yml -e version=1.5.0 environment=staging
```

```json
{
  "playbook": "deploy.yml",
  "vars": {
    "version": "1.5.0",
    "environment": "staging"
  }
}
```
---

```bash
$ ansible-playbook site.yml --tags "update,packages" -vv
```

```json
{
  "playbook": "site.yml",
  "tags": "update,packages",
  "verbosity": 2
}
```
---

```bash
$ ansible-playbook restore.yml --limit "databases" --forks 3
```

```json
{
  "playbook": "restore.yml",
  "limit": "databases",
  "forks": 3
}
```

---
```bash
$ ansible-playbook site.yml -i custom_inventory.ini -e '{"key1": "value1", "key2": "value2"}' --tags "provision,configure" --skip-tags "cleanup" --limit "webservers:&staged" --forks 10 -vvv
```

```json
{
  "playbook": "site.yml",
  "inventory": "custom_inventory.ini",
  "vars": {
    "key1": "value1",
    "key2": "value2"
  },
  "tags": "provision,configure",
  "skip_tags": "cleanup",
  "limit": "webservers:&staged",
  "forks": 10,
  "verbosity": 3
}
```

--- 

```bash
$ ansible-playbook site.yml -i custom_inventory.ini -e environment=production --diff --check
```

```json
{
  "playbook": "site.yml",
  "inventory": "custom_inventory.ini",
  "vars": {
    "environment": "production"
  },
  "cmdline": "--diff --check"
}
```
Ansible-Link supports the following native parameters:

* playbook: The name of the playbook to run (required)
* inventory: Path to the inventory file
* vars (extravars): A dictionary of additional variables to pass to the playbook
* limit: A host pattern to further constrain the list of hosts
* verbosity: Control the output level of ansible-playbook
* forks: Specify number of parallel processes to use
* tags: Only run plays and tasks tagged with these values
* skip_tags: Only run plays and tasks whose tags do not match these values
* cmdline: Any additional command line options to pass to ansible-playbook

Which means you can always use cmdline if your arg is not natively supported, like:

```json
{
  "playbook": "site.yml",
  "cmdline": "--diff --check -e environment=production -i /etc/ansible/test/custom_inventory.ini"
}
```

### Output
Ansible-Link will save each job as .json with the following info (from ansible-runner):
```json
{
  "status": "successfull",
  "playbook": "<playbook_name>",
  "inventory": null,
  "vars": {
    "customer": "emind"
  },
 "start_time": "2024-06-24T15:32:35.380662",
  "stdout": "<ANSIBLE PLAYBOOK OUTPUT>",
  "stderr": "",
  "stats": {
    "skipped": {
      "<playbook_name>": 8
    },
    "ok": {
      "<playbook_name>": 28
    },
    "dark": {},
    "failures": {
      "<playbook_name>": 1
    },
    "ignored": {},
    "rescued": {},
    "processed": {
      "<playbook_name>": 1
    },
    "changed": {}
  }
}
```
essentially showing everything ansible-playbook would display.

<b>Note</b> After submitting a request to the API, you will receive a job ID. You can use this job ID to check the status and retrieve the output of the playbook run using the /ansible/job/<job_id> and /ansible/job/<job_id>/output endpoints respectively.
<b>Note</b> After submitting a request to the API, you will receive a job ID. You can use this job ID to check the status and retrieve the output of the playbook run using the /ansible/job/<job_id> and /ansible/job/<job_id>/output endpoints respectively; use /ansible/job/<job_id>/progress or /ansible/job/<job_id>/result if you only need the progress snapshot or the final structured payload.

### How progress events are captured
- `ansible-runner` invokes an `event_handler` on every event; when `stdout` is present the handler stores the line together with `event`, `counter`, `uuid` and the timestamp under the job's `events` array. 【F:src/ansible_link.py†L193-L238】【F:src/job_storage.py†L18-L35】
- Roles/playbooks do not need special APIs: any text printed to stdout (e.g. `ansible.builtin.debug: msg=...`, `set_stats`, assertions) becomes a progress event visible via `GET /ansible/job/<job_id>/output`. Use `GET /ansible/job/<job_id>/progress` when the client needs only the progress snapshot and progress-tagged events, or `GET /ansible/job/<job_id>/result` to fetch solely the final structured outcome. Emit concise, frequent messages in key tasks to surface meaningful progress.

## Metrics
Ansible-Link exposes the following metrics:

```python
PLAYBOOK_RUNS = Counter('ansible_link_playbook_runs_total', 'Total number of playbook runs', ['playbook', 'status'])
PLAYBOOK_DURATION = Histogram('ansible_link_playbook_duration_seconds', 'Duration of playbook runs in seconds', ['playbook'])
ACTIVE_JOBS = Gauge('ansible_link_active_jobs', 'Number of currently active jobs')
```

The metrics can be used to set alerts, track the history of jobs, monitor performance and so on

## Security Considerations
* Use TLS in production
* Add basic auth

## Contributing
Contributions are always welcome - if you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## License
This project is licensed under the MPL2 License. See the LICENSE file for more information.



