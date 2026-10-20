# One sandbox: four attackers and one server

This is one CyberRangeCZ Sandbox Definition. Create **one pool of size 1** from this repository root. The single sandbox contains four Kali attacker VMs, one Debian ServiceDesk server VM, and a separate gateway router.

| Node | IP | HTTP |
| --- | --- | --- |
| attacker1 | `10.80.0.11` | `http://10.80.0.11/` |
| attacker2 | `10.80.0.12` | `http://10.80.0.12/` |
| attacker3 | `10.80.0.13` | `http://10.80.0.13/` |
| attacker4 | `10.80.0.14` | `http://10.80.0.14/` |
| server | `10.80.0.20` | ServiceDesk on port 80 |
| gateway | `10.80.0.1` | Routing only |

**Traffic policy:** Each attacker can ping and open HTTP on the other three attackers. The server can ping and open HTTP on all four attackers. New connections from any attacker to `10.80.0.20` are blocked, including ping and HTTP. The server does not forward packets. ServiceDesk remains reachable locally on the server at `http://127.0.0.1/`; it is not reachable from the attacker VMs. HTTP access among the permitted machines uses port 80 without adding `:80` to the URL.

## Deploy

1. Put this directory at the root of a Git repository accessible to CyberRangeCZ. `topology.yml` and `provisioning/` must be at the repository root.
2. Create one Sandbox Definition from that Git URL and revision. Create one pool with **size 1**, then Allocate it. The provisioning playbook configures all five hosts and fails if the required connectivity policy does not work.
3. Import `training-definition.json`, review and release it, then create one cloud Training Instance and assign the pool. Open a run to see the five hosts in the topology. The attacker Linux login is `user-access / ClientLab-Only-2026!`.

The image and flavor names in `topology.yml` must exist in your cloud. The platform runner needs Ansible, the `user-access` role, and `ansible.posix` from `provisioning/requirements.yml`. The five host IPs and gateway subnet must not conflict with the platform's management network.

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
