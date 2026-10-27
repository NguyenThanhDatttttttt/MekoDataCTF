# One sandbox: four attackers, one server and one checker

This is one CyberRangeCZ Sandbox Definition. Create **one pool of size 1** from this repository root. The single sandbox contains four Kali attacker VMs, one Debian ServiceDesk server VM, one Debian checker VM, and a separate gateway router.

| Node | IP | HTTP |
| --- | --- | --- |
| attacker1 | `10.80.0.11` | `http://10.80.0.11/` |
| attacker2 | `10.80.0.12` | `http://10.80.0.12/` |
| attacker3 | `10.80.0.13` | `http://10.80.0.13/` |
| attacker4 | `10.80.0.14` | `http://10.80.0.14/` |
| server | `10.80.0.20` | ServiceDesk on port 80 |
| checker | `10.80.0.30` | Checks four attacker HTTP services every 60 seconds; saves SQLite history |
| gateway | `10.80.0.1` | Routing only |

**Traffic policy:** Each attacker can ping and open HTTP on the other three attackers. The server can ping and open HTTP on all four attackers. New connections from any attacker to `10.80.0.20` are blocked, including ping and HTTP. The server does not forward packets. ServiceDesk remains reachable locally on the server at `http://127.0.0.1/`; it is not reachable from the attacker VMs. HTTP access among the permitted machines uses port 80 without adding `:80` to the URL.

## Deploy

1. Put this directory at the root of a Git repository accessible to CyberRangeCZ. `topology.yml` and `provisioning/` must be at the repository root.
2. Create one Sandbox Definition from that Git URL and revision. Create one pool with **size 1**, then Allocate it. The provisioning playbook configures all six hosts and fails if the required connectivity policy does not work.
3. Import `training-definition.json`, review and release it, then create one cloud Training Instance and assign the pool. Open a run to see the six hosts in the topology. The attacker Linux login is `user-access / ClientLab-Only-2026!`.

The image and flavor names in `topology.yml` must exist in your cloud. The platform runner needs Ansible, the `user-access` role, and `ansible.posix` from `provisioning/requirements.yml`. The six host IPs and gateway subnet must not conflict with the platform's management network.

## Verify inside the sandbox

On attacker1, these must succeed:

```bash
ping -c 1 10.80.0.12
ping -c 1 10.80.0.13
ping -c 1 10.80.0.14
curl --noproxy '*' -fsS http://10.80.0.12/health
curl --noproxy '*' -fsS http://10.80.0.13/health
curl --noproxy '*' -fsS http://10.80.0.14/health
```

These must fail from every attacker:

```bash
ping -c 1 -W 2 10.80.0.20
curl --noproxy '*' --connect-timeout 3 http://10.80.0.20/
```

On the server, `curl --noproxy '*' http://127.0.0.1/health` must succeed, and `sudo nft list table inet idor_server_acl` must show the rule blocking new attacker connections. The server can also ping and curl all four attacker addresses.

The server ACL has its own nftables table and systemd unit; it does not replace other firewall tables. The provisioning playbook tests all permitted and blocked paths before it finishes. A private `10.x.x.x` URL is accessible only from the lab network or an approved tunnel.

## Local source checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

## Automatic service checker

The `checker` VM (`10.80.0.30`) runs `web-checker.service` automatically on boot.
It checks the four attacker services concurrently at `http://10.80.0.11/health`
through `http://10.80.0.14/health`, using port **80**, matching the deployed services.
Each check cycle starts every 60 seconds, with a 3 second socket timeout per target.
If a cycle runs longer than 60 seconds, the next cycle starts after it finishes;
cycles never overlap. These are monitoring cycles, not competition rounds yet.

UP requires HTTP 200, valid JSON with `status: ok`, and the expected `node` identity.
Connection failures, timeout, redirects, bad JSON, wrong identity or unhealthy status
produce DOWN. A failed target does not stop monitoring the others. The next successful
check reports UP again. Each JSON log entry contains a UTC timestamp, target results,
response times and error details. This checks HTTP availability, not login or ticket operations.

Every complete cycle is committed to `/var/lib/web-checker/results.sqlite3` before
logging. `check_cycles` stores a persistent cycle ID and UTC timestamp;
`check_results` stores four target results, URL, UP/DOWN, latency and error detail.
Both UP and DOWN results are saved. Service restarts and provisioning updates keep
existing history; destroying the VM deletes its local disk history unless backed up.
No external collector, scoreboard, flags or outbound API is configured.
The service runs as web-checker with write access only to its state directory.
Storage errors fail the process and appear in journal; systemd retries after 3 seconds.

Inspect the latest saved results on the checker VM without installing extra packages:

```bash
sudo python3 -c "import sqlite3; c=sqlite3.connect('file:/var/lib/web-checker/results.sqlite3?mode=ro', uri=True); print(*c.execute('SELECT c.id,c.checked_at,r.name,r.status,r.elapsed_ms,r.detail FROM check_cycles c JOIN check_results r ON r.cycle_id=c.id ORDER BY c.id DESC,r.name LIMIT 20'), sep='\n')"
```

History is retained without automatic deletion; monitor disk usage during long runs.

On the checker VM, use the platform management account to inspect it:

```bash
sudo systemctl status web-checker
sudo journalctl -u web-checker -f -o cat
sudo journalctl -u web-checker --since '10 minutes ago' -o cat
```

To change monitored services, edit `checker/web_targets.json` before provisioning,
or `/etc/web-checker/web_targets.json` on the checker VM, then run
`sudo systemctl restart web-checker`. Add multiple named targets per VM if needed;
use a JSON health endpoint returning `status: ok`. `expected_node` and
`expected_sandbox` are optional identity checks.

Run one manual round on the checker (exit 0 if all targets are UP, otherwise 1):

```bash
sudo -u web-checker python3 /opt/web-checker/web_health.py --config /etc/web-checker/web_targets.json --json
```

Allocate a new sandbox from the updated topology to create the extra VM; re-running
provisioning alone on an old five-host sandbox cannot create it. Provisioning runs
an initial check from the checker VM and fails if any of the four targets is DOWN.
The checker shares the lab LAN and remains outside the `attackers` group.
