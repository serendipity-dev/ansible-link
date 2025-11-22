# Panoramica di Ansible-Link

Questo documento riassume le funzionalità presenti, il flusso di esecuzione dei job e l'architettura attuale del progetto Ansible-Link.

## Funzionalità principali
- **Avvio playbook Ansible via REST**: endpoint `POST /ansible/playbook` che valida la richiesta, genera un `job_id` e avvia l'esecuzione in un thread separato tramite `ansible-runner` restituendo 202. 【F:src/ansible_link.py†L230-L274】【F:src/ansible_link.py†L153-L229】
- **Persistenza dei job**: salvataggio in file JSON (`job-storage`) con metadati, stato e output; interrogazione tramite `GET /ansible/job/<job_id>` e `GET /ansible/jobs`. 【F:src/ansible_link.py†L278-L305】【F:src/job_storage.py†L12-L62】
- **Consultazione output/progresso**: endpoint `GET /ansible/job/<job_id>/output` per ottenere stdout/stderr aggregati, eventi e risultato finale, `GET /ansible/job/<job_id>/progress` per avere solo lo snapshot di avanzamento con i soli eventi di progresso, e `GET /ansible/job/<job_id>/result` per recuperare il JSON finale da `set_stats`. 【F:src/ansible_link.py†L306-L346】【F:src/job_storage.py†L12-L74】
- **Webhook opzionali**: notifiche per eventi `job_started`, `job_completed` e `job_error` con formattazione specifica per Slack/Discord o payload generico. 【F:src/ansible_link.py†L157-L225】【F:src/webhook.py†L13-L71】
- **Metriche Prometheus**: contatori per run totali, istogramma per durata e gauge per job attivi, esposti da un server interno. 【F:src/ansible_link.py†L154-L229】【F:src/ansible_link.py†L336-L353】
- **Discovery playbook**: elenco dei playbook disponibili in base alla whitelist configurata. 【F:src/ansible_link.py†L293-L305】

## Concorrenza e comportamento asincrono
- Ogni richiesta di esecuzione avvia un *nuovo thread* che esegue `ansible-runner`, permettendo a più client di lanciare job in parallelo. Non esiste un meccanismo di coda: i job partono subito e condividono le risorse del processo. 【F:src/ansible_link.py†L259-L274】【F:src/ansible_link.py†L153-L193】
- Il client riceve subito il `job_id` e può disconnettersi; lo stato e l'output vengono scritti su disco e sono recuperabili con `GET /ansible/job/<job_id>` anche dopo che il job è terminato. 【F:src/ansible_link.py†L243-L291】【F:src/job_storage.py†L20-L62】

## Stati del job
- **Persistiti**: `pending` (al salvataggio iniziale), `running` (impostato all'avvio del runner), `completed` oppure `failed` (in base a `runner.status`), `error` (eccezioni). 【F:src/ansible_link.py†L193-L238】【F:src/ansible_link.py†L243-L273】
- **Avanzamento**: i callback `event_handler` di `ansible-runner` catturano le linee di stdout con metadati (evento, contatore, UUID, timestamp) e le persistono in `events` per il job. Il campo `progress` mantiene fase (`pending|start|step|done|error`), `completed_steps`, `expected_total_steps`, `completed_weight`, `expected_weight_total` e l'ultima `label` ricevuta. 【F:src/ansible_link.py†L199-L249】【F:src/job_storage.py†L18-L74】
- **Output live**: l'endpoint `GET /ansible/job/<job_id>/output` restituisce stato, stdout aggregato dalle `events`, stderr, il campo `progress` aggiornato, l'eventuale `result` JSON finale (derivato da `set_stats`) e gli eventi stessi per consultare il progresso in tempo reale; in alternativa `GET /ansible/job/<job_id>/progress` e `GET /ansible/job/<job_id>/result` permettono di recuperare solo l'avanzamento o solo il risultato finale. 【F:src/ansible_link.py†L306-L346】【F:src/job_storage.py†L18-L74】

### Come vengono catturati gli eventi
- `ansible-runner` emette per ogni passo un payload `event_data` che include, tra gli altri, `event`, `counter`, `stdout`, `uuid` e `created`.
- Il `event_handler` registrato in `run_playbook` intercetta ogni evento: quando è presente `stdout`, crea un dizionario con i metadati (`timestamp`, `event`, `counter`, `stdout`, `uuid`) e lo aggiunge a `job.events` tramite `JobStorage.append_job_event`. 【F:src/ansible_link.py†L193-L238】【F:src/job_storage.py†L18-L35】
- Le linee che matchano il formato `[AL_PROGRESS <phase>] key=value ...` vengono ulteriormente parsate per aggiornare `job.progress` con fase (`start|step|done|error`), conteggio step, pesi e label. Questo consente di separare gli eventi di avanzamento dal resto dello stdout e alimentare una progress-bar. 【F:src/ansible_link.py†L199-L249】【F:src/job_storage.py†L18-L74】
- Gli output finali strutturati sono raccolti dagli eventi `set_stats` di Ansible e salvati in `job.result`, evitando di veicolarli via stdout. 【F:src/ansible_link.py†L213-L248】【F:src/job_storage.py†L18-L74】

Esempio di progress standardizzato in un playbook con 4 step:

```yaml
- name: inizio esecuzione
  ansible.builtin.debug:
    msg: "[AL_PROGRESS start] expected_total=4 expected_weight=4 label=\"Deploy applicazione\""

- name: step 1
  ansible.builtin.shell: ./task1.sh
- name: step 1 completato
  ansible.builtin.debug:
    msg: "[AL_PROGRESS step] weight=1 label=\"Task 1 completato\""

# ... ripetere per step successivi ...

- name: completato
  ansible.builtin.debug:
    msg: "[AL_PROGRESS done] label=\"Deploy terminato\""

- name: pubblica risultato finale strutturato
  ansible.builtin.set_stats:
    data:
      endpoint: "https://app.example.com"
      version: "1.2.3"
```

## Scheduling e gestione della concorrenza
- **Nessuna coda**: i job sono eseguiti immediatamente nel thread creato; la concorrenza è delegata al modello multithread di Flask + il thread manuale per runner.
- **Limiti**: assenza di throttling o pool di worker; un numero elevato di richieste può saturare le risorse.

## Architettura (PlantUML)
### Componenti principali
```plantuml
@startuml
package "Ansible-Link API" {
  [Flask-RESTX API] --> [JobStorage]
  [Flask-RESTX API] --> [WebhookSender]
  [Flask-RESTX API] --> [Prometheus Metrics]
  [Flask-RESTX API] --> [Ansible Runner Thread]
}

[Ansible Runner Thread] --> [ansible-runner]
[ansible-runner] --> [Inventory/Playbooks]
[JobStorage] --> [File System (job-storage)]
[WebhookSender] --> [Webhook Endpoint]
[Prometheus Metrics] --> [Prometheus Scraper]
@enduml
```

### Sequenza esecuzione job
```plantuml
@startuml
actor Client
participant "Flask /ansible/playbook" as API
participant "JobStorage" as Store
participant "Thread run_playbook" as Runner
participant "ansible-runner" as AR
participant "WebhookSender" as WH
participant "Prometheus" as PM

Client -> API: POST playbook
API -> API: valida input
API -> Store: save_job(status=pending)
API -> Runner: start thread
API --> Client: 202 job_id

Runner -> WH: job_started
Runner -> Store: update_status(running)
Runner -> AR: run()
AR -> Runner: event(stdout,...)
Runner -> Store: append_job_event()
Runner -> PM: ACTIVE_JOBS++
AR --> Runner: status (successful/failed) + output
Runner -> Store: update_status(completed/failed)
Runner -> Store: save_job_output()
Runner -> PM: PLAYBOOK_RUNS++, DURATION
Runner -> WH: job_completed/job_error
Runner -> PM: ACTIVE_JOBS--
@enduml
```
## Esempi d'uso dell'API con i playbook demo
Gli endpoint sono esposti con prefisso `/api/v2/ansible` (versione ricavata da `src/version.py`). Gli esempi seguenti usano `BASE_URL=http://localhost:5001/api/v2/ansible` e l'inventory di default incluso (`examples/inventory/hosts`).

### Playbook disponibili e parametri attesi
Use `GET $BASE_URL/available-playbooks` per verificare i playbook caricati. 【F:src/ansible_link.py†L427-L440】

| Playbook | Variabili funzionali (da passare in `vars`) | Risultato finale (da `set_stats`) |
| --- | --- | --- |
| `playbooks/bootstrap_tenant.yml` | `tenant_name` (nome tenant) 【F:examples/playbooks/bootstrap_tenant.yml†L5-L17】 | ID tenant e URL degli endpoint di automazione 【F:examples/playbooks/bootstrap_tenant.yml†L66-L79】 |
| `playbooks/cost_report.yml` | `start`, `end` (intervallo ISO8601), `resources` (lista opzionale di tipi: `vps`, `k8s`, `nstar`) 【F:examples/playbooks/cost_report.yml†L5-L18】【F:examples/playbooks/cost_report.yml†L41-L69】 | Totale costi e dettaglio per categoria + items filtrati 【F:examples/playbooks/cost_report.yml†L71-L80】 |
| `playbooks/vps.yml` | `hostname`, `cpu`, `memory_gb`, `image`, `network` 【F:examples/playbooks/vps.yml†L5-L22】 | URL/IP della VPS e credenziali admin generate 【F:examples/playbooks/vps.yml†L56-L64】 |
| `playbooks/nstar.yml` | `tenant`, `app_size` 【F:examples/playbooks/nstar.yml†L5-L18】 | URL servizio, tenant e credenziali admin 【F:examples/playbooks/nstar.yml†L41-L55】 |
| `playbooks/k8s.yml` | `cluster_name`, `version`, `workers`, `worker_flavor` 【F:examples/playbooks/k8s.yml†L5-L22】 | URL API, kubeconfig e credenziali admin del cluster 【F:examples/playbooks/k8s.yml†L44-L76】 |

_Nota_: le variabili `_total_weight`, `min_wait`, `max_wait` e `steps` servono solo per la demo/progress e non vanno specificate dai client.

### Avvio di un job (POST /playbook)
L'endpoint `POST $BASE_URL/playbook` accetta il playbook, l'inventory (opzionale) e le variabili. Restituisce `202` con `job_id` per il polling. 【F:src/ansible_link.py†L297-L353】

Esempi di payload reali (uno per ciascun playbook):

```bash
curl -X POST "$BASE_URL/playbook" \
  -H "Content-Type: application/json" \
  -d '{
        "playbook": "playbooks/bootstrap_tenant.yml",
        "vars": { "tenant_name": "acme-app" }
      }'

curl -X POST "$BASE_URL/playbook" \
  -H "Content-Type: application/json" \
  -d '{
        "playbook": "playbooks/cost_report.yml",
        "vars": {
          "start": "2025-02-01T00:00:00Z",
          "end": "2025-02-28T23:59:59Z",
          "resources": ["vps", "k8s"]
        }
      }'

curl -X POST "$BASE_URL/playbook" \
  -H "Content-Type: application/json" \
  -d '{
        "playbook": "playbooks/vps.yml",
        "vars": {
          "hostname": "app-01",
          "cpu": 4,
          "memory_gb": 8,
          "image": "ubuntu-22",
          "network": "dmz"
        }
      }'

curl -X POST "$BASE_URL/playbook" \
  -H "Content-Type: application/json" \
  -d '{
        "playbook": "playbooks/nstar.yml",
        "vars": { "tenant": "finance", "app_size": "medium" }
      }'

curl -X POST "$BASE_URL/playbook" \
  -H "Content-Type: application/json" \
  -d '{
        "playbook": "playbooks/k8s.yml",
        "vars": {
          "cluster_name": "lab-cluster",
          "version": "1.29",
          "workers": 5,
          "worker_flavor": "medium"
        }
      }'
```

La risposta tipica: `{ "job_id": "<UUID>", "status": "running", "errors": null }`.

### Monitoraggio e consultazione
- **Lista job recenti**: `GET $BASE_URL/jobs` restituisce ID, stato e playbook correnti. 【F:src/ansible_link.py†L355-L359】
- **Dettaglio stato**: `GET $BASE_URL/job/<job_id>` riporta metadata, progress, eventi e result salvati. 【F:src/ansible_link.py†L360-L369】
- **Solo output e log evento**: `GET $BASE_URL/job/<job_id>/output` aggrega stdout/stderr, eventi, progress e result. 【F:src/ansible_link.py†L369-L390】
- **Solo avanzamento**: `GET $BASE_URL/job/<job_id>/progress` restituisce fase corrente e soli eventi di progresso (`[AL_PROGRESS ...]`). 【F:src/ansible_link.py†L393-L410】
- **Solo risultato finale**: `GET $BASE_URL/job/<job_id>/result` ritorna il payload pubblicato via `set_stats` dal playbook (es. ID tenant, kubeconfig, ecc.). 【F:src/ansible_link.py†L412-L425】

Esempio di polling minimal:

```bash
JOB_ID=<UUID_RICEVUTO>

# Stato sintetico
curl "$BASE_URL/job/$JOB_ID"

# Output + avanzamento live
curl "$BASE_URL/job/$JOB_ID/output"

# Solo avanzamento (per progress bar)
curl "$BASE_URL/job/$JOB_ID/progress"

# Risultato finale strutturato (una volta completato)
curl "$BASE_URL/job/$JOB_ID/result"
```

Quando il playbook termina, `progress.phase` diventa `done` (o `error`) e `result` contiene gli artifact specifici del job, come ad esempio:
- `bootstrap_tenant.yml`: `{ "tenant": { "id": "<id>" }, "automations": { "urls": { ... } } }` 【F:examples/playbooks/bootstrap_tenant.yml†L66-L79】
- `cost_report.yml`: `{ "summary": { "total": <float>, "byCategory": {...} }, "items": [...] }` 【F:examples/playbooks/cost_report.yml†L71-L80】
- `vps.yml`: `{ "vps": { "url": "https://app-01.example.local", "ip": "..." }, "admin": {...} }` 【F:examples/playbooks/vps.yml†L56-L64】
- `nstar.yml`: `{ "nstar": { "url": "https://nstar.example.local/<tenant>" }, "tenant": "...", "admin": {...} }` 【F:examples/playbooks/nstar.yml†L41-L55】
- `k8s.yml`: `{ "cluster": { "name": "lab-cluster", "url": "..." }, "admin": {...}, "kubeconfig": "..." }` 【F:examples/playbooks/k8s.yml†L44-L76】
  
## Considerazioni su funzionalità mancanti o migliorabili
- **Endpoint per output live**: oltre a `GET /ansible/job/<job_id>/output`, sono disponibili endpoint dedicati per progresso (`/progress`) e risultato (`/result`); ulteriori estensioni potrebbero includere streaming SSE/WebSocket. 【F:src/ansible_link.py†L306-L346】
- **Coda/pool di esecuzione**: non esistono limiti di concorrenza o meccanismi di scheduling; introdurre un worker pool o una coda permetterebbe di controllare il carico. 【F:src/ansible_link.py†L259-L274】
- **Persistenza thread-safe/DB**: la gestione file-based può diventare un collo di bottiglia o creare race condition con molti job; l'uso di lock o di un backend DB migliorerebbe l'affidabilità. 【F:src/job_storage.py†L12-L62】
